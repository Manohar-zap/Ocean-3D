/* OCEAN 3D — Adaptive Mission 3D Simulation Engine */

var viewer = null;
let currentMissionData = null;
let simulationData = null;
let missionEntities = [];
let instrumentEntities = {};
let playback = null;

// ─── Depth coordinate system ───────────────────────────────────────────────
// Ocean depth is represented as negative ellipsoid height (meters below sea surface).
// NEVER use positive altitude (2500/3000) as a depth substitute.

function positionFromLatLonDepth(lat, lon, depthM) {
  const alt = depthM <= 0 ? 0.0 : -Math.abs(depthM);
  return Cesium.Cartesian3.fromDegrees(lon, lat, alt);
}

function headingToQuaternion(headingDeg, pitchDeg) {
  const h = Cesium.Math.toRadians(headingDeg || 0);
  const p = Cesium.Math.toRadians(pitchDeg || 0);
  const hpr = new Cesium.HeadingPitchRoll(h, p, 0);
  return Cesium.Transforms.headingPitchRollQuaternion(Cesium.Cartesian3.ZERO, hpr);
}

function apiUrl(path) {
  const base = (typeof window !== 'undefined' && window.BACKEND_API_BASE) || 'http://localhost:8000';
  return `${base.replace(/\/$/, '')}${path}`;
}

// ─── Instrument procedural 3D builders ───────────────────────────────────────

function createInstrumentModel(viewer, id, type, lat, lon, depthM, headingDeg, label, status) {
  const pos = positionFromLatLonDepth(lat, lon, depthM);
  const orient = headingToQuaternion(headingDeg, 0);
  const parts = [];
  const colorMap = {
    glider: '#38bdf8', auv: '#a78bfa', vessel: '#f59e0b', argo: '#34d399'
  };
  const col = Cesium.Color.fromCssColorString(colorMap[type] || '#38bdf8');

  if (type === 'glider') {
    // Elongated body + wings + tail
    parts.push(viewer.entities.add({
      id: `${id}_body`,
      position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(3.5, 0.6, 0.5), material: col.withAlpha(0.95), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.5) }
    }));
    parts.push(viewer.entities.add({
      id: `${id}_wing_l`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(0.8, 2.0, 0.08), material: col.withAlpha(0.7) }
    }));
    parts.push(viewer.entities.add({
      id: `${id}_tail`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(0.5, 0.02, 0.8), material: col.withAlpha(0.8) }
    }));
  } else if (type === 'auv') {
    parts.push(viewer.entities.add({
      id: `${id}_body`, position: pos, orientation: orient,
      cylinder: { length: 4.0, topRadius: 0.35, bottomRadius: 0.45, material: col.withAlpha(0.95), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.4) }
    }));
    parts.push(viewer.entities.add({
      id: `${id}_fin`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(0.3, 1.2, 0.06), material: col.withAlpha(0.7) }
    }));
  } else if (type === 'vessel') {
    parts.push(viewer.entities.add({
      id: `${id}_hull`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(12, 3, 2), material: col.withAlpha(0.95), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.4) }
    }));
    parts.push(viewer.entities.add({
      id: `${id}_super`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(4, 2.5, 3), material: Cesium.Color.fromCssColorString('#94a3b8').withAlpha(0.9) }
    }));
  } else if (type === 'argo') {
    parts.push(viewer.entities.add({
      id: `${id}_float`, position: pos, orientation: orient,
      cylinder: { length: 2.0, topRadius: 0.25, bottomRadius: 0.25, material: col.withAlpha(0.9), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.4) }
    }));
  }

  const lblText = type === 'argo' ? `${label}\nPASSIVE / NON-STEERABLE` : `${label}\n${status || ''}`;
  parts.push(viewer.entities.add({
    id: `${id}_label`, position: pos,
    label: {
      text: lblText, font: 'bold 10px IBM Plex Mono',
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, type === 'vessel' ? -30 : -22),
      fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3,
      scale: 0.9, disableDepthTestDistance: Number.POSITIVE_INFINITY
    }
  }));

  return parts;
}

function updateInstrumentParts(parts, lat, lon, depthM, headingDeg, pitchDeg) {
  const pos = positionFromLatLonDepth(lat, lon, depthM);
  const orient = headingToQuaternion(headingDeg, pitchDeg || 0);
  parts.forEach(p => {
    if (p.position) p.position = pos;
    if (p.orientation) p.orientation = orient;
  });
}

