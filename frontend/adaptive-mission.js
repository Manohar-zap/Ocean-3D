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

// ─── Canvas Badge Billboard Generator (Overview Scale Visibility) ─────────

function generateInstrumentBadgeCanvas(id, ptype, name, battPct, rangeKm, isSelected, isRejected, isPassive) {
  const canvas = document.createElement('canvas');
  canvas.width = 160;
  canvas.height = 72;
  const ctx = canvas.getContext('2d');

  let borderColor = '#38bdf8'; // cyan
  let bgColor = 'rgba(7, 20, 34, 0.92)';
  let tagText = 'CANDIDATE';
  let tagColor = '#38bdf8';

  if (isSelected) {
    borderColor = '#f59e0b'; // gold
    bgColor = 'rgba(245, 158, 11, 0.25)';
    tagText = 'SELECTED';
    tagColor = '#f59e0b';
  } else if (isRejected) {
    borderColor = '#ef4444'; // red
    bgColor = 'rgba(239, 68, 68, 0.2)';
    tagText = 'REJECTED';
    tagColor = '#ef4444';
  } else if (isPassive) {
    borderColor = '#34d399'; // green
    tagText = 'PASSIVE';
    tagColor = '#34d399';
  }

  // Card background
  ctx.fillStyle = bgColor;
  ctx.strokeStyle = borderColor;
  ctx.lineWidth = 3;
  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(4, 4, 152, 64, 8);
  } else {
    ctx.rect(4, 4, 152, 64);
  }
  ctx.fill();
  ctx.stroke();

  // Status tag badge
  ctx.fillStyle = tagColor;
  ctx.font = 'bold 10px "IBM Plex Mono", monospace';
  ctx.fillText(tagText, 12, 18);

  // Instrument ID
  ctx.fillStyle = '#ffffff';
  ctx.font = 'bold 13px "IBM Plex Mono", monospace';
  ctx.fillText(id, 12, 36);

  // Metrics subtext
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px "IBM Plex Mono", monospace';
  if (isPassive) {
    ctx.fillText('PASSIVE DRIFT FLOAT', 12, 54);
  } else if (ptype === 'vessel') {
    ctx.fillText('RESEARCH SHIP', 12, 54);
  } else {
    ctx.fillText(`${battPct || 80}% BATT • ${rangeKm || 400}km`, 12, 54);
  }

  return canvas.toDataURL();
}

// ─── Instrument 3D Procedural Models & Two-Scale Entities ─────────────────

