/* OCEAN 3D — Adaptive Mission Control JS Engine */

var viewer = null;
let currentMissionData = null;
let simulationPlaybackTimer = null;
let trajectoryEntities = [];

function apiUrl(path) {
  const base = (typeof window !== 'undefined' && window.BACKEND_API_BASE) || 'http://localhost:8000';
  return `${base.replace(/\/$/, '')}${path}`;
}

async function initMissionGlobe() {
  const token = (typeof window !== 'undefined' && window.CESIUM_ION_TOKEN) || '';
  if (token && token !== 'demo_token') {
    Cesium.Ion.defaultAccessToken = token;
  }

  viewer = new Cesium.Viewer('cesiumContainer', {
    terrainProvider: Cesium.createWorldTerrain ? Cesium.createWorldTerrain() : new Cesium.EllipsoidTerrainProvider(),
    animation: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    geocoder: false,
    homeButton: false,
    infoBox: false,
    sceneModePicker: false,
    selectionIndicator: false,
    timeline: false,
    navigationHelpButton: false
  });

  // Initial Camera Target: Bay of Bengal Information Gap (15.4°N, 88.7°E)
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(88.7, 15.4, 1800000),
    orientation: {
      heading: Cesium.Math.toRadians(0.0),
      pitch: Cesium.Math.toRadians(-60.0),
      roll: 0.0
    },
    duration: 1.5
  });

  // Handle Globe Clicks
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction(async (click) => {
    const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
    if (cartesian) {
      const lat = Cesium.Math.toDegrees(Cesium.Cartographic.fromCartesian(cartesian).latitude);
      const lon = Cesium.Math.toDegrees(Cesium.Cartographic.fromCartesian(cartesian).longitude);
      await loadAdaptiveMissionForLocation(lat, lon);
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  // Initial Mission Load
  await loadAdaptiveMissionForLocation(15.4, 88.7);
}

async function loadAdaptiveMissionForLocation(lat, lon, depth = 500.0) {
  try {
    const res = await fetch(apiUrl(`/api/adaptive/plan?lat=${lat.toFixed(2)}&lon=${lon.toFixed(2)}&depth=${depth}&platform=glider`));
    if (!res.ok) return;
    const plan = await res.json();
    currentMissionData = plan;

    renderMissionPlanUI(plan);
    renderMissionGlobeOverlay(plan);
  } catch (e) {
    console.warn("Failed to load mission plan:", e);
  }
}

function renderMissionPlanUI(plan) {
  const gap = plan.target_gap || {};
  const winner = plan.selected_winner || {};
  const rejected = plan.rejected_candidates || [];

  // Update Gap Card
  document.getElementById("gapBadge").textContent = `PRIORITY ${gap.priority_score || 91} / 100`;
  document.getElementById("gapCoords").textContent = `${gap.latitude}° N, ${gap.longitude}° E`;
  document.getElementById("gapDepth").textContent = `${gap.depth_m || 500} m`;
  document.getElementById("gapTempRes").textContent = `+${(gap.residual_mean || 2.31).toFixed(2)} °C`;
  document.getElementById("gapAge").textContent = `${((gap.observation_age_hours || 201) / 24).toFixed(1)} days`;
  document.getElementById("gapDist").textContent = `${gap.nearest_observation_km || 186} km`;

  // Update Candidates Card
  const listEl = document.getElementById("candidateList");
  if (listEl) {
    let html = "";
    if (winner) {
      html += `
        <div style="background:var(--panel-3); padding:8px; border-radius:4px; border:1px solid var(--accent);">
          <div style="display:flex; justify-content:space-between; font-weight:700; font-size:11px;">
            <span>${winner.name}</span>
            <span class="badge green">RECOMMENDED (${winner.mission_score})</span>
          </div>
          <div style="font-size:10px; color:var(--text-dim); margin-top:2px;">
            Dist: ${winner.distance_km}km | Duration: ${winner.estimated_duration_hours}h | EIG: +${winner.expected_information_gain}%
          </div>
        </div>`;
    }

    rejected.forEach(r => {
      html += `
        <div style="background:var(--panel-3); padding:8px; border-radius:4px; border:1px solid var(--line); opacity:0.75;">
          <div style="display:flex; justify-content:space-between; font-weight:700; font-size:11px;">
            <span>${r.name || r.instrument_id}</span>
            <span class="badge red">REJECTED</span>
          </div>
          <div style="font-size:10px; color:#ef4444; margin-top:2px;">
            Reason: ${r.rejection_reason || 'Constraint limit exceeded'}
          </div>
        </div>`;
    });
    listEl.innerHTML = html;
  }

  // Update Feasibility & Energy Card
  if (winner && winner.route_details) {
    const route = winner.route_details;
    const energy = winner.energy_details || {};
    document.getElementById("mDist").textContent = `${route.direct_distance_km} km`;
    document.getElementById("mCurrent").textContent = `${route.avg_current_speed_mps} m/s (${route.avg_current_direction_deg}°)`;
    document.getElementById("mDuration").textContent = `${route.estimated_duration_hours} Hours`;
    document.getElementById("mEnergy").textContent = `${energy.energy_required_percent || 47}%`;
  }

  // Update Scientific Payoff Card
  const eig = winner.information_gain_details || {};
  document.getElementById("gapBefore").textContent = `${gap.priority_score || 82}%`;
  document.getElementById("gapAfter").textContent = `${eig.posterior_uncertainty_percent || 44}%`;
  document.getElementById("gainVal").textContent = `+${eig.expected_information_gain_percent || 38}%`;
}

function clearMissionGlobe() {
  trajectoryEntities.forEach(e => viewer.entities.remove(e));
  trajectoryEntities = [];
}

function renderMissionGlobeOverlay(plan) {
  if (!viewer) return;
  clearMissionGlobe();

  const gap = plan.target_gap || {};
  const winner = plan.selected_winner || {};
  const route = winner.route_details || {};
  const waypoints = route.waypoints || [];

  // 1. Target Gap Ring (Glowing Amber)
  const targetEnt = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 2000.0),
    ellipse: {
      semiMajorAxis: 150000.0,
      semiMinorAxis: 150000.0,
      height: 2000.0,
      material: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.25),
      outline: true,
      outlineColor: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.95),
      outlineWidth: 2.5
    },
    label: {
      text: `🎯 GAP TARGET (${gap.priority_score}%)`,
      font: 'bold 11px IBM Plex Mono',
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -25),
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 3
    }
  });
  trajectoryEntities.push(targetEnt);

  // 2. Trajectory Waypoints & Current Vectors
  if (waypoints.length >= 2) {
    const coords = [];
    waypoints.forEach(w => {
      coords.push(w.longitude, w.latitude, 2500.0);
    });

    const routePoly = viewer.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArrayHeights(coords),
        width: 4.0,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.4,
          taperPower: 0.7,
          color: Cesium.Color.fromCssColorString('#3fe0c5')
        })
      }
    });
    trajectoryEntities.push(routePoly);
  }
}