function removeEntityGroup(parts) {
  parts.forEach(p => { try { viewer.entities.remove(p); } catch (_) {} });
}

// ─── Globe init ──────────────────────────────────────────────────────────────

async function initMissionGlobe() {
  const token = (typeof window !== 'undefined' && window.CESIUM_ION_TOKEN) || '';
  if (token && token !== 'demo_token') Cesium.Ion.defaultAccessToken = token;

  viewer = new Cesium.Viewer('cesiumContainer', {
    terrainProvider: Cesium.createWorldTerrain ? Cesium.createWorldTerrain() : new Cesium.EllipsoidTerrainProvider(),
    animation: false, baseLayerPicker: false, fullscreenButton: false,
    geocoder: false, homeButton: false, infoBox: false,
    sceneModePicker: false, selectionIndicator: false, timeline: false, navigationHelpButton: false
  });
  viewer.scene.globe.depthTestAgainstTerrain = true;

  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(88.7, 15.4, 1800000),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(-55), roll: 0 },
    duration: 1.5
  });

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction(async (click) => {
    const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
    if (cartesian) {
      const c = Cesium.Cartographic.fromCartesian(cartesian);
      await loadAdaptiveMissionForLocation(Cesium.Math.toDegrees(c.latitude), Cesium.Math.toDegrees(c.longitude));
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  buildPhaseTimeline();
  await loadAdaptiveMissionForLocation(15.4, 88.7);
}

function clearMissionGlobe() {
  missionEntities.forEach(e => { try { viewer.entities.remove(e); } catch (_) {} });
  missionEntities = [];
  Object.keys(instrumentEntities).forEach(k => {
    removeEntityGroup(instrumentEntities[k]);
    delete instrumentEntities[k];
  });
}

// ─── Current field arrows ────────────────────────────────────────────────────

function renderCurrentField(field) {
  if (!field || !field.length) return;
  field.forEach((pt, idx) => {
    const speed = pt.speed_mps || 0;
    const scale = Math.min(80000, 40000 + speed * 120000);
    const dirRad = Cesium.Math.toRadians(pt.direction_deg || 0);
    const endLat = pt.latitude + (Math.sin(dirRad) * scale / 111320);
    const endLon = pt.longitude + (Math.cos(dirRad) * scale / (111320 * Math.cos(Cesium.Math.toRadians(pt.latitude))));
    const alpha = Math.min(0.95, 0.3 + speed * 1.2);
    const ent = viewer.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArrayHeights([
          pt.longitude, pt.latitude, -Math.min(pt.depth_m || 0, 1),
          endLon, endLat, -Math.min(pt.depth_m || 0, 1)
        ]),
        width: Math.max(2, speed * 8),
        material: Cesium.Color.fromCssColorString('#3fe0c5').withAlpha(alpha)
      }
    });
    missionEntities.push(ent);
  });
}

// ─── Gap target ──────────────────────────────────────────────────────────────

function renderGapTarget(gap) {
  const ent = viewer.entities.add({
    position: positionFromLatLonDepth(gap.latitude, gap.longitude, 0),
    ellipse: {
      semiMajorAxis: 120000, semiMinorAxis: 120000, height: 0,
      material: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.2),
      outline: true, outlineColor: Cesium.Color.fromCssColorString('#f59e0b'), outlineWidth: 3
    },
    label: {
      text: `GAP TARGET\n${gap.latitude}°N ${gap.longitude}°E\nDepth ${gap.depth_m}m | Priority ${gap.priority_score}%`,
      font: 'bold 11px IBM Plex Mono', style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -40),
      fillColor: Cesium.Color.fromCssColorString('#f59e0b'),
      outlineColor: Cesium.Color.BLACK, outlineWidth: 3
    }
  });
  missionEntities.push(ent);
}

// ─── Route polylines ─────────────────────────────────────────────────────────