function createInstrumentModel(viewer, cData, isSelected, isRejected, targetGap) {
  const id = cData.instrument_id || 'inst';
  const ptype = cData.platform_type || 'glider';
  const lat = cData.latitude || 0;
  const lon = cData.longitude || 0;
  const depthM = ptype === 'vessel' ? 0 : (cData.depth_m || 10);
  const headingDeg = cData.heading_deg || 45;
  const pos = positionFromLatLonDepth(lat, lon, depthM);
  const orient = headingToQuaternion(headingDeg, 0);
  const parts = [];

  const isPassive = ptype === 'argo' || !cData.controllable;

  let mainColorHex = '#38bdf8'; // glider cyan
  if (ptype === 'auv') mainColorHex = '#a78bfa'; // auv violet
  else if (ptype === 'vessel') mainColorHex = '#f59e0b'; // vessel amber
  else if (ptype === 'argo') mainColorHex = '#34d399'; // float green

  if (isSelected) mainColorHex = '#f59e0b';
  else if (isRejected) mainColorHex = '#ef4444';

  const col = Cesium.Color.fromCssColorString(mainColorHex);

  // 1. High-contrast Overview Badge Billboard (Unmissable at overview scale)
  const badgeUrl = generateInstrumentBadgeCanvas(
    id, ptype, cData.name, cData.battery_percent, cData.max_range_km, isSelected, isRejected, isPassive
  );

  const anchorEnt = viewer.entities.add({
    id: `${id}_anchor`,
    position: pos,
    orientation: orient,
    billboard: {
      image: badgeUrl,
      scale: 0.9,
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      scaleByDistance: new Cesium.NearFarScalar(1e3, 0.8, 5e6, 1.1)
    }
  });
  anchorEnt.candidateData = cData;
  parts.push(anchorEnt);

  // 2. Readable Label
  let labelTag = isSelected ? '★ SELECTED VEHICLE' : (isRejected ? `✕ REJECTED: ${cData.rejection_reason || 'Out of spec'}` : `✓ CANDIDATE (${cData.distance_to_target_km || 0} km)`);
  if (isPassive) labelTag = 'PASSIVE • NON-STEERABLE DRIFT FLOAT';

  let subText = `${ptype.toUpperCase()} • ${cData.battery_percent || 80}% BATT • ${cData.max_range_km || 400}km RANGE`;
  if (isPassive) subText = 'PROFILING ARGO FLOAT';
  else if (ptype === 'vessel') subText = 'ORV RESEARCH SHIP';

  const lblText = `${id}\n${subText}\n${labelTag}`;

  const lblEnt = viewer.entities.add({
    id: `${id}_label`,
    position: pos,
    label: {
      text: lblText,
      font: 'bold 11px "IBM Plex Mono", monospace',
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, ptype === 'vessel' ? -55 : -45),
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 4,
      showBackground: true,
      backgroundColor: Cesium.Color.fromCssColorString('rgba(7, 20, 34, 0.88)'),
      backgroundPadding: new Cesium.Cartesian2(8, 4),
      scaleByDistance: new Cesium.NearFarScalar(1e3, 0.9, 5e6, 1.05)
    }
  });
  lblEnt.candidateData = cData;
  parts.push(lblEnt);

  // 3. Zoomed 3D Procedural Geometry
  if (ptype === 'glider') {
    // Fuselage Body
    const bodyEnt = viewer.entities.add({
      id: `${id}_body`, position: pos, orientation: orient,
      cylinder: { length: 200, topRadius: 15, bottomRadius: 15, material: col.withAlpha(0.9), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.6) }
    });
    bodyEnt.candidateData = cData; parts.push(bodyEnt);

    // Nose Cone
    const noseEnt = viewer.entities.add({
      id: `${id}_nose`, position: pos, orientation: orient,
      cylinder: { length: 50, topRadius: 0, bottomRadius: 15, material: col.withAlpha(0.95) }
    });
    noseEnt.candidateData = cData; parts.push(noseEnt);

    // Swept Wings
    const wingsEnt = viewer.entities.add({
      id: `${id}_wings`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(40, 220, 5), material: col.withAlpha(0.85) }
    });
    wingsEnt.candidateData = cData; parts.push(wingsEnt);

    // Vertical Tail Fin
    const tailEnt = viewer.entities.add({
      id: `${id}_tail`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(30, 6, 60), material: col.withAlpha(0.85) }
    });
    tailEnt.candidateData = cData; parts.push(tailEnt);

    // CTD Sensor Pod
    const sensorEnt = viewer.entities.add({
      id: `${id}_sensor`, position: pos, orientation: orient,
      ellipsoid: { radii: new Cesium.Cartesian3(12, 12, 12), material: Cesium.Color.WHITE.withAlpha(0.9) }
    });
    sensorEnt.candidateData = cData; parts.push(sensorEnt);
  } else if (ptype === 'auv') {
    // Torpedo Body
    const bodyEnt = viewer.entities.add({
      id: `${id}_body`, position: pos, orientation: orient,
      cylinder: { length: 250, topRadius: 20, bottomRadius: 20, material: col.withAlpha(0.9), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.6) }
    });
    bodyEnt.candidateData = cData; parts.push(bodyEnt);

    // Nose Cone
    const noseEnt = viewer.entities.add({
      id: `${id}_nose`, position: pos, orientation: orient,
      cylinder: { length: 60, topRadius: 0, bottomRadius: 20, material: col.withAlpha(0.95) }
    });
    noseEnt.candidateData = cData; parts.push(noseEnt);

    // Stern Fins
    const finV = viewer.entities.add({
      id: `${id}_fin_v`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(30, 8, 100), material: col.withAlpha(0.8) }
    });
    finV.candidateData = cData; parts.push(finV);

    const finH = viewer.entities.add({
      id: `${id}_fin_h`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(30, 100, 8), material: col.withAlpha(0.8) }
    });
    finH.candidateData = cData; parts.push(finH);

    // Ventral Sensor Section
    const sensorEnt = viewer.entities.add({
      id: `${id}_sensor`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(80, 30, 15), material: Cesium.Color.fromCssColorString('#a78bfa').withAlpha(0.85) }
    });
    sensorEnt.candidateData = cData; parts.push(sensorEnt);
  } else if (ptype === 'vessel') {
    // Hull
    const hullEnt = viewer.entities.add({
      id: `${id}_hull`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(500, 100, 50), material: col.withAlpha(0.95), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.6) }
    });
    hullEnt.candidateData = cData; parts.push(hullEnt);

    // Superstructure / Bridge
    const bridgeEnt = viewer.entities.add({
      id: `${id}_bridge`, position: pos, orientation: orient,
      box: { dimensions: new Cesium.Cartesian3(150, 80, 80), material: Cesium.Color.fromCssColorString('#cbd5e1').withAlpha(0.9) }
    });
    bridgeEnt.candidateData = cData; parts.push(bridgeEnt);

    // Mast
    const mastEnt = viewer.entities.add({
      id: `${id}_mast`, position: pos, orientation: orient,
      cylinder: { length: 120, topRadius: 4, bottomRadius: 5, material: Cesium.Color.WHITE.withAlpha(0.9) }
    });
    mastEnt.candidateData = cData; parts.push(mastEnt);
  } else if (ptype === 'argo') {
    // Float Body
    const floatEnt = viewer.entities.add({
      id: `${id}_float`, position: pos, orientation: orient,
      cylinder: { length: 200, topRadius: 15, bottomRadius: 15, material: col.withAlpha(0.9), outline: true, outlineColor: Cesium.Color.WHITE.withAlpha(0.6) }
    });
    floatEnt.candidateData = cData; parts.push(floatEnt);

    // Damping Disc
    const discEnt = viewer.entities.add({
      id: `${id}_disc`, position: pos, orientation: orient,
      cylinder: { length: 8, topRadius: 60, bottomRadius: 60, material: col.withAlpha(0.7) }
    });
    discEnt.candidateData = cData; parts.push(discEnt);

    // Antenna
    const antEnt = viewer.entities.add({
      id: `${id}_antenna`, position: pos, orientation: orient,
      cylinder: { length: 120, topRadius: 3, bottomRadius: 3, material: Cesium.Color.WHITE.withAlpha(0.9) }
    });
    antEnt.candidateData = cData; parts.push(antEnt);
  }

  // 4. Selected Vehicle Emphasis: Glowing Target Polyline & Ring Halo
  if (isSelected && targetGap && targetGap.latitude) {
    const targetPos = positionFromLatLonDepth(targetGap.latitude, targetGap.longitude, 0);

    const targetLineEnt = viewer.entities.add({
      id: `${id}_target_line`,
      polyline: {
        positions: [pos, targetPos],
        width: 4,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.4,
          color: Cesium.Color.fromCssColorString('#f59e0b')
        })
      }
    });
    targetLineEnt.candidateData = cData; parts.push(targetLineEnt);

    const haloEnt = viewer.entities.add({
      id: `${id}_halo`,
      position: pos,
      ellipse: {
        semiMajorAxis: 35000,
        semiMinorAxis: 35000,
        height: 0,
        material: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.2),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#f59e0b'),
        outlineWidth: 3
      }
    });
    haloEnt.candidateData = cData; parts.push(haloEnt);
  }

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

// ─── Instrument Info Modal ────────────────────────────────────────────────

function openInstrumentModal(c) {
  const modal = document.getElementById('instrumentInfoModal');
  if (!modal) return;

  const winnerId = currentMissionData?.selected_winner?.instrument_id;
  const isSelected = c.instrument_id === winnerId;
  const isRejected = !c.feasible;
  const isPassive = c.platform_type === 'argo' || !c.controllable;

  document.getElementById('modalTitle').textContent = `${c.instrument_id} (${c.name || ''})`;

  const badgeEl = document.getElementById('modalStatusBadge');
  if (isSelected) {
    badgeEl.textContent = 'RECOMMENDED WINNER';
    badgeEl.className = 'badge green';
  } else if (isRejected) {
    badgeEl.textContent = 'REJECTED';
    badgeEl.className = 'badge red';
  } else if (isPassive) {
    badgeEl.textContent = 'PASSIVE DRIFT';
    badgeEl.className = 'badge amber';
  } else {
    badgeEl.textContent = 'CANDIDATE';
    badgeEl.className = 'badge blue';
  }

  document.getElementById('mValId').textContent = c.instrument_id;
  document.getElementById('mValType').textContent = (c.platform_type || '').toUpperCase();
  document.getElementById('mValPos').textContent = `${c.latitude.toFixed(2)}° N, ${c.longitude.toFixed(2)}° E`;
  document.getElementById('mValDepthCap').textContent = `${c.maximum_depth_m || 1000} m`;
  document.getElementById('mValRange').textContent = isPassive ? 'N/A (Passive Drift)' : `${c.max_range_km || 400} km`;
  document.getElementById('mValBatt').textContent = `${c.battery_percent}%`;
  document.getElementById('mValSensors').textContent = c.sensors ? c.sensors.join(', ') : 'CTD (Conductivity, Temp, Depth), Dissolved Oxygen';
  document.getElementById('mValCtrl').textContent = c.controllable ? 'YES (Steerable Autonav)' : 'NO (Passive Float)';

  const statusText = isRejected
    ? `REJECTED: ${c.rejection_reason || 'Constraint limit exceeded'}`
    : (isSelected ? 'FEASIBLE & OPTIMAL — Selected for Mission Execution' : 'FEASIBLE CANDIDATE');
  document.getElementById('mValStatus').textContent = statusText;

  modal.classList.remove('hidden');

  // Highlight candidate card in sidebar
  document.querySelectorAll('.candidate-item').forEach(el => {
    if (el.dataset.instrumentId === c.instrument_id) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      el.style.outline = '2px solid var(--accent)';
      setTimeout(() => { el.style.outline = 'none'; }, 2000);
    }
  });
}