async function startMissionSimulation() {
  if (!currentMissionData || !currentMissionData.target_gap) return;
  const gap = currentMissionData.target_gap;

  const btn = document.getElementById("btnPlayMission");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(apiUrl(`/api/adaptive/simulate?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${gap.variables[0]}`));
    if (!res.ok) return;
    const sim = await res.json();

    runSimulationAnimation(sim);
  } catch (e) {
    console.warn("Simulation playback error:", e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function runSimulationAnimation(sim) {
  const winner = sim.selected_platform || {};
  const route = winner.route_details || {};
  const waypoints = route.waypoints || [];
  if (!waypoints.length) return;

  const statusBadge = document.getElementById("simStatusBadge");
  const timeEl = document.getElementById("simTime");
  const distEl = document.getElementById("simDistRem");
  const battVal = document.getElementById("simBattVal");
  const battFill = document.getElementById("simBattFill");

  let stepIdx = 0;
  if (simulationPlaybackTimer) clearInterval(simulationPlaybackTimer);

  statusBadge.textContent = "TRANSIT & SAMPLING";
  statusBadge.className = "badge blue";

  // Vehicle Entity
  const vehicleEnt = viewer.entities.add({
    position: Cesium.Cartesian3.fromDegrees(waypoints[0].longitude, waypoints[0].latitude, 3000.0),
    point: {
      pixelSize: 12,
      color: Cesium.Color.fromCssColorString('#38bdf8'),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2
    },
    label: {
      text: `${winner.name || 'GLIDER'} [NAVIGATING]`,
      font: 'bold 11px IBM Plex Mono',
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -20),
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 3
    }
  });
  trajectoryEntities.push(vehicleEnt);

  const totalSteps = waypoints.length;
  simulationPlaybackTimer = setInterval(() => {
    if (stepIdx >= totalSteps) {
      clearInterval(simulationPlaybackTimer);
      statusBadge.textContent = "TARGET REACHED & DIVE COMPLETE";
      statusBadge.className = "badge green";

      // Mark sampling sequence as completed
      ["s0", "s100", "s250", "s500", "s1000"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = `<span style="color:#34d399; font-weight:700;">✓ ACQUIRED</span>`;
      });

      // Update before vs after payoff values
      document.getElementById("gapAfter").textContent = `${sim.after_simulation.information_gap_percent}%`;
      document.getElementById("gainVal").textContent = `+${sim.scientific_payoff.expected_information_gain_percent}%`;
      return;
    }

    const wp = waypoints[stepIdx];
    vehicleEnt.position = Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, 3000.0);

    const ratio = (stepIdx + 1) / totalSteps;
    const remDist = (route.direct_distance_km * (1.0 - ratio)).toFixed(1);
    const elapsedHrs = (route.estimated_duration_hours * ratio).toFixed(1);
    const curBatt = (winner.battery_percent - (winner.energy_details?.energy_required_percent || 47) * ratio).toFixed(1);

    timeEl.textContent = `T + ${elapsedHrs} Hours`;
    distEl.textContent = `${remDist} km`;
    battVal.textContent = `${curBatt}%`;
    battFill.style.width = `${curBatt}%`;

    stepIdx++;
  }, 800);
}

document.addEventListener("DOMContentLoaded", () => {
  initMissionGlobe();

  const playBtn = document.getElementById("btnPlayMission");
  if (playBtn) playBtn.onclick = startMissionSimulation;
});