function renderRoutePolyline(waypoints, color, width, glow, id) {
  if (!waypoints || waypoints.length < 2) return null;
  const coords = [];
  waypoints.forEach(w => {
    const d = w.depth_m || 0;
    coords.push(w.longitude, w.latitude, d <= 0 ? 0 : -Math.abs(d));
  });
  const mat = glow
    ? new Cesium.PolylineGlowMaterialProperty({ glowPower: 0.3, color: Cesium.Color.fromCssColorString(color) })
    : Cesium.Color.fromCssColorString(color).withAlpha(0.5);
  const ent = viewer.entities.add({
    id: id || undefined,
    polyline: { positions: Cesium.Cartesian3.fromDegreesArrayHeights(coords), width: width || 3, material: mat }
  });
  missionEntities.push(ent);
  return ent;
}

// ─── Render all fleet instruments ────────────────────────────────────────────

function renderFleetInstruments(candidates, selectedId) {
  candidates.forEach(c => {
    const id = c.instrument_id;
    const isRejected = !c.feasible;
    const isSelected = id === selectedId;
    const parts = createInstrumentModel(
      viewer, id, c.platform_type,
      c.latitude, c.longitude, c.platform_type === 'vessel' ? 0 : 5,
      45, c.name,
      isRejected ? 'REJECTED' : (isSelected ? 'SELECTED' : `${c.distance_to_target_km} km`)
    );
    if (isRejected) {
      parts.forEach(p => {
        if (p.box) p.box.material = Cesium.Color.fromCssColorString('#ef4444').withAlpha(0.4);
        if (p.cylinder) p.cylinder.material = Cesium.Color.fromCssColorString('#ef4444').withAlpha(0.4);
      });
    }
    instrumentEntities[id] = parts;
  });
}

// ─── UI rendering ────────────────────────────────────────────────────────────

function renderMissionPlanUI(plan) {
  const gap = plan.target_gap || {};
  const winner = plan.selected_winner || {};
  const allCandidates = plan.all_candidates || [];

  document.getElementById('gapBadge').textContent = `PRIORITY ${gap.priority_score || '—'} / 100`;
  document.getElementById('gapCoords').textContent = `${gap.latitude}° N, ${gap.longitude}° E`;
  document.getElementById('gapDepth').textContent = `${gap.depth_m || 500} m`;
  document.getElementById('gapTempRes').textContent = gap.residual_mean != null ? `+${gap.residual_mean.toFixed(2)} °C` : '—';
  document.getElementById('gapAge').textContent = gap.observation_age_hours != null ? `${(gap.observation_age_hours / 24).toFixed(1)} days` : '—';
  document.getElementById('gapDist').textContent = gap.nearest_observation_km != null ? `${gap.nearest_observation_km} km` : '—';

  const listEl = document.getElementById('candidateList');
  listEl.innerHTML = allCandidates.map(c => {
    const checks = c.feasibility_checks || {};
    const checkHtml = Object.values(checks).map(ch =>
      `<span class="c-check ${ch.passed ? 'pass' : 'fail'}">${ch.passed ? '✓' : '✕'} ${ch.label}</span>`
    ).join('');
    const cls = !c.feasible ? 'rejected' : (winner.instrument_id === c.instrument_id ? 'selected' : '');
    const badge = !c.feasible ? '<span class="badge red">REJECTED</span>'
      : (winner.instrument_id === c.instrument_id ? '<span class="badge green">SELECTED</span>' : '<span class="badge blue">CANDIDATE</span>');
    return `<div class="candidate-item ${cls}">
      <div class="c-name"><span>${c.name}</span>${badge}</div>
      <div style="font-size:10px;color:var(--text-dim);">${c.platform_type.toUpperCase()} | ${c.distance_to_target_km} km | Max ${c.maximum_depth_m}m | Batt ${c.battery_percent}%</div>
      <div class="candidate-checks">${checkHtml}</div>
      ${c.rejection_reason ? `<div style="color:#ef4444;font-size:9px;margin-top:3px;">${c.rejection_reason}</div>` : ''}
    </div>`;
  }).join('');

  if (winner && winner.route_details) {
    const route = winner.route_details;
    const energy = winner.energy_details || {};
    document.getElementById('mPlatform').textContent = winner.name || '—';
    document.getElementById('mDist').textContent = `${route.direct_distance_km} km`;
    document.getElementById('mDuration').textContent = `${route.estimated_duration_hours} h`;
    document.getElementById('mEnergy').textContent = `${energy.energy_required_percent || '—'}%`;
    document.getElementById('mReserve').textContent = `${energy.energy_remaining_percent || '—'}% (> ${energy.safety_reserve_percent || 15}% req)`;
    document.getElementById('feasBadge').textContent = `FEASIBLE (${winner.mission_score})`;
    renderDepthCapabilityBar(winner.platform_type === 'glider' ? 1000 : (winner.maximum_depth_m || 1000), gap.depth_m || 500, true);
  }

  const eig = winner.information_gain_details || {};
  document.getElementById('gapBefore').textContent = `${gap.priority_score || '—'}%`;
  document.getElementById('gapAfter').textContent = `${eig.posterior_uncertainty_percent || '—'}%`;
  document.getElementById('gainVal').textContent = eig.expected_information_gain_percent != null ? `+${eig.expected_information_gain_percent}%` : '—';

  if (plan.fleet_provenance) {
    document.getElementById('fleetProvenanceBadge').textContent = plan.fleet_provenance;
  }
}