// ─── Globe Init ─────────────────────────────────────────────────────────────

async function initMissionGlobe() {
  const token = (typeof window !== 'undefined' && window.CESIUM_ION_TOKEN) || '';
  if (token && token !== 'demo_token') Cesium.Ion.defaultAccessToken = token;

  let baseLayer;
  try {
    baseLayer = new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({
      url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      maximumLevel: 19,
      credit: 'Esri'
    }));
  } catch (e) {
    baseLayer = undefined;
  }

  viewer = new Cesium.Viewer('cesiumContainer', {
    baseLayer: baseLayer,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    animation: false, baseLayerPicker: false, fullscreenButton: false,
    geocoder: false, homeButton: false, infoBox: false,
    sceneModePicker: false, selectionIndicator: false, timeline: false, navigationHelpButton: false
  });
  viewer.scene.globe.depthTestAgainstTerrain = true;

  // Globe picking handler for instrument modal popups
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((click) => {
    const picked = viewer.scene.pick(click.position);
    if (Cesium.defined(picked) && picked.id) {
      let candidate = picked.id.candidateData;
      if (!candidate && typeof picked.id.id === 'string') {
        const parentId = picked.id.id.split('_')[0];
        candidate = (currentMissionData?.all_candidates || []).find(c => c.instrument_id === parentId);
      }
      if (candidate) {
        openInstrumentModal(candidate);
        return;
      }
    }

    const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
    if (cartesian) {
      const c = Cesium.Cartographic.fromCartesian(cartesian);
      loadAdaptiveMissionForLocation(Cesium.Math.toDegrees(c.latitude), Cesium.Math.toDegrees(c.longitude));
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  buildPhaseTimeline();

  const closeBtn = document.getElementById('modalCloseBtn');
  if (closeBtn) {
    closeBtn.onclick = () => {
      const m = document.getElementById('instrumentInfoModal');
      if (m) m.classList.add('hidden');
    };
  }

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

// ─── Current Field Arrows ───────────────────────────────────────────────────

function renderCurrentField(field, targetDepthM, provenance) {
  if (!field || !field.length) return;
  const depth = Math.abs(targetDepthM || (field[0] && field[0].depth_m) || 500);

  field.forEach((pt) => {
    const speed = pt.speed_mps || 0;
    const dirRad = Cesium.Math.toRadians(pt.direction_deg || 0);
    const scale = Math.min(80000, 30000 + speed * 100000);
    const endLat = pt.latitude + (Math.sin(dirRad) * scale / 111320);
    const endLon = pt.longitude + (Math.cos(dirRad) * scale / (111320 * Math.cos(Cesium.Math.toRadians(pt.latitude))));
    const alpha = Math.min(0.95, 0.4 + speed * 1.2);

    const ent = viewer.entities.add({
      polyline: {
        positions: [
          positionFromLatLonDepth(pt.latitude, pt.longitude, depth),
          positionFromLatLonDepth(endLat, endLon, depth)
        ],
        width: Math.max(3, Math.min(8, speed * 12)),
        material: new Cesium.PolylineArrowMaterialProperty(
          Cesium.Color.fromCssColorString('#3fe0c5').withAlpha(alpha)
        )
      }
    });
    missionEntities.push(ent);
  });

  const depthEl = document.getElementById('legDepthVal');
  if (depthEl) depthEl.textContent = `${depth} m`;

  const provEl = document.getElementById('legProvVal');
  if (provEl) {
    const provText = provenance || (field[0] && field[0].provenance) || 'INCOIS MODEL';
    provEl.textContent = provText;
    provEl.className = provText === 'INCOIS MODEL' ? 'badge blue' : 'badge amber';
  }
}

// ─── Gap Target ─────────────────────────────────────────────────────────────

function renderGapTarget(gap) {
  const targetDepth = Math.abs(gap.depth_m || 500);

  // 1. Organic Surface Target Polygon with Cyan Dashed Boundary
  const polyCoords = gap.polygon_coordinates;
  if (polyCoords && Array.isArray(polyCoords) && polyCoords.length >= 3) {
    const flatCoords = [];
    polyCoords.forEach(pt => {
      if (Array.isArray(pt) && pt.length >= 2) flatCoords.push(pt[0], pt[1]);
    });

    if (flatCoords.length >= 6) {
      const cartesianPositions = Cesium.Cartesian3.fromDegreesArray(flatCoords);

      // Shaded Surface Fill
      const polyEnt = viewer.entities.add({
        polygon: {
          hierarchy: cartesianPositions,
          height: 0,
          material: Cesium.Color.fromCssColorString('#0891b2').withAlpha(0.24)
        }
      });
      missionEntities.push(polyEnt);

      // Cyan Dashed Perimeter Boundary Line
      const borderEnt = viewer.entities.add({
        polyline: {
          positions: cartesianPositions,
          width: 3.5,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString('#22d3ee'),
            dashLength: 16.0
          }),
          clampToGround: true
        }
      });
      missionEntities.push(borderEnt);

      // Interior Survey Sampling Grid Dots
      if (gap.survey_points && Array.isArray(gap.survey_points)) {
        gap.survey_points.forEach(sPt => {
          const dotEnt = viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(sPt[0], sPt[1], 0),
            point: {
              pixelSize: 4.5,
              color: Cesium.Color.fromCssColorString('#38bdf8'),
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 1.0
            }
          });
          missionEntities.push(dotEnt);
        });
      }
    }
  } else {
    // Fallback: Surface Target Ellipse Ring
    const entSurface = viewer.entities.add({
      position: positionFromLatLonDepth(gap.latitude, gap.longitude, 0),
      ellipse: {
        semiMajorAxis: 120000, semiMinorAxis: 120000, height: 0,
        material: Cesium.Color.fromCssColorString('#0891b2').withAlpha(0.22),
        outline: true, outlineColor: Cesium.Color.fromCssColorString('#22d3ee'), outlineWidth: 3
      }
    });
    missionEntities.push(entSurface);
  }

  // Surface Survey Zone rendered cleanly without floating text labels

  // 3D Underwater Target Volume at Depth (-500m)
  const targetPos3D = positionFromLatLonDepth(gap.latitude, gap.longitude, targetDepth);
  const ent3D = viewer.entities.add({
    position: targetPos3D,
    cylinder: {
      length: 80,
      topRadius: 25000,
      bottomRadius: 25000,
      material: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.35),
      outline: true,
      outlineColor: Cesium.Color.fromCssColorString('#f59e0b')
    },
    label: {
      text: `🎯 3D TARGET VOLUME\nDepth: ${targetDepth} m`,
      font: 'bold 12px "IBM Plex Mono", monospace',
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      fillColor: Cesium.Color.fromCssColorString('#f59e0b'),
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 4
    }
  });
  missionEntities.push(ent3D);

  // Vertical Guide Column connecting Surface (0m) to Underwater Target (-500m)
  const surfacePos = positionFromLatLonDepth(gap.latitude, gap.longitude, 0);
  const guideCol = viewer.entities.add({
    polyline: {
      positions: [surfacePos, targetPos3D],
      width: 3,
      material: new Cesium.PolylineDashMaterialProperty({
        color: Cesium.Color.fromCssColorString('#f59e0b')
      })
    }
  });
  missionEntities.push(guideCol);
}

// ─── Route Polylines ────────────────────────────────────────────────────────

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

// ─── Render All Fleet Instruments ───────────────────────────────────────────

function renderFleetInstruments(candidates, selectedId, targetGap) {
  candidates.forEach(c => {
    const id = c.instrument_id;
    const isRejected = !c.feasible;
    const isSelected = id === selectedId;

    const parts = createInstrumentModel(viewer, c, isSelected, isRejected, targetGap);
    instrumentEntities[id] = parts;
  });
}

// ─── UI Rendering ───────────────────────────────────────────────────────────

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
    return `<div class="candidate-item ${cls}" data-instrument-id="${c.instrument_id}">
      <div class="c-name"><span>${c.name}</span>${badge}</div>
      <div style="font-size:10px;color:var(--text-dim);">${c.platform_type.toUpperCase()} | ${c.distance_to_target_km} km | Max ${c.maximum_depth_m}m | Batt ${c.battery_percent}%</div>
      <div class="candidate-checks">${checkHtml}</div>
      ${c.rejection_reason ? `<div style="color:#ef4444;font-size:9px;margin-top:3px;">${c.rejection_reason}</div>` : ''}
    </div>`;
  }).join('');

  document.querySelectorAll('.candidate-item').forEach(el => {
    el.onclick = () => {
      const instId = el.dataset.instrumentId;
      const candidate = (allCandidates || []).find(c => c.instrument_id === instId);
      if (candidate) {
        openInstrumentModal(candidate);
        if (viewer) {
          viewer.camera.flyTo({
            destination: positionFromLatLonDepth(candidate.latitude, candidate.longitude, 80000),
            orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
            duration: 1.2
          });
        }
      }
    };
  });

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

  // Populate Route Options Comparison Table
  const routeTable = document.getElementById('routeComparisonTable');
  if (routeTable) {
    const winnerRoute = winner.route_details || {};
    const candidates = winnerRoute.candidate_routes || plan.routing?.candidate_routes || [];
    const direct = winnerRoute.direct_route || plan.routing?.direct_route;
    const selected = winnerRoute.selected_route || plan.routing?.selected_route;

    let html = '';

    if (direct) {
      const assist = direct.current_assistance_mps || 0;
      const oppose = direct.current_opposition_mps || 0;
      const netTag = assist >= oppose
        ? `<span style="color:#34d399;">+${assist.toFixed(2)}m/s ASSIST</span>`
        : `<span style="color:#ef4444;">-${oppose.toFixed(2)}m/s DRAG</span>`;

      html += `
        <div class="route-row direct">
          <div class="route-hdr">
            <span>DIRECT ROUTE (Straight)</span>
            <span class="badge blue">BASELINE</span>
          </div>
          <div class="route-metrics">
            <div>Dist: ${direct.distance_km} km</div>
            <div>Time: ${direct.travel_time_hours} h</div>
            <div>Flow: ${netTag}</div>
            <div>Cost J: ${direct.total_cost}</div>
          </div>
        </div>`;
    }

    candidates.forEach((r, idx) => {
      const isOpt = selected && (r.label === selected.label || r.total_cost === selected.total_cost);
      const assist = r.current_assistance_mps || 0;
      const oppose = r.current_opposition_mps || 0;
      const netTag = assist >= oppose
        ? `<span style="color:#34d399;">+${assist.toFixed(2)}m/s ASSIST</span>`
        : `<span style="color:#ef4444;">-${oppose.toFixed(2)}m/s DRAG</span>`;
      const badge = isOpt
        ? `<span class="badge green">OPTIMAL (SELECTED)</span>`
        : `<span class="badge blue">CANDIDATE ${String.fromCharCode(65 + idx)}</span>`;

      html += `
        <div class="route-row ${isOpt ? 'optimal' : ''}">
          <div class="route-hdr">
            <span>${r.label || 'ROUTE ' + String.fromCharCode(65 + idx)}</span>
            ${badge}
          </div>
          <div class="route-metrics">
            <div>Dist: ${r.distance_km} km</div>
            <div>Time: ${r.travel_time_hours} h</div>
            <div>Flow: ${netTag}</div>
            <div>Risk: ${r.risk_score}</div>
            <div>Energy: ${r.energy_cost}</div>
            <div>Cost J: ${r.total_cost}</div>
          </div>
        </div>`;
    });

    routeTable.innerHTML = html;
  }

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

// ─── Globe Overlay (pre-play) ────────────────────────────────────────────────