function renderDepthCapabilityBar(maxDepth, targetDepth, feasible) {
  const el = document.getElementById('depthCapabilityBar');
  const marks = [0, 100, 250, 500, 750, 1000].filter(d => d <= Math.max(maxDepth, targetDepth, 1000));
  el.innerHTML = `<div style="font-weight:700;color:var(--cyan);margin-bottom:4px;">DEPTH CAPABILITY</div>` +
    marks.map(d => {
      let extra = '';
      if (d === targetDepth) extra = ' <span style="color:var(--accent);">← TARGET</span>';
      if (d === maxDepth) extra = ' <span style="color:var(--cyan);">← MAX DEPTH</span>';
      if (!feasible && d === maxDepth && targetDepth > maxDepth) extra = ' <span style="color:var(--red);">✕ IMPOSSIBLE</span>';
      return `<div class="dc-row">${d} m${extra}</div>`;
    }).join('');
}

function buildPhaseTimeline() {
  const phases = [
    'GAP DETECTED', 'FLEET SEARCH', 'FEASIBILITY', 'SELECTED', 'ROUTE OPT',
    'DEPLOY', 'TRANSIT', 'CURRENT ADJ', 'DESCENT', 'APPROACH',
    'TARGET', 'SAMPLING', 'ACQUIRED', 'REASSESS'
  ];
  const el = document.getElementById('phaseTimeline');
  el.innerHTML = phases.map((p, i) => `<span class="phase-chip" data-phase="${i}">${String(i + 1).padStart(2, '0')} ${p}</span>`).join('');
}

function setActivePhase(index) {
  document.querySelectorAll('.phase-chip').forEach((chip, i) => {
    chip.classList.toggle('active', i === index);
    chip.classList.toggle('done', i < index);
  });
}

// ─── Globe overlay (pre-play) ────────────────────────────────────────────────

function renderMissionGlobeOverlay(plan) {
  if (!viewer) return;
  clearMissionGlobe();

  const gap = plan.target_gap || {};
  const winner = plan.selected_winner || {};
  const route = winner.route_details || {};

  renderGapTarget(gap);
  renderFleetInstruments(plan.all_candidates || [], winner.instrument_id);
  renderCurrentField(plan.current_field || route.current_field || []);

  if (route.selected_route) {
    renderRoutePolyline(route.selected_route.waypoints, '#3fe0c5', 4, true, 'selected_route');
  } else if (route.waypoints) {
    renderRoutePolyline(route.waypoints, '#3fe0c5', 4, true, 'selected_route');
  }
}

// ─── Profile chart ───────────────────────────────────────────────────────────

const profilePoints = [];

function resetProfileChart() {
  profilePoints.length = 0;
  drawProfileChart();
}

function addProfilePoint(depth, temp, sal) {
  profilePoints.push({ depth, temp, sal });
  drawProfileChart();
}