function renderMissionGlobeOverlay(plan) {
  if (!viewer) return;
  clearMissionGlobe();

  const gap = plan.target_gap || {};
  const winner = plan.selected_winner || {};
  const route = winner.route_details || {};
  const candidates = plan.all_candidates || [];

  renderGapTarget(gap);
  renderFleetInstruments(candidates, winner.instrument_id, gap);

  // Render current field at target planning depth with explicit provenance
  const fieldDepth = gap.depth_m || plan.current_depth_m || route.current_depth_m || 500;
  const fieldProv = plan.current_data_provenance || route.current_data_provenance || 'INCOIS MODEL';
  renderCurrentField(plan.current_field || route.current_field || [], fieldDepth, fieldProv);

  // Render Direct Route (grey baseline)
  if (route.direct_route) {
    renderRoutePolyline(route.direct_route.waypoints, '#64748b', 2, false, 'direct_route');
  }
  // Render Candidate Routes A, B, C (Indigo, Purple, Violet)
  if (route.candidate_routes) {
    route.candidate_routes.forEach((r, idx) => {
      renderRoutePolyline(r.waypoints, ['#818cf8', '#a78bfa', '#c084fc'][idx] || '#818cf8', 2.5, false, `cand_route_${idx}`);
    });
  }
  // Render Selected Optimal Route (Glowing Cyan)
  if (route.selected_route) {
    renderRoutePolyline(route.selected_route.waypoints, '#3fe0c5', 5, true, 'selected_route');
  } else if (route.waypoints) {
    renderRoutePolyline(route.waypoints, '#3fe0c5', 5, true, 'selected_route');
  }

  // Camera framing: Zoom so ALL candidate instruments and target gap are visible on page load!
  if (candidates.length > 0 && gap.latitude) {
    const pts = [
      Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude),
      ...candidates.map(c => Cesium.Cartesian3.fromDegrees(c.longitude, c.latitude))
    ];
    const bs = Cesium.BoundingSphere.fromPoints(pts);
    viewer.camera.flyToBoundingSphere(bs, {
      duration: 1.5,
      offset: new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(0),
        Cesium.Math.toRadians(-50),
        Math.max(bs.radius * 2.8, 500000)
      )
    });
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
  ctx.fillStyle = '#0c1e30';
  ctx.fillRect(0, 0, w, h);

  // Axes & Grid
  ctx.strokeStyle = 'rgba(255,255,255,0.15)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(50, 15); ctx.lineTo(50, h - 25); ctx.lineTo(w - 15, h - 25); ctx.stroke();

  ctx.fillStyle = '#94a3b8';
  ctx.font = '9px "IBM Plex Mono", monospace';
  ctx.fillText('Depth (m)', 4, h / 2);
  ctx.fillText('T (°C) / S (PSU)', w / 2 - 35, h - 8);

  if (!profilePoints.length) {
    ctx.fillStyle = '#64748b';
    ctx.fillText('Awaiting CTD sampling...', w / 2 - 55, h / 2);
    return;
  }

  const maxDepth = Math.max(...profilePoints.map(p => p.depth), 1000);
  const temps = profilePoints.map(p => p.temp);
  const minT = Math.min(...temps) - 1, maxT = Math.max(...temps) + 1;

  profilePoints.forEach((p, i) => {
    const x = 50 + ((p.temp - minT) / Math.max(1, maxT - minT)) * (w - 75);
    const y = 15 + (p.depth / maxDepth) * (h - 45);

    const isTarget = currentMissionData && Math.abs(p.depth - (currentMissionData.target_gap?.depth_m || 500)) < 20;

    // Draw point node
    ctx.fillStyle = isTarget ? '#f59e0b' : '#38bdf8';
    ctx.beginPath();
    ctx.arc(x, y, isTarget ? 6 : 4, 0, Math.PI * 2);
    ctx.fill();

    if (i > 0) {
      const prev = profilePoints[i - 1];
      const px = 50 + ((prev.temp - minT) / Math.max(1, maxT - minT)) * (w - 75);
      const py = 15 + (prev.depth / maxDepth) * (h - 45);
      ctx.strokeStyle = '#3fe0c5';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke();
    }

    ctx.fillStyle = isTarget ? '#f59e0b' : '#94a3b8';
    ctx.font = isTarget ? 'bold 9px "IBM Plex Mono", monospace' : '8px "IBM Plex Mono", monospace';
    ctx.fillText(`${p.depth}m ${p.temp}°C`, x + 7, y + 3);
  });
}

// ─── Water Column Overlay ──────────────────────────────────────────────────

function updateWaterColumn(depthM, sample, targetDepthM, seafloorM, bathyStatus) {
  const overlay = document.getElementById('waterColumnOverlay');
  if (!overlay) return;
  overlay.classList.remove('hidden');

  const badgeEl = document.getElementById('wcBathymetryBadge');
  if (badgeEl) {
    if (seafloorM) {
      badgeEl.textContent = `SEAFLOOR: ${seafloorM} m`;
    } else {
      badgeEl.textContent = bathyStatus || 'BATHYMETRY UNAVAILABLE — DEPTH LIMIT SIMULATION';
    }
  }

  const depths = [0, 100, 250, 500, 750, 1000];
  const targetD = targetDepthM || 500;
  const curD = Math.round(depthM || 0);

  document.getElementById('wcRuler').innerHTML = depths.map(d => {
    let tag = d === 0 ? 'SURFACE (0m)' : `${d}m`;
    let isCur = Math.abs(d - curD) < 40;
    let isTarget = Math.abs(d - targetD) < 20;

    let extra = '';
    if (isCur) extra += ` <span style="color:var(--accent); font-weight:700;">↓ NOW: ${curD}m</span>`;
    if (isTarget) extra += ` <span style="color:var(--cyan); font-weight:700;">🎯 TARGET</span>`;

    return `<div class="${isCur ? 'active-depth' : ''}">${tag}${extra}</div>`;
  }).join('<div style="color:var(--teal); text-align:center; line-height:1.2;">↓</div>');

  if (sample) {
    const isTarget = Math.abs(sample.depth_m - targetD) < 20;
    const provBadge = sample.simulated
      ? '<span class="badge amber">SIMULATED MEASUREMENT</span>'
      : '<span class="badge blue">MODEL-DERIVED SIMULATION</span>';
    const targetTag = isTarget
      ? '<div style="color:#34d399; font-weight:700; margin-top:4px; letter-spacing:0.5px;">★ TARGET VARIABLE ACQUIRED</div>'
      : '';

    document.getElementById('wcSampleReadout').innerHTML =
      `<div style="color:var(--accent); font-weight:700; margin-bottom:2px;">CTD SAMPLING AT ${sample.depth_m} m</div>
       <div style="font-size:9.5px; line-height:1.6; color:var(--text);">
         TEMP: <b style="color:var(--cyan);">${sample.temperature_c} °C</b><br>
         SALINITY: <b style="color:var(--teal);">${sample.salinity_psu} PSU</b><br>
         PRESSURE: <b style="color:var(--text-dim);">${sample.pressure_dbar} dbar</b>
       </div>
       <div style="margin-top:4px;">${provBadge}</div>
       ${targetTag}`;
  }
}

function hideWaterColumn() {
  document.getElementById('waterColumnOverlay').classList.add('hidden');
}

// ─── Cinematic Story Narration Banner & Final Summary Modal ───────────────