function drawProfileChart() {
  const canvas = document.getElementById('profileCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = '#11273c';
  ctx.fillRect(0, 0, w, h);

  // Axes
  ctx.strokeStyle = 'rgba(255,255,255,0.2)'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(50, 10); ctx.lineTo(50, h - 20); ctx.lineTo(w - 10, h - 20); ctx.stroke();
  ctx.fillStyle = '#94a3b8'; ctx.font = '9px IBM Plex Mono';
  ctx.fillText('Depth (m)', 4, h / 2);
  ctx.fillText('T (°C)', w / 2 - 20, h - 6);

  if (!profilePoints.length) {
    ctx.fillStyle = '#64748b'; ctx.fillText('Awaiting sampling...', w / 2 - 50, h / 2);
    return;
  }

  const maxDepth = Math.max(...profilePoints.map(p => p.depth), 1000);
  const temps = profilePoints.map(p => p.temp);
  const minT = Math.min(...temps) - 1, maxT = Math.max(...temps) + 1;

  profilePoints.forEach((p, i) => {
    const x = 50 + ((p.temp - minT) / (maxT - minT)) * (w - 70);
    const y = 10 + (p.depth / maxDepth) * (h - 40);
    ctx.fillStyle = '#38bdf8';
    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
    if (i > 0) {
      const prev = profilePoints[i - 1];
      const px = 50 + ((prev.temp - minT) / (maxT - minT)) * (w - 70);
      const py = 10 + (prev.depth / maxDepth) * (h - 40);
      ctx.strokeStyle = '#3fe0c5'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke();
    }
    ctx.fillStyle = '#94a3b8'; ctx.font = '8px IBM Plex Mono';
    ctx.fillText(`${p.depth}m`, x + 6, y + 3);
  });
}

// ─── Water column overlay ────────────────────────────────────────────────────

function updateWaterColumn(depthM, sample) {
  const overlay = document.getElementById('waterColumnOverlay');
  overlay.classList.remove('hidden');
  const depths = [0, 100, 250, 500, 1000];
  document.getElementById('wcRuler').innerHTML = depths.map(d =>
    `<div class="${Math.abs(d - depthM) < 50 ? 'active-depth' : ''}">${d === 0 ? 'SURFACE' : d + ' m'}${d === depthM ? ' ← NOW' : ''}</div>`
  ).join('<div style="color:var(--cyan);text-align:center;">↓</div>');
  if (sample) {
    const sim = sample.simulated ? ' <span style="color:#f59e0b;">(SIMULATED)</span>' : '';
    document.getElementById('wcSampleReadout').innerHTML =
      `<div style="color:var(--accent);font-weight:700;">${depthM} m</div>
       TEMP ${sample.temperature_c} °C<br>SALINITY ${sample.salinity_psu} PSU<br>PRESSURE ${sample.pressure_dbar} dbar${sim}`;
  }
}

function hideWaterColumn() {
  document.getElementById('waterColumnOverlay').classList.add('hidden');
}

// ─── Mission Playback Engine ─────────────────────────────────────────────────

class MissionPlayback {
  constructor(sim) {
    this.sim = sim;
    this.frames = sim.trajectory_frames || [];
    this.phases = sim.mission_phases || [];
    this.sampling = sim.depth_sampling_sequence || [];
    this.running = false;
    this.paused = false;
    this.frameIdx = 0;
    this.speed = 1;
    this.tickMs = 120;
    this.vehicleParts = null;
    this.routeEntities = [];
    this.scannerEnt = null;
    this.lastTs = 0;
    this.phaseIdx = 0;
    this.prePhaseDone = false;
    this.prePhaseStep = 0;
    this.totalFrames = this.frames.length + this.sampling.length * 8 + 60;
    this.onFrame = null;
  }

  async start() {
    this.running = true;
    this.paused = false;
    this.frameIdx = 0;
    this.prePhaseStep = 0;
    this.prePhaseDone = false;
    resetProfileChart();
    hideWaterColumn();
    document.getElementById('gapHeatmapOverlay').classList.add('hidden');
    clearMissionGlobe();

    const gap = this.sim.target_gap;
    const winner = this.sim.selected_platform;
    renderGapTarget(gap);
    renderCurrentField(this.sim.routing?.current_field || []);

    // Pre-animation phases: scanner → candidates → routes
    await this.runPreAnimation(gap, winner);
    this.animate();
  }

  async runPreAnimation(gap, winner) {
    setActivePhase(0);
    document.getElementById('simPhase').textContent = '01 GAP DETECTED';
    await this.wait(800 / this.speed);

    // Scanner ring animation
    let scanRadius = 50000;
    this.scannerEnt = viewer.entities.add({
      position: positionFromLatLonDepth(gap.latitude, gap.longitude, 0),
      ellipse: {
        semiMajorAxis: new Cesium.CallbackProperty(() => scanRadius, false),
        semiMinorAxis: new Cesium.CallbackProperty(() => scanRadius, false),
        height: 0,
        material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.15),
        outline: true, outlineColor: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.6)
      }
    });
    missionEntities.push(this.scannerEnt);
    for (let i = 0; i < 12; i++) {
      scanRadius += 80000;
      setActivePhase(1);
      document.getElementById('simPhase').textContent = '02 FLEET SEARCH';
      await this.wait(200 / this.speed);
    }
    viewer.entities.remove(this.scannerEnt);

    // Show all candidates
    setActivePhase(2);
    document.getElementById('simPhase').textContent = '03 FEASIBILITY CHECK';
    renderFleetInstruments(this.sim.all_candidates || [], null);
    await this.wait(1200 / this.speed);

    // Highlight rejections then selection
    const selId = winner.instrument_id;
    Object.keys(instrumentEntities).forEach(id => {
      if (id !== selId) {
        const c = (this.sim.all_candidates || []).find(x => x.instrument_id === id);
        if (c && !c.feasible) {
          instrumentEntities[id].forEach(p => {
            if (p.box) p.box.material = Cesium.Color.fromCssColorString('#ef4444').withAlpha(0.3);
            if (p.cylinder) p.cylinder.material = Cesium.Color.fromCssColorString('#ef4444').withAlpha(0.3);
          });
        }
      }
    });
    await this.wait(800 / this.speed);

    setActivePhase(3);
    document.getElementById('simPhase').textContent = '04 INSTRUMENT SELECTED';
    renderFleetInstruments(this.sim.all_candidates || [], selId);
    await this.wait(600 / this.speed);

    // Route planning animation
    setActivePhase(4);
    document.getElementById('simPhase').textContent = '05 ROUTE OPTIMIZED';
    const routing = this.sim.routing || {};
    if (routing.direct_route) renderRoutePolyline(routing.direct_route.waypoints, '#64748b', 2, false, 'direct');
    await this.wait(700 / this.speed);
    (routing.candidate_routes || []).forEach((r, i) => {
      renderRoutePolyline(r.waypoints, ['#818cf8', '#a78bfa', '#c084fc'][i] || '#818cf8', 2, false, `cand_${i}`);
    });
    await this.wait(900 / this.speed);
    if (routing.selected_route) {
      renderRoutePolyline(routing.selected_route.waypoints, '#3fe0c5', 5, true, 'optimal');
    }
    await this.wait(600 / this.speed);

    // Create vehicle at start
    const startWp = (routing.selected_route || {}).waypoints?.[0] || this.frames[0];
    if (startWp) {
      this.vehicleParts = createInstrumentModel(
        viewer, 'vehicle', winner.platform_type,
        startWp.latitude, startWp.longitude, 0,
        startWp.heading_deg || 0, winner.name, 'DEPLOYING'
      );
    }
    this.prePhaseDone = true;
  }

  wait(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  animate(ts) {
    if (!this.running) return;
    if (this.paused) { requestAnimationFrame(t => this.animate(t)); return; }

    if (!this.prePhaseDone) { requestAnimationFrame(t => this.animate(t)); return; }

    const elapsed = ts - this.lastTs;
    if (elapsed < this.tickMs / this.speed) {
      requestAnimationFrame(t => this.animate(t));
      return;
    }
    this.lastTs = ts;

    if (this.frameIdx < this.frames.length) {
      this.updateTransitFrame(this.frames[this.frameIdx]);
      this.frameIdx++;
    } else {
      const sampleIdx = this.frameIdx - this.frames.length;
      if (sampleIdx < this.sampling.length) {
        this.updateSamplingFrame(this.sampling[sampleIdx], sampleIdx);
        this.frameIdx += 8;
      } else if (sampleIdx < this.sampling.length + 5) {
        this.showGapReduction();
        this.frameIdx += 5;
      } else {
        this.finish();
        return;
      }
    }

    const progress = Math.min(1000, Math.floor((this.frameIdx / this.totalFrames) * 1000));
    document.getElementById('timelineScrubber').value = progress;
    requestAnimationFrame(t => this.animate(t));
  }

  updateTransitFrame(frame) {
    const winner = this.sim.selected_platform;
    const phaseMap = {
      TRANSIT: 6, CURRENT_ADJUSTMENT: 7, DESCENT: 8,
      TARGET_APPROACH: 9, TARGET_REACHED: 10
    };
    const pIdx = phaseMap[frame.phase] || 6;
    setActivePhase(pIdx);

    if (this.vehicleParts) {
      updateInstrumentParts(this.vehicleParts, frame.latitude, frame.longitude, frame.depth_m, frame.heading_deg, frame.pitch_deg);
    }

    document.getElementById('simPhase').textContent = this.phases[pIdx]?.label || frame.phase;
    document.getElementById('simTime').textContent = `T + ${frame.elapsed_hours} h`;
    document.getElementById('simDepth').textContent = `${frame.depth_m.toFixed(0)} m`;
    document.getElementById('simHeading').textContent = `${frame.heading_deg.toFixed(0)}°`;
    document.getElementById('simGroundTrack').textContent = `${frame.ground_track_deg.toFixed(0)}°`;
    document.getElementById('simDragVal').textContent = `${frame.current_speed_mps.toFixed(2)} m/s → ${frame.current_direction_deg.toFixed(0)}°`;
    document.getElementById('simBattVal').textContent = `${frame.battery_percent.toFixed(1)}%`;
    document.getElementById('simBattFill').style.width = `${frame.battery_percent}%`;
    document.getElementById('simStatusBadge').textContent = frame.phase;
    document.getElementById('simStatusBadge').className = 'badge blue';

    const route = winner.route_details?.selected_route || winner.route_details || {};
    const remDist = Math.max(0, (route.distance_km || 0) * (1 - this.frameIdx / Math.max(1, this.frames.length)));
    document.getElementById('simDistRem').textContent = `${remDist.toFixed(1)} km`;

    if (frame.depth_m > 0) updateWaterColumn(frame.depth_m, null);
    else hideWaterColumn();

    // Camera director
    if (frame.depth_m > 50) {
      viewer.camera.lookAt(
        positionFromLatLonDepth(frame.latitude, frame.longitude, frame.depth_m),
        new Cesium.HeadingPitchRange(Cesium.Math.toRadians(frame.heading_deg + 90), Cesium.Math.toRadians(-20), 800)
      );
    } else if (this.frameIdx % 5 === 0) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(frame.longitude, frame.latitude, 80000),
        orientation: { heading: Cesium.Math.toRadians(frame.heading_deg), pitch: Cesium.Math.toRadians(-35), roll: 0 },
        duration: 0.5
      });
    }
  }

  updateSamplingFrame(sample, idx) {
    setActivePhase(11);
    document.getElementById('simPhase').textContent = '12 SENSOR SAMPLING';
    document.getElementById('simStatusBadge').textContent = 'SAMPLING';
    document.getElementById('simDepth').textContent = `${sample.depth_m} m`;

    updateWaterColumn(sample.depth_m, sample);
    addProfilePoint(sample.depth_m, sample.temperature_c, sample.salinity_psu);

    const el = document.getElementById(`s_${sample.depth_m}`);
    if (el) {
      const sim = sample.simulated ? ' (SIM)' : '';
      el.innerHTML = `<span style="color:#34d399;font-weight:700;">✓ T=${sample.temperature_c}°C S=${sample.salinity_psu}${sim}</span>`;
    }

    if (this.vehicleParts) {
      const target = this.sim.target;
      updateInstrumentParts(this.vehicleParts, target.latitude, target.longitude, sample.depth_m, 0, -10);
    }

    viewer.camera.lookAt(
      positionFromLatLonDepth(this.sim.target.latitude, this.sim.target.longitude, sample.depth_m),
      new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-15), 600)
    );
  }

  showGapReduction() {
    setActivePhase(13);
    document.getElementById('simPhase').textContent = '14 INFORMATION GAP REASSESSED';
    const before = this.sim.before_simulation.information_gap_percent;
    const after = this.sim.after_simulation.information_gap_percent;
    document.getElementById('gapBefore').textContent = `${before}%`;
    document.getElementById('gapAfter').textContent = `${after}%`;
    document.getElementById('gainVal').textContent = `+${this.sim.scientific_payoff.expected_information_gain_percent}%`;

    const overlay = document.getElementById('gapHeatmapOverlay');
    overlay.classList.remove('hidden');
    document.getElementById('gapHeatBefore').querySelector('span').textContent = `${before}%`;
    document.getElementById('gapHeatAfter').querySelector('span').textContent = `${after}%`;

    // Visual gap region color shift
    const gap = this.sim.target_gap;
    const heatEnt = viewer.entities.add({
      position: positionFromLatLonDepth(gap.latitude, gap.longitude, 0),
      ellipse: {
        semiMajorAxis: 100000, semiMinorAxis: 100000, height: 0,
        material: Cesium.Color.fromCssColorString('#34d399').withAlpha(0.25),
        outline: true, outlineColor: Cesium.Color.fromCssColorString('#34d399')
      }
    });
    missionEntities.push(heatEnt);

    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 600000),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
      duration: 1.5
    });
  }

  finish() {
    this.running = false;
    document.getElementById('simStatusBadge').textContent = 'COMPLETE';
    document.getElementById('simStatusBadge').className = 'badge green';
    document.getElementById('btnPlayPause').textContent = '▶';
    setActivePhase(13);
  }

  pause() { this.paused = true; document.getElementById('btnPlayPause').textContent = '▶'; }
  resume() { this.paused = false; this.lastTs = 0; document.getElementById('btnPlayPause').textContent = '⏸'; requestAnimationFrame(t => this.animate(t)); }
  restart() { this.running = false; startMissionSimulation(); }
}

// ─── Simulation launch ───────────────────────────────────────────────────────

async function loadAdaptiveMissionForLocation(lat, lon, depth = 500.0) {
  try {
    const res = await fetch(apiUrl(`/api/adaptive/plan?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}&depth=${depth}&platform=glider`));
    if (!res.ok) return;
    currentMissionData = await res.json();
    renderMissionPlanUI(currentMissionData);
    renderMissionGlobeOverlay(currentMissionData);
  } catch (e) {
    console.warn('Failed to load mission plan:', e);
  }
}

async function startMissionSimulation() {
  if (!currentMissionData || !currentMissionData.target_gap) return;
  const gap = currentMissionData.target_gap;
  const btn = document.getElementById('btnPlayMission');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(apiUrl(`/api/adaptive/simulate?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${(gap.variables && gap.variables[0]) || 'temperature'}`));
    if (!res.ok) return;
    simulationData = await res.json();
    if (simulationData.status === 'NO_FEASIBLE_MISSION') {
      document.getElementById('simStatusBadge').textContent = 'NO FEASIBLE MISSION';
      return;
    }

    // Build dive sequence UI
    const diveEl = document.getElementById('diveSequence');
    diveEl.innerHTML = (simulationData.depth_sampling_sequence || []).map(s =>
      `<div class="metric-row"><span>${s.depth_m} m</span><span id="s_${s.depth_m}" style="color:var(--text-dim);">⏳ Pending</span></div>`
    ).join('');

    const energy = simulationData.energy_timeline || {};
    document.getElementById('simBattVal').textContent = `${energy.initial_battery_percent}%`;
    document.getElementById('simBattFill').style.width = `${energy.initial_battery_percent}%`;
    document.getElementById('simSafetyReserve').textContent = `${energy.safety_reserve_percent}%`;

    playback = new MissionPlayback(simulationData);
    document.getElementById('btnPlayPause').textContent = '⏸';
    await playback.start();
  } catch (e) {
    console.warn('Simulation playback error:', e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ─── Playback controls ───────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initMissionGlobe();

  document.getElementById('btnPlayMission').onclick = startMissionSimulation;

  document.getElementById('btnPlayPause').onclick = () => {
    if (!playback) { startMissionSimulation(); return; }
    if (playback.paused) playback.resume();
    else playback.pause();
  };

  document.getElementById('btnRestart').onclick = () => {
    if (playback) playback.restart();
    else startMissionSimulation();
  };

  document.querySelectorAll('.speed-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (playback) playback.speed = parseFloat(btn.dataset.speed);
    };
  });

  document.getElementById('timelineScrubber').oninput = (e) => {
    if (!playback || !playback.frames.length) return;
    const ratio = e.target.value / 1000;
    playback.frameIdx = Math.floor(ratio * playback.frames.length);
    playback.paused = true;
    document.getElementById('btnPlayPause').textContent = '▶';
    if (playback.frames[playback.frameIdx]) playback.updateTransitFrame(playback.frames[playback.frameIdx]);
  };
});