function updateCinematicBanner(phaseTag, title, subText) {
  const banner = document.getElementById('cinematicBanner');
  if (!banner) return;
  if (!phaseTag) {
    banner.classList.add('hidden');
    return;
  }
  const tagEl = document.getElementById('cbPhaseTag');
  if (tagEl) tagEl.textContent = phaseTag;
  const titleEl = document.getElementById('cbTitle');
  if (titleEl) titleEl.textContent = title;
  const subEl = document.getElementById('cbSubText');
  if (subEl) subEl.textContent = subText || '';
  banner.classList.remove('hidden');
}

function showFinalSummaryModal(sim) {
  const modal = document.getElementById('finalSummaryModal');
  if (!modal) return;

  const winner = sim.selected_platform || {};
  const target = sim.target || {};
  const route = winner.route_details || {};
  const energy = winner.energy_details || {};
  const eig = sim.scientific_payoff || {};
  const before = sim.before_simulation?.information_gap_percent || 82;
  const after = sim.after_simulation?.information_gap_percent || 44;
  const gain = eig.expected_information_gain_percent || (before - after);

  const platformEl = document.getElementById('smPlatform');
  if (platformEl) platformEl.textContent = winner.name || 'GLIDER-07';

  const posEl = document.getElementById('smTargetPos');
  if (posEl) posEl.textContent = `${target.latitude?.toFixed(2) || '15.40'}°N ${target.longitude?.toFixed(2) || '88.70'}°E`;

  const depthEl = document.getElementById('smTargetDepth');
  if (depthEl) depthEl.textContent = `${target.depth_m || 500} m`;

  const distEl = document.getElementById('smDistance');
  if (distEl) distEl.textContent = `${route.direct_distance_km || route.distance_km || 137.8} km`;

  const durEl = document.getElementById('smDuration');
  if (durEl) durEl.textContent = `${route.estimated_duration_hours || 31.4} h`;

  const energyEl = document.getElementById('smEnergy');
  if (energyEl) energyEl.textContent = `${energy.energy_required_percent || 47.0}% (${energy.transit_energy_wh || 1504} Wh)`;

  const reserveEl = document.getElementById('smReserve');
  if (reserveEl) reserveEl.textContent = `${energy.safety_reserve_percent || 15.0}% (${energy.energy_remaining_percent || 35.0}% REMAINING)`;

  const gainEl = document.getElementById('smGapGain');
  if (gainEl) gainEl.textContent = `${before}% → ${after}% (+${gain}% EXPECTED INFORMATION GAIN)`;

  modal.classList.remove('hidden');

  if (viewer) {
    viewer.camera.flyTo({
      destination: positionFromLatLonDepth(target.latitude || 15.4, target.longitude || 88.7, 1200000),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-50), roll: 0 },
      duration: 2.0
    });
  }
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
    const summaryModal = document.getElementById('finalSummaryModal');
    if (summaryModal) summaryModal.classList.add('hidden');
    clearMissionGlobe();

    const gap = this.sim.target_gap || {};
    const winner = this.sim.selected_platform || {};
    const fieldDepth = gap.depth_m || this.sim.current_depth_m || 500;
    const fieldProv = this.sim.current_data_provenance || 'INCOIS MODEL';

    renderGapTarget(gap);
    renderCurrentField(this.sim.routing?.current_field || [], fieldDepth, fieldProv);

    // Pre-animation phases: scanner → candidates → routes
    await this.runPreAnimation(gap, winner);
    this.animate();
  }

  async runPreAnimation(gap, winner) {
    setActivePhase(0);
    document.getElementById('simPhase').textContent = '01 GAP DETECTED';
    updateCinematicBanner('PHASE 01 — GAP DETECTED', 'HIGH-VALUE OBSERVATION GAP DETECTED', `Location: ${gap.latitude || 15.4}°N ${gap.longitude || 88.7}°E | Priority: ${gap.priority_score || 91}% | Target Depth: ${gap.depth_m || 500}m`);
    await this.wait(1000 / this.speed);

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
      updateCinematicBanner('PHASE 02 — FLEET SEARCH', 'DISCOVERING CONTROLLABLE RESEARCH FLEET', 'Searching active ocean vehicle fleet in Bay of Bengal sector...');
      await this.wait(200 / this.speed);
    }
    viewer.entities.remove(this.scannerEnt);

    // Show all candidates
    setActivePhase(2);
    document.getElementById('simPhase').textContent = '03 FEASIBILITY CHECK';
    updateCinematicBanner('PHASE 03 — FEASIBILITY FILTERING', 'EVALUATING VEHICLE CONSTRAINTS & REJECTIONS', 'Filtering candidates by range, depth capability, battery, and steerability...');
    renderFleetInstruments(this.sim.all_candidates || [], null, gap);
    await this.wait(1400 / this.speed);

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
    await this.wait(1000 / this.speed);

    setActivePhase(3);
    document.getElementById('simPhase').textContent = '04 INSTRUMENT SELECTED';
    updateCinematicBanner('PHASE 04 — INSTRUMENT SELECTED', `${winner.name || 'GLIDER-07'} SELECTED FOR MISSION`, `Max Depth: ${winner.maximum_depth_m || 1000}m | Target Depth: ${gap.depth_m || 500}m | Range: ${winner.max_range_km || 400}km | Battery: ${winner.battery_percent || 82}%`);
    renderFleetInstruments(this.sim.all_candidates || [], selId, gap);
    await this.wait(1000 / this.speed);

    // Route planning animation
    setActivePhase(4);
    document.getElementById('simPhase').textContent = '05 ROUTE OPTIMIZATION';
    updateCinematicBanner('PHASE 05/06 — ROUTE OPTIMIZATION', 'GRID A* MULTI-CANDIDATE ROUTE SELECTION', 'Querying INCOIS 3D current model data & evaluating Direct baseline vs Candidates A/B/C...');
    const routing = this.sim.routing || {};
    if (routing.direct_route) renderRoutePolyline(routing.direct_route.waypoints, '#64748b', 2, false, 'direct');
    await this.wait(900 / this.speed);

    (routing.candidate_routes || []).forEach((r, i) => {
      renderRoutePolyline(r.waypoints, ['#818cf8', '#a78bfa', '#c084fc'][i] || '#818cf8', 3, false, `cand_${i}`);
    });
    await this.wait(1100 / this.speed);

    if (routing.selected_route) {
      renderRoutePolyline(routing.selected_route.waypoints, '#3fe0c5', 5, true, 'optimal');
    }
    await this.wait(900 / this.speed);

    // Create vehicle at start
    const startWp = (routing.selected_route || {}).waypoints?.[0] || this.frames[0];
    if (startWp) {
      const activeWinnerData = Object.assign({}, winner, {
        latitude: startWp.latitude,
        longitude: startWp.longitude,
        heading_deg: startWp.heading_deg || 0
      });
      this.vehicleParts = createInstrumentModel(viewer, activeWinnerData, true, false, gap);
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
    const winner = this.sim.selected_platform || {};
    const phaseMap = {
      DEPLOYMENT: 5, TRANSIT: 6, CURRENT_ADJUSTMENT: 7, DESCENT: 8,
      TARGET_APPROACH: 9, TARGET_REACHED: 10, DEEP_SAMPLING: 11
    };
    const pIdx = phaseMap[frame.phase] || 6;
    setActivePhase(pIdx);

    if (this.vehicleParts) {
      updateInstrumentParts(this.vehicleParts, frame.latitude, frame.longitude, frame.depth_m, frame.heading_deg, frame.pitch_deg);
    }

    const posEl = document.getElementById('simPos');
    if (posEl) posEl.textContent = `${frame.latitude.toFixed(2)}°N ${frame.longitude.toFixed(2)}°E`;

    document.getElementById('simPhase').textContent = this.phases[pIdx]?.label || frame.phase;
    document.getElementById('simTime').textContent = `T + ${frame.elapsed_hours.toFixed(1)} h`;
    document.getElementById('simDepth').textContent = `${frame.depth_m.toFixed(0)} m`;
    document.getElementById('simHeading').textContent = `${frame.heading_deg.toFixed(0)}°`;
    document.getElementById('simGroundTrack').textContent = `${frame.ground_track_deg.toFixed(0)}°`;
    document.getElementById('simDragVal').textContent = `${(frame.current_speed_mps || 0).toFixed(2)} m/s → ${(frame.current_direction_deg || 0).toFixed(0)}°`;

    const effSpeedEl = document.getElementById('simEffSpeed');
    if (effSpeedEl) effSpeedEl.textContent = `${(frame.effective_speed_mps || 0.35).toFixed(2)} m/s`;

    // Compute current assist / drag along vehicle heading
    const radH = Cesium.Math.toRadians(frame.heading_deg || 0);
    const radC = Cesium.Math.toRadians(frame.current_direction_deg || 0);
    const along = (frame.current_speed_mps || 0) * Math.cos(radH - radC);
    const assistEl = document.getElementById('simAssistDrag');
    if (assistEl) {
      if (along >= 0) {
        assistEl.innerHTML = `<span style="color:#34d399; font-weight:700;">CURRENT ASSIST: +${along.toFixed(2)} m/s</span>`;
      } else {
        assistEl.innerHTML = `<span style="color:#ef4444; font-weight:700;">CURRENT DRAG: ${along.toFixed(2)} m/s</span>`;
      }
    }

    const remDist = frame.distance_remaining_km != null ? frame.distance_remaining_km : Math.max(0, ((winner.route_details?.distance_km || 0) * (1 - this.frameIdx / Math.max(1, this.frames.length))));
    document.getElementById('simDistRem').textContent = `${remDist.toFixed(1)} km`;

    // Energy & Battery State Readouts
    const curBatt = frame.battery_percent != null ? frame.battery_percent : 82.0;
    const usedPct = frame.energy_used_percent != null ? frame.energy_used_percent : (frame.initial_battery_percent - curBatt);
    const usedWh = frame.energy_used_wh != null ? frame.energy_used_wh : 0.0;
    const remWh = frame.energy_remaining_wh != null ? frame.energy_remaining_wh : 2624.0;
    const reservePct = frame.safety_reserve_percent != null ? frame.safety_reserve_percent : 15.0;
    const battState = frame.battery_state || (curBatt >= reservePct + 15 ? 'NORMAL' : (curBatt >= reservePct ? 'WARNING' : 'CRITICAL'));

    document.getElementById('simBattVal').textContent = `${curBatt.toFixed(1)}%`;
    const fillEl = document.getElementById('simBattFill');
    if (fillEl) fillEl.style.width = `${Math.max(0, Math.min(100, curBatt))}%`;

    const energyUsedEl = document.getElementById('simEnergyUsed');
    if (energyUsedEl) energyUsedEl.textContent = `${usedPct.toFixed(1)}% (${usedWh.toFixed(0)} Wh)`;

    const battRemEl = document.getElementById('simBattRem');
    if (battRemEl) battRemEl.textContent = `${curBatt.toFixed(1)}% (${remWh.toFixed(0)} Wh)`;

    const reserveEl = document.getElementById('simSafetyReserve');
    if (reserveEl) reserveEl.textContent = `${reservePct.toFixed(1)}%`;

    const stateEl = document.getElementById('simEnergyState');
    if (stateEl) {
      if (battState === 'CRITICAL' || curBatt < reservePct) {
        stateEl.textContent = 'CRITICAL — RESERVE BREACHED';
        stateEl.className = 'badge red';
        if (fillEl) fillEl.style.background = 'var(--red)';
      } else if (battState === 'WARNING' || curBatt < reservePct + 15.0) {
        stateEl.textContent = 'WARNING — APPROACHING RESERVE';
        stateEl.className = 'badge amber';
        if (fillEl) fillEl.style.background = 'var(--accent)';
      } else {
        stateEl.textContent = 'HEALTHY';
        stateEl.className = 'badge green';
        if (fillEl) fillEl.style.background = 'var(--green)';
      }
    }

    document.getElementById('simStatusBadge').textContent = frame.phase;
    document.getElementById('simStatusBadge').className = battState === 'CRITICAL' ? 'badge red' : 'badge blue';

    // Water Column Overlay & Camera Director
    const targetDepthM = this.sim.target?.depth_m || 500;
    updateWaterColumn(frame.depth_m, null, targetDepthM, this.sim.seafloor_depth_m, this.sim.bathymetry_status);

    if (frame.depth_m > 0) {
      // Underwater Close-Up View tracking vehicle descent into water column
      const headingRad = Cesium.Math.toRadians(frame.heading_deg || 0);
      viewer.camera.lookAt(
        positionFromLatLonDepth(frame.latitude, frame.longitude, frame.depth_m),
        new Cesium.HeadingPitchRange(
          headingRad + Math.PI / 2.0,
          Cesium.Math.toRadians(-22.0),
          Math.max(500, frame.depth_m * 1.6)
        )
      );
    } else if (this.frameIdx % 4 === 0) {
      // Surface Transit View
      viewer.camera.flyTo({
        destination: positionFromLatLonDepth(frame.latitude, frame.longitude, 60000),
        orientation: { heading: Cesium.Math.toRadians(frame.heading_deg || 0), pitch: Cesium.Math.toRadians(-40), roll: 0 },
        duration: 0.4
      });
    }
  }

  updateSamplingFrame(sample, idx) {
    const targetDepthM = this.sim.target?.depth_m || 500;
    const isTarget = Math.abs(sample.depth_m - targetDepthM) < 20;

    setActivePhase(11);
    document.getElementById('simPhase').textContent = isTarget
      ? '12 SENSOR SAMPLING — TARGET VARIABLE ACQUIRED'
      : `12 SENSOR SAMPLING AT ${sample.depth_m}m`;

    document.getElementById('simStatusBadge').textContent = isTarget ? 'TARGET ACQUIRED' : 'SAMPLING';
    document.getElementById('simStatusBadge').className = isTarget ? 'badge green' : 'badge blue';
    document.getElementById('simDepth').textContent = `${sample.depth_m} m`;

    updateWaterColumn(sample.depth_m, sample, targetDepthM, this.sim.seafloor_depth_m, this.sim.bathymetry_status);
    addProfilePoint(sample.depth_m, sample.temperature_c, sample.salinity_psu);

    // Update Dive Sequence UI
    const el = document.getElementById(`s_${sample.depth_m}`);
    if (el) {
      const provTag = sample.simulated ? ' [SIM]' : ' [MODEL]';
      const glowCls = isTarget ? 'style="color:#34d399; font-weight:700;"' : 'style="color:#38bdf8;"';
      el.innerHTML = `<span ${glowCls}>✓ T=${sample.temperature_c}°C S=${sample.salinity_psu}${provTag}${isTarget ? ' ★ TARGET ACQUIRED' : ''}</span>`;
    }

    // Stop vehicle translation & deploy CTD probe with winch cable in 3D
    const target = this.sim.target;
    if (this.vehicleParts) {
      updateInstrumentParts(this.vehicleParts, target.latitude, target.longitude, 0.0, 0, 0);
    }

    if (!this.sensorProbeEnt) {
      // 3D CTD Rosette Probe Package
      this.sensorProbeEnt = viewer.entities.add({
        position: positionFromLatLonDepth(target.latitude, target.longitude, sample.depth_m),
        cylinder: {
          length: 14,
          topRadius: 8,
          bottomRadius: 8,
          material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.95),
          outline: true,
          outlineColor: Cesium.Color.WHITE
        },
        label: {
          text: `CTD PROBE: ${sample.depth_m}m`,
          font: 'bold 11px "IBM Plex Mono", monospace',
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          pixelOffset: new Cesium.Cartesian2(0, -22)
        }
      });
      missionEntities.push(this.sensorProbeEnt);

      // 3D Winch Cable
      this.winchCableEnt = viewer.entities.add({
        polyline: {
          positions: new Cesium.CallbackProperty(() => [
            positionFromLatLonDepth(target.latitude, target.longitude, 0),
            positionFromLatLonDepth(target.latitude, target.longitude, this.currentProbeDepth || sample.depth_m)
          ], false),
          width: 3,
          material: Cesium.Color.fromCssColorString('#cbd5e1')
        }
      });
      missionEntities.push(this.winchCableEnt);
    } else {
      this.sensorProbeEnt.position = positionFromLatLonDepth(target.latitude, target.longitude, sample.depth_m);
      this.currentProbeDepth = sample.depth_m;
      if (this.sensorProbeEnt.label) {
        this.sensorProbeEnt.label.text = isTarget
          ? `★ CTD TARGET PROBE: ${sample.depth_m}m`
          : `CTD PROBE: ${sample.depth_m}m`;
      }
    }

    // Camera Director focuses on underwater CTD sampling probe at depth
    const headingRad = Cesium.Math.toRadians(this.sim.selected_platform?.heading_deg || 0);
    viewer.camera.lookAt(
      positionFromLatLonDepth(this.sim.target.latitude, this.sim.target.longitude, sample.depth_m),
      new Cesium.HeadingPitchRange(headingRad, Cesium.Math.toRadians(-18), Math.max(450, sample.depth_m * 1.4))
    );
  }

  showGapReduction() {
    setActivePhase(13);
    document.getElementById('simPhase').textContent = '14 INFORMATION GAP REASSESSED';
    document.getElementById('simStatusBadge').textContent = 'DATA ACQUIRED';
    document.getElementById('simStatusBadge').className = 'badge green';

    const before = this.sim.before_simulation?.information_gap_percent || 82;
    const after = this.sim.after_simulation?.information_gap_percent || 44;
    const gain = this.sim.scientific_payoff?.expected_information_gain_percent || 38;

    updateCinematicBanner('PHASE 14 — INFORMATION GAP REASSESSED', 'BAYESIAN UNCERTAINTY REDUCTION UPDATE', `Before: ${before}% → After: ${after}% | Expected Information Gain: +${gain}% (Simulated What-If)`);

    document.getElementById('gapBefore').textContent = `${before}%`;
    document.getElementById('gapAfter').textContent = `${after}%`;
    document.getElementById('gainVal').textContent = `+${gain}%`;

    const overlay = document.getElementById('gapHeatmapOverlay');
    if (overlay) overlay.classList.remove('hidden');
    const heatBefore = document.getElementById('gapHeatBefore');
    if (heatBefore) heatBefore.querySelector('span').textContent = `${before}%`;
    const heatAfter = document.getElementById('gapHeatAfter');
    if (heatAfter) heatAfter.querySelector('span').textContent = `${after}%`;

    // Visual gap region color shift
    const gap = this.sim.target_gap || {};
    const heatEnt = viewer.entities.add({
      position: positionFromLatLonDepth(gap.latitude || 15.4, gap.longitude || 88.7, 0),
      ellipse: {
        semiMajorAxis: 100000, semiMinorAxis: 100000, height: 0,
        material: Cesium.Color.fromCssColorString('#34d399').withAlpha(0.25),
        outline: true, outlineColor: Cesium.Color.fromCssColorString('#34d399')
      }
    });
    missionEntities.push(heatEnt);

    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(gap.longitude || 88.7, gap.latitude || 15.4, 600000),
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
    updateCinematicBanner('PHASE 14 — MISSION COMPLETE', 'OCEAN ADAPTIVE MISSION EXECUTED & DATA ACQUIRED', 'All CTD sampling sequences completed. Bayesian posterior uncertainty updated.');
    showFinalSummaryModal(this.sim);
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

  const smCloseBtn = document.getElementById('smCloseBtn');
  if (smCloseBtn) smCloseBtn.onclick = () => document.getElementById('finalSummaryModal').classList.add('hidden');

  const smRestartBtn = document.getElementById('smRestartBtn');
  if (smRestartBtn) {
    smRestartBtn.onclick = () => {
      document.getElementById('finalSummaryModal').classList.add('hidden');
      if (playback) playback.restart();
      else startMissionSimulation();
    };
  }

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
