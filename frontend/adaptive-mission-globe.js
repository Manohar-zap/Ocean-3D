/* OCEAN 3D — Adaptive Ocean Observation & Mission Globe Controller */

(function() {
  'use strict';

  // Global adaptive state
  window.adaptiveState = {
    gaps: [],
    selectedGap: null,
    currentPlan: null,
    simulationData: null,
    playback: null,
    gapEntities: [],
    missionEntities: [],
    candidateEntities: [],
    gapsVisible: true
  };

  function apiUrl(path) {
    if (typeof window.apiUrl === 'function') return window.apiUrl(path);
    const base = (window.state && window.state.apiBase) || (typeof window !== 'undefined' && window.BACKEND_API_BASE) || 'http://localhost:8000';
    return `${base.replace(/\/$/, '')}${path}`;
  }

  const PHASES = [
    { id: 1, label: '01 GAP DETECTED' },
    { id: 2, label: '02 FLEET SEARCH' },
    { id: 3, label: '03 FEASIBILITY' },
    { id: 4, label: '04 PLATFORM SELECTED' },
    { id: 5, label: '05 ROUTE OPTIMIZED' },
    { id: 6, label: '06 DEPLOYMENT' },
    { id: 7, label: '07 TRANSIT' },
    { id: 8, label: '08 CURRENT AFFECTED' },
    { id: 9, label: '09 3D DESCENT' },
    { id: 10, label: '10 TARGET REACHED' },
    { id: 11, label: '11 SENSOR SAMPLING' },
    { id: 12, label: '12 DATA ACQUIRED' },
    { id: 13, label: '13 TWIN UPDATED' },
    { id: 14, label: '14 GAP RESOLVED' }
  ];

  function posFromLatLonDepth(lat, lon, depthM) {
    const alt = depthM <= 0 ? 0.0 : -Math.abs(depthM);
    return Cesium.Cartesian3.fromDegrees(lon, lat, alt);
  }

  function headingPitchToQuaternion(headingDeg, pitchDeg) {
    const h = Cesium.Math.toRadians(headingDeg || 0);
    const p = Cesium.Math.toRadians(pitchDeg || 0);
    const hpr = new Cesium.HeadingPitchRoll(h, p, 0);
    return Cesium.Transforms.headingPitchRollQuaternion(Cesium.Cartesian3.ZERO, hpr);
  }

  // Generate crisp 2D Canvas Billboard for Information Gaps on Cesium Globe
  function generateGapBadgeCanvas(gap) {
    const canvas = document.createElement('canvas');
    canvas.width = 176;
    canvas.height = 46;
    const ctx = canvas.getContext('2d');

    const prio = gap.priority_score || 75;
    const isResolved = gap.isResolved;
    const isRed = (gap.color === 'red') || (gap.priority_level === 'CRITICAL');
    const nearestKm = gap.nearest_observation_km || (isRed ? 420 : 260);

    let borderColor = isRed ? '#ef4444' : '#f59e0b';
    let bgColor = isRed ? 'rgba(25, 10, 15, 0.92)' : 'rgba(25, 20, 10, 0.92)';
    let badgeText = isRed ? `🔴 CRITICAL • ${nearestKm.toFixed(0)}km VOID` : `🟡 ELEVATED • ${nearestKm.toFixed(0)}km GAP`;
    let badgeColor = isRed ? '#f87171' : '#fbbf24';

    if (isResolved) {
      borderColor = '#34d399';
      bgColor = 'rgba(6, 24, 18, 0.92)';
      badgeText = `✓ RESOLVED [${prio.toFixed(0)}%]`;
      badgeColor = '#34d399';
    }

    // Outer rounded glass card
    ctx.fillStyle = bgColor;
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(2, 2, 172, 42, 6);
    else ctx.rect(2, 2, 172, 42);
    ctx.fill();
    ctx.stroke();

    // Priority glyph tag
    ctx.fillStyle = badgeColor;
    ctx.font = 'bold 10px "IBM Plex Mono", monospace';
    ctx.fillText(badgeText, 8, 16);

    // Gap Name
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 11px "IBM Plex Sans", sans-serif';
    const nameStr = gap.name.length > 20 ? gap.name.slice(0, 18) + '…' : gap.name;
    ctx.fillText(nameStr, 8, 33);

    return canvas.toDataURL();
  }

  // Canvas billboard for candidate observing platforms
  function generateCandidateBadgeCanvas(inst, isWinner, isRejected) {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 72;
    const ctx = canvas.getContext('2d');

    const isSim = inst.is_simulated || (inst.operational_status && inst.operational_status.includes('SIMULATED'));
    let borderColor = isSim ? '#f59e0b' : '#38bdf8';
    let bgColor = 'rgba(7, 20, 34, 0.94)';
    let tag = isSim ? '◬ SIMULATED ASSET' : '● OPERATIONAL ASSET';
    let tagCol = isSim ? '#f59e0b' : '#38bdf8';

    if (isWinner) {
      borderColor = '#f59e0b';
      bgColor = 'rgba(30, 22, 6, 0.96)';
      tag = isSim ? '★ SELECTED [SIMULATED]' : '★ SELECTED [OPERATIONAL]';
      tagCol = '#f59e0b';
    } else if (isRejected) {
      borderColor = '#f43f5e';
      bgColor = 'rgba(28, 10, 14, 0.94)';
      tag = '✕ UNSUITABLE';
      tagCol = '#f43f5e';
    }

    ctx.fillStyle = bgColor;
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(4, 4, 192, 64, 6);
    else ctx.rect(4, 4, 192, 64);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = tagCol;
    ctx.font = 'bold 10px "IBM Plex Mono", monospace';
    ctx.fillText(tag, 10, 18);

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 12px "IBM Plex Mono", monospace';
    ctx.fillText(inst.instrument_id, 10, 36);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '9.5px "IBM Plex Mono", monospace';
    if (!inst.controllable) {
      ctx.fillText('PASSIVE DRIFT FLOAT [IN-SITU]', 10, 53);
    } else {
      const typeStr = inst.platform_type ? inst.platform_type.toUpperCase() : 'GLIDER';
      const provStr = isSim ? '[SIMULATED PLAN]' : '[OPERATIONAL]';
      ctx.fillText(`${typeStr} • ${inst.battery_percent}% BATT • ${provStr}`, 10, 53);
    }

    return canvas.toDataURL();
  }

  // ─── 1. Automatic Gap Loading and Globe Markers ─────────────────────────────

  window.loadAdaptiveInformationGaps = async function() {
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!viewerInstance) return;
    const ovGapsEl = document.getElementById('ovGaps');
    const isVisible = ovGapsEl ? ovGapsEl.checked : (window.adaptiveState.gapsVisible !== false);
    window.adaptiveState.gapsVisible = isVisible;
    if (!isVisible) {
      clearGapEntities();
      return;
    }
    try {
      let queryStr = '';
      if (typeof currentBounds === 'function') {
        const b = currentBounds();
        if (b) {
          queryStr = `?min_lat=${b.min_lat}&max_lat=${b.max_lat}&min_lon=${b.min_lon}&max_lon=${b.max_lon}`;
        }
      }
      const url = apiUrl('/api/adaptive/gaps' + queryStr);
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      window.adaptiveState.gaps = data.gaps || [];

      clearGapEntities();
      if (window.adaptiveState.gapsVisible !== false) {
        renderGapEntitiesOnGlobe();
      }
      populateAdaptiveSidebarTab();
    } catch (e) {
      console.warn('Adaptive gap loading notice:', e);
    }
  };

  function clearGapEntities() {
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!viewerInstance || !viewerInstance.entities) return;
    (window.adaptiveState.gapEntities || []).forEach(ent => {
      try { viewerInstance.entities.remove(ent); } catch(e){}
    });
    window.adaptiveState.gapEntities = [];
    try {
      const allEnts = viewerInstance.entities.values.slice();
      for(let i=0; i<allEnts.length; i++){
        const e = allEnts[i];
        if (e && (e.isAdaptiveGap || (e.id && (e.id.includes('GAP-') || e.id.includes('_polygon') || e.id.includes('_boundary') || e.id.includes('_halo'))))) {
          viewerInstance.entities.remove(e);
        }
      }
    } catch(e){}
  }

  function renderGapEntitiesOnGlobe() {
    clearGapEntities();
    const ovGapsEl = document.getElementById('ovGaps');
    const isVisible = ovGapsEl ? ovGapsEl.checked : (window.adaptiveState.gapsVisible !== false);
    window.adaptiveState.gapsVisible = isVisible;
    if (!isVisible) {
      return; // Do NOT render any gap entities on globe when toggle is OFF
    }
    const gaps = window.adaptiveState.gaps;
    const selectedGap = window.adaptiveState.selectedGap;
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!viewerInstance) return;

    setupGlobeGapPicking(viewerInstance);

    gaps.forEach(gap => {
      const isSelected = selectedGap && (selectedGap.id === gap.id);
      const isResolved = gap.isResolved;

      // 1. Organic Contour Polygon & Dashed Boundary (matching reference visualization)
      const polyCoords = gap.polygon_coordinates;
      if (polyCoords && Array.isArray(polyCoords) && polyCoords.length >= 3) {
        const flatCoords = [];
        polyCoords.forEach(pt => {
          if (Array.isArray(pt) && pt.length >= 2) {
            flatCoords.push(pt[0], pt[1]);
          }
        });

        if (flatCoords.length >= 6) {
          const cartesianPositions = Cesium.Cartesian3.fromDegreesArray(flatCoords);

          // A. Organic Shaded Polygon Surface (Red for Critical, Yellow for Elevated, Cyan for Selected)
          const isRed = (gap.color === 'red') || (gap.priority_level === 'CRITICAL');
          const polyColor = isResolved
            ? Cesium.Color.fromCssColorString('#059669').withAlpha(0.22)
            : (isSelected
              ? Cesium.Color.fromCssColorString('#0891b2').withAlpha(0.28)
              : (isRed
                ? Cesium.Color.fromCssColorString('#dc2626').withAlpha(0.28)
                : Cesium.Color.fromCssColorString('#d97706').withAlpha(0.26)));

          const polyEnt = viewerInstance.entities.add({
            id: `${gap.id}_polygon`,
            polygon: {
              hierarchy: cartesianPositions,
              height: 0,
              material: polyColor
            }
          });
          polyEnt.gapData = gap;
          polyEnt.gapCentroidPos = cartesianPositions[0] || Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);
          polyEnt.isAdaptiveGap = true;
          window.adaptiveState.gapEntities.push(polyEnt);

          // B. Dashed Perimeter Contour Boundary (Red dashed for Critical, Yellow dashed for Elevated, Cyan for active target)
          const borderColor = isResolved
            ? Cesium.Color.fromCssColorString('#34d399')
            : (isSelected
              ? Cesium.Color.fromCssColorString('#22d3ee')
              : (isRed
                ? Cesium.Color.fromCssColorString('#ef4444')
                : Cesium.Color.fromCssColorString('#f59e0b')));

          const borderEnt = viewerInstance.entities.add({
            id: `${gap.id}_boundary`,
            polyline: {
              positions: cartesianPositions,
              width: isSelected ? 3.5 : 2.5,
              material: new Cesium.PolylineDashMaterialProperty({
                color: borderColor,
                dashLength: 16.0
              }),
              clampToGround: true
            }
          });
          borderEnt.gapData = gap;
          borderEnt.gapCentroidPos = cartesianPositions[0] || Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);
          borderEnt.isAdaptiveGap = true;
          window.adaptiveState.gapEntities.push(borderEnt);

          // C. Interior Survey Sampling Grid Dots (Shown inside selected active target region)
          if (isSelected && gap.survey_points && Array.isArray(gap.survey_points)) {
            gap.survey_points.forEach((sPt, sIdx) => {
              const dotPos = Cesium.Cartesian3.fromDegrees(sPt[0], sPt[1], 0);
              const dotEnt = viewerInstance.entities.add({
                id: `${gap.id}_survey_dot_${sIdx}`,
                position: dotPos,
                point: {
                  pixelSize: 4.5,
                  color: Cesium.Color.fromCssColorString('#38bdf8'),
                  outlineColor: Cesium.Color.BLACK,
                  outlineWidth: 1.0
                }
              });
              dotEnt.gapData = gap;
              dotEnt.gapCentroidPos = dotPos;
              dotEnt.isAdaptiveGap = true;
              window.adaptiveState.gapEntities.push(dotEnt);
            });
          }
        }
      } else {
        // Fallback: Pulsing halo if polygon coordinates are not available
        const prio = gap.priority_score || 70;
        let haloColorHex = isResolved ? '#34d399' : (isSelected ? '#22d3ee' : (prio >= 80 ? '#f43f5e' : '#f59e0b'));
        let haloRadius = isResolved ? 80000 : (prio >= 80 ? 180000 : 130000);
        const haloColor = Cesium.Color.fromCssColorString(haloColorHex);
        const pos = Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);

        const haloEnt = viewerInstance.entities.add({
          id: `${gap.id}_halo`,
          position: pos,
          ellipse: {
            semiMajorAxis: haloRadius,
            semiMinorAxis: haloRadius,
            height: 0,
            material: haloColor.withAlpha(isResolved ? 0.20 : 0.28),
            outline: true,
            outlineColor: haloColor.withAlpha(0.9),
            outlineWidth: 2
          }
        });
        haloEnt.gapData = gap;
        haloEnt.gapCentroidPos = pos;
        haloEnt.isAdaptiveGap = true;
        window.adaptiveState.gapEntities.push(haloEnt);
      }

      // Zone billboard badges removed for clean 3D globe visualization
    });

    setupGlobeGapOcclusion(viewerInstance);
    updateBackfaceOcclusion();
  }

  // Camera horizon occlusion: occludes entities located on the far/back hemisphere of the 3D globe
  function isPointVisibleOnGlobe(viewerInstance, cartesianPos) {
    if (!viewerInstance || !viewerInstance.camera || !cartesianPos) return false;
    try {
      const cameraPos = viewerInstance.camera.positionWC;
      if (!cameraPos) return true;

      // 1. Precise Horizon Ellipsoidal Occluder
      const occluder = new Cesium.EllipsoidalOccluder(Cesium.Ellipsoid.WGS84, cameraPos);
      if (!occluder.isPointVisible(cartesianPos)) return false;

      // 2. Geodetic Surface Normal dot-product check (guarantees points facing away from camera are 100% culled)
      const surfaceNormal = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(cartesianPos, new Cesium.Cartesian3());
      const toCamera = Cesium.Cartesian3.subtract(cameraPos, cartesianPos, new Cesium.Cartesian3());
      const dot = Cesium.Cartesian3.dot(surfaceNormal, toCamera);
      return dot > 0.05;
    } catch (e) {
      return true;
    }
  }

  function updateBackfaceOcclusion() {
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!viewerInstance || !viewerInstance.camera) return;
    try {
      const isVisibleLayer = window.adaptiveState.gapsVisible !== false;
      const entities = window.adaptiveState.gapEntities || [];
      for (let i = 0; i < entities.length; i++) {
        const ent = entities[i];
        if (ent && ent.gapCentroidPos) {
          const isFacingFront = isPointVisibleOnGlobe(viewerInstance, ent.gapCentroidPos);
          ent.show = isVisibleLayer && isFacingFront;
        }
      }

      const candidateEntities = window.adaptiveState.candidateEntities || [];
      for (let i = 0; i < candidateEntities.length; i++) {
        const cEnt = candidateEntities[i];
        if (cEnt && cEnt.candidatePos) {
          const isFacingFront = isPointVisibleOnGlobe(viewerInstance, cEnt.candidatePos);
          cEnt.show = isFacingFront;
        }
      }
    } catch (e) {
      // safe fallback
    }
  }

  function setupGlobeGapOcclusion(viewerInstance) {
    if (!viewerInstance || viewerInstance._adaptiveGapOcclusionHooked) return;
    try {
      // Continuous per-frame horizon occlusion update: fires on every frame during rotation/orbit/pan
      viewerInstance.scene.postRender.addEventListener(updateBackfaceOcclusion);
      viewerInstance.camera.changed.addEventListener(updateBackfaceOcclusion);
      viewerInstance.camera.moveEnd.addEventListener(updateBackfaceOcclusion);
      viewerInstance._adaptiveGapOcclusionHooked = true;
    } catch (e) {
      console.warn('Globe gap occlusion setup error:', e);
    }
  }

  // Globe click handler to select gap regions directly on the 3D globe
  function setupGlobeGapPicking(viewerInstance) {
    if (!viewerInstance || viewerInstance._adaptiveGapPickHandler) return;
    try {
      const handler = new Cesium.ScreenSpaceEventHandler(viewerInstance.scene.canvas);
      handler.setInputAction((click) => {
        const picked = viewerInstance.scene.pick(click.position);
        if (Cesium.defined(picked) && picked.id && (picked.id.gapData || picked.id.isAdaptiveGap)) {
          const gap = picked.id.gapData;
          if (gap && typeof window.selectAdaptiveGap === 'function') {
            window.selectAdaptiveGap(gap);
          }
        }
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
      viewerInstance._adaptiveGapPickHandler = handler;
    } catch (e) {
      console.warn('Globe gap pick handler setup error:', e);
    }
  }

  // Toggle visibility of gap layer
  window.toggleAdaptiveGapsLayer = function(show) {
    window.adaptiveState.gapsVisible = !!show;
    if (!show) {
      clearGapEntities();
    } else {
      if (typeof window.loadAdaptiveInformationGaps === 'function') {
        window.loadAdaptiveInformationGaps();
      } else {
        renderGapEntitiesOnGlobe();
      }
    }
    updateBackfaceOcclusion();
  };

  // Populate list in the 4th sidebar tab ("tab-adaptive")
  function populateAdaptiveSidebarTab() {
    const listEl = document.getElementById('adaptiveGapList');
    if (!listEl) return;
    const gaps = window.adaptiveState.gaps;
    if (!gaps.length) {
      listEl.innerHTML = '<div style="font-size:11px; color:var(--text-dim); padding:8px;">No information gaps detected.</div>';
      return;
    }

    listEl.innerHTML = gaps.map(g => {
      const prio = g.priority_score || 70;
      const isRed = (g.color === 'red') || (g.priority_level === 'CRITICAL');
      const prioBadge = g.isResolved 
        ? '<span class="badge-priority resolved">✓ RESOLVED</span>' 
        : (isRed 
          ? `<span class="badge-priority critical" style="background:#991b1b; color:#fecaca; border:1px solid #ef4444; font-size:9.5px; padding:2px 6px;">🔴 RED • CRITICAL</span>`
          : `<span class="badge-priority elevated" style="background:#854d0e; color:#fef08a; border:1px solid #f59e0b; font-size:9.5px; padding:2px 6px;">🟡 YELLOW • ELEVATED</span>`);

      return `
        <div class="adm-card" style="cursor:pointer; transition:border-color .15s; border-left: 4px solid ${isRed ? '#ef4444' : '#f59e0b'};" onclick="selectAdaptiveGapById('${g.id}')">
          <div class="adm-card-hdr">
            <span style="color:#fff; font-weight:600;">${g.id}</span>
            ${prioBadge}
          </div>
          <div style="font-size:11.5px; font-weight:700; color:var(--text); margin-top:2px;">${g.name}</div>
          <div class="adm-row"><span class="adm-label">Nearest Float</span><span class="adm-val" style="color:${isRed ? '#f87171' : '#fbbf24'}; font-weight:700;">${g.nearest_observation_km.toFixed(0)} km away</span></div>
          <div class="adm-row"><span class="adm-label">Target Depth</span><span class="adm-val" style="color:var(--adm-cyan);">${g.depth_m.toFixed(0)} m</span></div>
          <div class="adm-row"><span class="adm-label">ML Prediction</span><span class="adm-val" style="color:#38bdf8;">${g.ml_expected_value != null ? g.ml_expected_value.toFixed(1) + ' °C' : '10.8 °C'}</span></div>
          <div class="adm-row"><span class="adm-label">90% PI</span><span class="adm-val" style="color:#fb7185; font-size:10px;">[${g.ml_prediction_interval_90pct ? g.ml_prediction_interval_90pct.join(', ') : '...'} °C]</span></div>
        </div>
      `;
    }).join('');
  }

  window.selectAdaptiveGapById = function(gapId) {
    const gap = window.adaptiveState.gaps.find(g => g.id === gapId);
    if (gap) selectAdaptiveGap(gap);
  };

  // ─── 2. Gap Selection & Focused Information Panel ───────────────────────────

  window.selectAdaptiveGap = function(gap) {
    window.adaptiveState.selectedGap = gap;
    window.adaptiveState.currentPlan = null;
    clearMissionGraphics();
    renderGapEntitiesOnGlobe();

    // Smooth camera transition to gap
    (window.viewer || viewer).camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 950000),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-45), roll: 0 },
      duration: 1.2
    });

    // Populate Focused Diagnostics Panel
    const pPanel = document.getElementById('adaptiveMissionPanel');
    if (!pPanel) return;

    const prio = gap.priority_score || 75;
    const isRed = (gap.color === 'red') || (gap.priority_level === 'CRITICAL');
    const prioCls = gap.isResolved ? 'resolved' : (isRed ? 'critical' : 'elevated');
    const prioText = gap.isResolved ? '✓ RESOLVED' : (isRed ? `🔴 CRITICAL VOID (${prio.toFixed(0)}%)` : `🟡 ELEVATED GAP (${prio.toFixed(0)}%)`);

    const badgeEl = document.getElementById('admBadgePriority');
    badgeEl.className = `badge-priority ${prioCls}`;
    badgeEl.textContent = prioText;
    if (!gap.isResolved) {
      badgeEl.style.background = isRed ? '#991b1b' : '#854d0e';
      badgeEl.style.color = isRed ? '#fecaca' : '#fef08a';
      badgeEl.style.border = `1px solid ${isRed ? '#ef4444' : '#f59e0b'}`;
    }

    document.getElementById('admGapTitle').textContent = gap.name;
    document.getElementById('admGapCoords').textContent = `${gap.latitude.toFixed(2)}°N, ${gap.longitude.toFixed(2)}°E (${gap.depth_m.toFixed(0)} m depth)`;
    document.getElementById('admGapReason').textContent = gap.reason || 'Insufficient observational density in deep water column.';

    // Diagnostics Fields
    document.getElementById('admCoverage').textContent = gap.observation_coverage || 'Sparse regional observations';
    document.getElementById('admNearest').textContent = `${gap.nearest_platform_id || 'ARGO-5906203'} (${(gap.nearest_platform_type || 'argo').toUpperCase()}) — ${gap.nearest_observation_km.toFixed(0)} km away`;
    document.getElementById('admStaleness').textContent = `${gap.observation_age_days || 14.2} days (${(gap.observation_age_hours || 340).toFixed(0)} hours)`;
    document.getElementById('admDepthStatus').textContent = gap.depth_coverage_status || `Target: ${gap.depth_m}m. Subsurface water column unobserved.`;
    document.getElementById('admMissingVars').textContent = (gap.variables || ['temperature', 'salinity']).join(', ');

    const mlPred = gap.ml_expected_value != null ? `${gap.ml_expected_value.toFixed(2)} °C` : '10.85 °C';
    const mlPi = gap.ml_prediction_interval_90pct ? `[${gap.ml_prediction_interval_90pct[0].toFixed(1)}, ${gap.ml_prediction_interval_90pct[1].toFixed(1)}]` : '[7.86, 12.76]';
    const predEl = document.getElementById('admMlPrediction');
    if (predEl) predEl.textContent = `${mlPred} (90% PI: ${mlPi})`;

    const uncVal = gap.ml_uncertainty_percent || gap.uncertainty_percent || 56.5;
    const sigmaVal = gap.ml_uncertainty_sigma ? ` (σ = ${gap.ml_uncertainty_sigma.toFixed(2)} °C)` : '';
    const uncEl = document.getElementById('admMlUncertainty');
    if (uncEl) uncEl.textContent = `${uncVal.toFixed(1)}%${sigmaVal}`;

    // Component Breakdown
    const comp = gap.components || {};
    if (document.getElementById('admBarDisagreement')) document.getElementById('admBarDisagreement').style.width = `${comp.ml_uncertainty_score || uncVal}%`;
    if (document.getElementById('admBarSpatial')) document.getElementById('admBarSpatial').style.width = `${comp.spatial_gap_score || 80}%`;
    if (document.getElementById('admBarDensity')) document.getElementById('admBarDensity').style.width = `${comp.density_score || 75}%`;
    if (document.getElementById('admBarDepth')) document.getElementById('admBarDepth').style.width = `${comp.depth_coverage_score || 50}%`;
    if (document.getElementById('admBarTemporal')) document.getElementById('admBarTemporal').style.width = `${comp.temporal_staleness_score || 65}%`;

    // Reset Planning sections
    document.getElementById('admPlanningSection').style.display = 'none';
    document.getElementById('admFailureSection').style.display = 'none';
    document.getElementById('admExecutionSection').style.display = 'none';

    const playBtn = document.getElementById('btnAdaptivePlayMission');
    playBtn.style.display = 'flex';
    playBtn.disabled = false;
    playBtn.innerHTML = '<span>🚀</span><span>PLAN & LAUNCH MISSION</span>';

    // Show panel
    pPanel.classList.add('open');

    // Also update banner
    updateCinematicBanner('PHASE 01 — INFORMATION GAP DETECTED', gap.name, `Location: ${gap.latitude.toFixed(2)}°N ${gap.longitude.toFixed(2)}°E | Depth: ${gap.depth_m}m | Priority: ${prio.toFixed(1)}%`);
  };

  // ─── 3. Animated Platform Discovery & Feasibility Gating ─────────────────────

  window.startAdaptiveMissionPlanning = async function() {
    const gap = window.adaptiveState.selectedGap;
    if (!gap) return;

    const playBtn = document.getElementById('btnAdaptivePlayMission');
    playBtn.disabled = true;
    playBtn.innerHTML = '<span>⏳</span><span>ANALYZING FLEET…</span>';

    // Phase 1: Emit radar scan pulse from target on globe
    buildPhaseTimeline();
    setActivePhase(1);
    updateCinematicBanner('PHASE 02 — SEARCHING FOR AVAILABLE PLATFORMS', 'SCANNING FLEET TELEMETRY RADIUS (1,000 KM)', 'Querying autonomous underwater gliders, deep AUVs, and mobile surface vehicles…');

    renderRadarScanWave(gap.latitude, gap.longitude);

    try {
      // Step 1: Discover candidate instruments
      const instUrl = apiUrl(`/api/adaptive/instruments?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&sensor=${(gap.variables && gap.variables[0]) || 'temperature'}`);
      const instRes = await fetch(instUrl);
      const instData = instRes.ok ? await instRes.json() : null;

      // Reveal candidate markers on globe
      clearCandidateEntities();
      if (instData && instData.all_candidates) {
        renderCandidatePlatformsOnGlobe(instData.all_candidates, gap);
      }

      await new Promise(r => setTimeout(r, 900));

      // Step 2: Feasibility & Optimal Mission Planning
      setActivePhase(2);
      updateCinematicBanner('PHASE 03 — FEASIBILITY & ENERGY OPTIMIZATION', 'EVALUATING MULTI-CRITERIA CONSTRAINTS', 'Checking controllability, depth rating, sensor payload, range, currents, and safety reserve…');

      const planUrl = apiUrl(`/api/adaptive/plan?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&platform=glider`);
      const planRes = await fetch(planUrl);
      const plan = await planRes.json();
      window.adaptiveState.currentPlan = plan;

      // Populate Candidate list in panel
      const planSec = document.getElementById('admPlanningSection');
      planSec.style.display = 'flex';

      renderCandidateListUI(plan.all_candidates || [], plan.selected_winner?.instrument_id);

      // Check for FAILURE CASE (Requirement 16)
      if (plan.decision === 'NO_FEASIBLE_PLATFORM' || !plan.selected_winner) {
        setActivePhase(2);
        updateCinematicBanner('PHASE 03 — FEASIBILITY REJECTED: NO FEASIBLE PLATFORM', 'CANNOT REACH TARGET WITH CONTROLLABLE ASSETS', 'All candidate platforms exceed maximum range or depth threshold for this remote gap.');

        document.getElementById('admFailureSection').style.display = 'flex';
        document.getElementById('admFailReason').textContent = plan.recommended_action || 'Distance to gap exceeds maximum vehicle range. Operating threshold exceeded.';
        document.getElementById('admExecutionSection').style.display = 'none';
        playBtn.style.display = 'none';
        return;
      }

      // Successful platform selection
      const winner = plan.selected_winner;
      setActivePhase(3);
      updateCinematicBanner('PHASE 04 — PLATFORM SELECTED & ROUTE OPTIMIZED', `${winner.name.toUpperCase()} ASSIGNED TO MISSION`, `Transit Distance: ${winner.distance_km.toFixed(1)} km | Duration: ${winner.estimated_duration_hours.toFixed(1)}h | Safety Reserve: ${winner.energy_details?.safety_reserve_percent?.toFixed(1)}%`);

      // Highlight winner platform & draw route on globe
      highlightWinnerPlatform(winner, gap);
      renderRouteOnGlobe(winner.route_details);

      // Populate Winner Details
      document.getElementById('admExecutionSection').style.display = 'flex';
      document.getElementById('admWinnerName').textContent = `${winner.name} [SIMULATED ASSET]`;
      document.getElementById('admWinnerType').textContent = `${(winner.platform_type || 'glider').toUpperCase()} (SIMULATED PLANNING PLATFORM)`;
      document.getElementById('admWinnerDist').textContent = winner.distance_label || `${winner.distance_km.toFixed(1)} km [SIMULATED ESTIMATE]`;
      document.getElementById('admWinnerDuration').textContent = winner.duration_label || `${winner.estimated_duration_hours.toFixed(1)} hrs [SIMULATED ESTIMATE]`;
      document.getElementById('admWinnerEnergy').textContent = `${winner.energy_label || (winner.energy_required_percent?.toFixed(1) + '%')} (${winner.remaining_battery_after_mission?.toFixed(1)}% battery remaining) [SIMULATED]`;
      document.getElementById('admWinnerReserve').textContent = `${winner.energy_details?.safety_reserve_percent?.toFixed(1)}% (Passes ≥15% threshold) [PLANNING SAFETY]`;

      playBtn.style.display = 'none';
      const execBtn = document.getElementById('btnAdaptiveExecuteSim');
      execBtn.style.display = 'flex';

    } catch (err) {
      console.error('Mission planning error:', err);
      playBtn.disabled = false;
      playBtn.innerHTML = '<span>🚀</span><span>RETRY MISSION PLANNING</span>';
    }
  };

  // Render expanding radar pulse on the globe
  function renderRadarScanWave(lat, lon) {
    let radius = 10000;
    const maxRadius = 1000000;
    const scanEnt = (window.viewer || viewer).entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
      ellipse: {
        semiMajorAxis: new Cesium.CallbackProperty(() => {
          radius += 35000;
          if (radius > maxRadius) radius = maxRadius;
          return radius;
        }, false),
        semiMinorAxis: new Cesium.CallbackProperty(() => {
          return radius;
        }, false),
        height: 0,
        material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.28),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#38bdf8')
      }
    });
    window.adaptiveState.missionEntities.push(scanEnt);
    setTimeout(() => (window.viewer || viewer).entities.remove(scanEnt), 2400);
  }

  // Render candidate observing platforms on the globe
  function renderCandidatePlatformsOnGlobe(candidates, gap) {
    candidates.forEach(c => {
      const isControllable = c.controllable;
      const pos = Cesium.Cartesian3.fromDegrees(c.longitude, c.latitude, 0);
      const targetPos = Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);

      // Connecting search ray
      const rayEnt = (window.viewer || viewer).entities.add({
        polyline: {
          positions: [pos, targetPos],
          width: 2,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString(isControllable ? '#38bdf8' : '#f43f5e').withAlpha(0.6),
            dashLength: 14.0
          })
        }
      });
      rayEnt.candidatePos = pos;
      window.adaptiveState.candidateEntities.push(rayEnt);

      // Badge Billboard
      const badgeImg = generateCandidateBadgeCanvas(c, false, !c.feasible);
      const bEnt = (window.viewer || viewer).entities.add({
        position: pos,
        billboard: {
          image: badgeImg,
          scale: 0.85,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM
        }
      });
      bEnt.candidateData = c;
      bEnt.candidatePos = pos;
      window.adaptiveState.candidateEntities.push(bEnt);
    });
  }

  function clearCandidateEntities() {
    window.adaptiveState.candidateEntities.forEach(ent => (window.viewer || viewer).entities.remove(ent));
    window.adaptiveState.candidateEntities = [];
  }

  function clearMissionGraphics() {
    window.adaptiveState.missionEntities.forEach(ent => (window.viewer || viewer).entities.remove(ent));
    window.adaptiveState.missionEntities = [];
    clearCandidateEntities();
  }

  // Highlight selected winner platform
  function highlightWinnerPlatform(winner, gap) {
    const pos = Cesium.Cartesian3.fromDegrees(winner.route_details?.start_lon || gap.longitude, winner.route_details?.start_lat || gap.latitude, 0);
    const ringEnt = (window.viewer || viewer).entities.add({
      position: pos,
      ellipse: {
        semiMajorAxis: 35000,
        semiMinorAxis: 35000,
        height: 0,
        material: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.4),
        outline: true,
        outlineColor: Cesium.Color.fromCssColorString('#f59e0b'),
        outlineWidth: 3
      }
    });
    window.adaptiveState.missionEntities.push(ringEnt);
  }

  // Draw current-aware route and current vector field
  function renderRouteOnGlobe(route) {
    if (!route || !route.waypoints) return;
    const waypoints = route.waypoints;
    const coords = waypoints.map(w => Cesium.Cartesian3.fromDegrees(w.longitude, w.latitude, 0));

    // Route polyline with neon glow
    const lineEnt = (window.viewer || viewer).entities.add({
      polyline: {
        positions: coords,
        width: 4,
        material: new Cesium.PolylineGlowMaterialProperty({
          glowPower: 0.35,
          color: Cesium.Color.fromCssColorString('#3fe0c5')
        })
      }
    });
    window.adaptiveState.missionEntities.push(lineEnt);

    // Current vector field arrows
    const field = route.current_field || [];
    field.forEach(pt => {
      const p1 = Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat, 0);
      const rad = Cesium.Math.toRadians(pt.dir_deg || 0);
      const dist = (pt.speed_mps || 0.2) * 20000;
      const endLon = pt.lon + (Math.sin(rad) * dist) / 111320;
      const endLat = pt.lat + (Math.cos(rad) * dist) / 110540;
      const p2 = Cesium.Cartesian3.fromDegrees(endLon, endLat, 0);

      const arrow = (window.viewer || viewer).entities.add({
        polyline: {
          positions: [p1, p2],
          width: 2,
          material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.5)
        }
      });
      window.adaptiveState.missionEntities.push(arrow);
    });
  }

  // Render candidate platform cards in the sidebar/panel
  function renderCandidateListUI(candidates, winnerId) {
    const listEl = document.getElementById('admCandidateList');
    if (!listEl) return;

    listEl.innerHTML = candidates.map(c => {
      const isWinner = c.instrument_id === winnerId;
      const isFeasible = c.feasible && c.controllable;
      const isSim = c.is_simulated || (c.operational_status && c.operational_status.includes('SIMULATED'));
      const statusBadge = isWinner ? '<span class="badge-priority resolved">★ SELECTED</span>' : (isFeasible ? '<span class="badge-priority elevated">SUITABLE</span>' : '<span class="badge-priority critical">UNSUITABLE</span>');
      const provTag = isSim
        ? '<span style="font-size:9px; padding:1px 5px; border-radius:3px; background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.4); font-weight:600; font-family:\'IBM Plex Mono\',monospace;">◬ SIMULATED PLANNING ASSET</span>'
        : '<span style="font-size:9px; padding:1px 5px; border-radius:3px; background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.4); font-weight:600; font-family:\'IBM Plex Mono\',monospace;">● OPERATIONAL IN-SITU ASSET</span>';

      let reasonHtml = '';
      if (!isFeasible) {
        reasonHtml = `<div style="color:#f43f5e; font-size:10px; margin-top:3px;">✕ Rejected: ${c.rejection_reason || 'Constraints exceeded'}</div>`;
      }

      const distLabel = c.distance_label || (c.distance_to_target_km ? `${c.distance_to_target_km.toFixed(1)} km [SIMULATED ESTIMATE]` : '0 km');
      const battLabel = isSim ? `${c.battery_percent}% • ${c.remaining_range_km} km [SIMULATED]` : `${c.battery_percent}% • ${c.remaining_range_km} km`;

      return `
        <div class="adm-card" style="border-color:${isWinner ? 'var(--adm-accent)' : (isFeasible ? 'var(--adm-line)' : 'rgba(244,63,94,0.4)')}; background:${isWinner ? 'rgba(245,158,11,0.1)' : 'var(--adm-panel-card)'};">
          <div class="adm-card-hdr" style="flex-wrap:wrap; gap:4px;">
            <span style="font-size:11.5px; font-weight:700; color:#fff;">${c.name || c.instrument_id}</span>
            <div style="display:flex; gap:4px; align-items:center;">${provTag} ${statusBadge}</div>
          </div>
          <div class="adm-row"><span class="adm-label">Platform Type</span><span class="adm-val">${c.platform_type.toUpperCase()}</span></div>
          <div class="adm-row"><span class="adm-label">Distance to Gap</span><span class="adm-val">${distLabel}</span></div>
          <div class="adm-row"><span class="adm-label">Max Depth Rating</span><span class="adm-val">${c.maximum_depth_m} m</span></div>
          <div class="adm-row"><span class="adm-label">Battery & Range</span><span class="adm-val">${battLabel}</span></div>
          ${reasonHtml}
        </div>
      `;
    }).join('');
  }

  // ─── 4. Cinematic 3D Mission Execution ──────────────────────────────────────

  window.executeAdaptiveMission = async function() {
    const gap = window.adaptiveState.selectedGap;
    const plan = window.adaptiveState.currentPlan;
    if (!gap || !plan || !plan.selected_winner) return;

    const execBtn = document.getElementById('btnAdaptiveExecuteSim');
    execBtn.disabled = true;

    try {
      const url = apiUrl(`/api/adaptive/simulate?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${(gap.variables && gap.variables[0]) || 'temperature'}`);
      const res = await fetch(url);
      const sim = await res.json();
      window.adaptiveState.simulationData = sim;

      if (sim.status === 'NO_FEASIBLE_MISSION') {
        alert('Mission simulation infeasible for this location.');
        return;
      }

      // Launch Playback Controller
      if (window.adaptiveState.playback) {
        window.adaptiveState.playback.destroy();
      }
      window.adaptiveState.playback = new GlobeMissionPlayback(sim);
      await window.adaptiveState.playback.start();

    } catch (err) {
      console.error('Mission simulation error:', err);
      execBtn.disabled = false;
    }
  };

  // ─── 5. Playback Controller Class ───────────────────────────────────────────

  class GlobeMissionPlayback {
    constructor(simData) {
      this.sim = simData;
      this.frames = simData.trajectory_frames || [];
      this.samples = simData.depth_sampling_sequence || [];
      this.frameIdx = 0;
      this.sampleIdx = 0;
      this.running = false;
      this.paused = false;
      this.speed = 1.0;
      this.lastTs = 0;
      this.vehicleEnt = null;
      this.depthProbeEnt = null;
      this.winchCableEnt = null;
      this.sonarRings = [];
      this.cameraFollow = true;
    }

    async start() {
      this.running = true;
      this.paused = false;
      this.frameIdx = 0;
      this.sampleIdx = 0;

      // Show HUDs
      document.getElementById('phaseTimeline').style.display = 'flex';
      document.getElementById('cinematicBanner').style.display = 'flex';
      document.getElementById('missionTelemetryHud').style.display = 'flex';
      document.getElementById('adaptiveWaterColumnOverlay').style.display = 'flex';
      document.getElementById('missionPlaybackBar').style.display = 'flex';

      // Set Play/Pause icon
      document.getElementById('btnPbPlay').textContent = '⏸';

      // Create 3D Vehicle Model on Globe
      this.createVehicleModel();

      // Camera Fly to Departure Point
      const firstFrame = this.frames[0];
      if (firstFrame) {
        (window.viewer || viewer).camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(firstFrame.longitude, firstFrame.latitude, 65000),
          orientation: { heading: Cesium.Math.toRadians(firstFrame.heading_deg || 0), pitch: Cesium.Math.toRadians(-40), roll: 0 },
          duration: 1.2
        });
      }

      setActivePhase(5);
      updateCinematicBanner('PHASE 06 — MISSION DEPLOYMENT', 'CONTROLLABLE OBSERVING PLATFORM DEPLOYED', `${this.sim.selected_platform?.name} departed position toward target gap.`);

      requestAnimationFrame(ts => this.tick(ts));
    }

    createVehicleModel() {
      const ptype = this.sim.selected_platform?.platform_type || 'glider';
      let colHex = '#38bdf8';
      if (ptype === 'auv') colHex = '#a78bfa';
      else if (ptype === 'usv') colHex = '#3b82f6';
      else if (ptype === 'vessel') colHex = '#f59e0b';

      this.vehicleEnt = (window.viewer || viewer).entities.add({
        id: 'mission_active_vehicle',
        position: Cesium.Cartesian3.ZERO,
        cylinder: {
          length: 22,
          topRadius: 4,
          bottomRadius: 4,
          material: Cesium.Color.fromCssColorString(colHex),
          outline: true,
          outlineColor: Cesium.Color.WHITE
        },
        label: {
          text: `★ ${this.sim.selected_platform?.instrument_id}`,
          font: 'bold 11px "IBM Plex Mono", monospace',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          pixelOffset: new Cesium.Cartesian2(0, -25)
        }
      });
      window.adaptiveState.missionEntities.push(this.vehicleEnt);
    }

    tick(ts) {
      if (!this.running) return;
      if (this.paused) {
        requestAnimationFrame(t => this.tick(t));
        return;
      }

      if (!this.lastTs) this.lastTs = ts;
      const delta = (ts - this.lastTs) / 1000.0;

      if (delta >= (0.05 / this.speed)) {
        this.lastTs = ts;
        if (this.frameIdx < this.frames.length) {
          const frame = this.frames[this.frameIdx];
          this.updateFrame(frame);
          this.frameIdx++;
        } else if (this.sampleIdx < this.samples.length) {
          const sample = this.samples[this.sampleIdx];
          this.updateSamplingStep(sample);
          this.sampleIdx++;
        } else {
          this.completeMission();
          return;
        }
      }

      requestAnimationFrame(t => this.tick(t));
    }

    updateFrame(frame) {
      const pos = posFromLatLonDepth(frame.latitude, frame.longitude, frame.depth_m);
      if (this.vehicleEnt) {
        this.vehicleEnt.position = pos;
        this.vehicleEnt.orientation = headingPitchToQuaternion(frame.heading_deg, frame.pitch_deg);
      }

      // Telemetry HUD Readout (Explicitly marked as simulated)
      document.getElementById('telDepthVal').textContent = `${frame.depth_m.toFixed(0)} m [SIM]`;
      document.getElementById('telSpeedVal').textContent = `${frame.effective_speed_mps?.toFixed(2) || 0.35} m/s [SIM]`;
      document.getElementById('telHeadingVal').textContent = `${frame.heading_deg?.toFixed(0) || 0}° [SIM]`;
      document.getElementById('telBattVal').textContent = `${frame.battery_percent?.toFixed(1) || 80}% [SIM]`;
      document.getElementById('telBattFill').style.width = `${frame.battery_percent || 80}%`;

      // Live sensor readings (Simulated soundings)
      const baseTemp = this.sim.target_gap?.model_value || 28.2;
      const tempC = Math.max(4.0, baseTemp - (frame.depth_m * 0.024));
      const salPSU = 34.8 + (frame.depth_m * 0.0003);
      const pressDbar = frame.depth_m * 0.101 + 10.0;

      document.getElementById('telTempVal').textContent = `${tempC.toFixed(2)} °C [SIM]`;
      document.getElementById('telSalVal').textContent = `${salPSU.toFixed(2)} PSU [SIM]`;
      document.getElementById('telPressVal').textContent = `${pressDbar.toFixed(1)} dbar [SIM]`;

      // Scrubber
      const scrubber = document.getElementById('timelineScrubber');
      if (scrubber) scrubber.value = Math.floor((this.frameIdx / Math.max(1, this.frames.length)) * 1000);
      document.getElementById('playbackTime').textContent = `T+ ${Math.floor(frame.elapsed_hours || 0)}h ${Math.floor(((frame.elapsed_hours || 0) % 1) * 60)}m`;

      // Phase & Banner updates
      if (frame.depth_m > 0) {
        setActivePhase(8); // 3D Descent
        updateCinematicBanner('PHASE 09 — 3D DEPTH DIVE & PROFILING [SIMULATED]', `UNDERWATER DESCENT TO ${frame.depth_m.toFixed(0)} METERS [SIMULATED]`, 'Simulated platform diving through thermocline collecting continuous physical parameters…');

        // Update vertical water column ruler
        this.updateWaterColumnRuler(frame.depth_m);

        // Sonar pulses in 3D
        if (this.frameIdx % 2 === 0) {
          this.emitSonarPulse(frame.latitude, frame.longitude, frame.depth_m);
        }

        // 3D Camera underwater lookAt
        if (this.cameraFollow) {
          const headingRad = Cesium.Math.toRadians(frame.heading_deg || 0);
          (window.viewer || viewer).camera.lookAt(
            pos,
            new Cesium.HeadingPitchRange(headingRad + Math.PI / 2.0, Cesium.Math.toRadians(-25.0), Math.max(600, frame.depth_m * 1.5))
          );
        }
      } else {
        setActivePhase(6); // Transit
        updateCinematicBanner('PHASE 07 — TRANSIT ALONG CURRENT-AFFECTED ROUTE [SIMULATED]', `EN ROUTE: ${frame.distance_remaining_km?.toFixed(1)} KM REMAINING [SIM]`, `Ground Track: ${frame.ground_track_deg?.toFixed(0)}° | Speed: ${frame.effective_speed_mps?.toFixed(2)} m/s [SIM] (Current: ${frame.current_speed_mps?.toFixed(2)} m/s)`);

        if (this.cameraFollow && this.frameIdx % 5 === 0) {
          (window.viewer || viewer).camera.flyTo({
            destination: posFromLatLonDepth(frame.latitude, frame.longitude, 45000),
            orientation: { heading: Cesium.Math.toRadians(frame.heading_deg || 0), pitch: Cesium.Math.toRadians(-42), roll: 0 },
            duration: 0.35
          });
        }
      }
    }

    updateWaterColumnRuler(depthM) {
      const maxRulerDepth = 1000.0;
      const ratio = Math.min(1.0, depthM / maxRulerDepth);
      const cursor = document.getElementById('wcVehicleCursor');
      const label = document.getElementById('wcCursorLabel');
      if (cursor) cursor.style.top = `${ratio * 100}%`;
      if (label) label.textContent = `${depthM.toFixed(0)} m [SIM]`;
    }

    emitSonarPulse(lat, lon, depthM) {
      const pulseEnt = (window.viewer || viewer).entities.add({
        position: posFromLatLonDepth(lat, lon, depthM),
        ellipse: {
          semiMajorAxis: 2000,
          semiMinorAxis: 2000,
          height: -depthM,
          material: Cesium.Color.fromCssColorString('#3fe0c5').withAlpha(0.6),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#3fe0c5')
        }
      });
      window.adaptiveState.missionEntities.push(pulseEnt);
      setTimeout(() => (window.viewer || viewer).entities.remove(pulseEnt), 1200);
    }

    updateSamplingStep(sample) {
      setActivePhase(10);
      updateCinematicBanner('PHASE 11 — SENSOR SAMPLING AT TARGET HORIZON [SIMULATED SOUNDINGS]', `ACQUIRING SYNTHETIC SOUNDING AT ${sample.depth_m} METERS [SIMULATED]`, `T: ${sample.temperature_c}°C | S: ${sample.salinity_psu} PSU | Pressure: ${sample.pressure_dbar} dbar (Simulated data stream)`);

      document.getElementById('telTempVal').textContent = `${sample.temperature_c} °C [SIM]`;
      document.getElementById('telSalVal').textContent = `${sample.salinity_psu} PSU [SIM]`;
      document.getElementById('telPressVal').textContent = `${sample.pressure_dbar} dbar [SIM]`;
      document.getElementById('telOxyVal').textContent = '194 µmol/kg [SIM]';
      document.getElementById('telChlVal').textContent = '0.52 mg/m³ [SIM]';

      this.updateWaterColumnRuler(sample.depth_m);
      this.emitSonarPulse(this.sim.target?.latitude || 15.4, this.sim.target?.longitude || 88.7, sample.depth_m);
    }

    completeMission() {
      this.running = false;
      document.getElementById('btnPbPlay').textContent = '▶';
      setActivePhase(13);
      updateCinematicBanner('PHASE 14 — MISSION COMPLETE & GAP RESOLVED [SIMULATION]', 'DIGITAL TWIN REASSESSED & UNCERTAINTY REDUCED', 'Synthetic deep ocean soundings ingested. Bayesian posterior uncertainty updated.');

      // Visually shrink and transform the gap halo on the globe!
      const gap = window.adaptiveState.selectedGap;
      if (gap) {
        gap.isResolved = true;
        gap.priority_score = this.sim.after_simulation?.information_gap_percent || 24.0;
        gap.priority_level = 'RESOLVED';
        clearGapEntities();
        renderGapEntitiesOnGlobe();
      }

      // Ingest new in-situ observations into backend digital twin store
      if (this.sim && this.sim.selected_platform) {
        fetch(apiUrl('/api/adaptive/ingest'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mission_id: this.sim.mission_id || 'MIS-AUTO',
            platform_id: this.sim.selected_platform.instrument_id,
            platform_type: this.sim.selected_platform.platform_type || 'glider',
            latitude: this.sim.target?.latitude || (gap && gap.latitude) || 0.0,
            longitude: this.sim.target?.longitude || (gap && gap.longitude) || 0.0,
            sampling_sequence: this.sim.depth_sampling_sequence || []
          })
        }).then(r => r.json()).then(res => {
          console.log('[AdaptiveMission] In-situ observations ingested into digital twin:', res);
        }).catch(err => {
          console.warn('[AdaptiveMission] Ingestion notification error:', err);
        });
      }

      // Show Summary Modal
      showMissionSummaryModal(this.sim);
    }

    pause() {
      this.paused = true;
      document.getElementById('btnPbPlay').textContent = '▶';
    }

    resume() {
      this.paused = false;
      this.lastTs = 0;
      document.getElementById('btnPbPlay').textContent = '⏸';
    }

    restart() {
      this.destroy();
      window.executeAdaptiveMission();
    }

    destroy() {
      this.running = false;
      if (this.vehicleEnt) (window.viewer || viewer).entities.remove(this.vehicleEnt);
      clearMissionGraphics();
    }
  }

  // ─── 6. Phase Timeline Helper ───────────────────────────────────────────────

  function buildPhaseTimeline() {
    const el = document.getElementById('phaseTimeline');
    if (!el) return;
    el.innerHTML = PHASES.map(p => `<div id="pt_step_${p.id}" class="pt-step">${p.label}</div>`).join('');
  }

  function setActivePhase(phaseId) {
    PHASES.forEach(p => {
      const stepEl = document.getElementById(`pt_step_${p.id}`);
      if (!stepEl) return;
      if (p.id === phaseId) {
        stepEl.className = 'pt-step active';
        stepEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      } else if (p.id < phaseId) {
        stepEl.className = 'pt-step passed';
      } else {
        stepEl.className = 'pt-step';
      }
    });
  }

  function updateCinematicBanner(phaseTag, title, subText) {
    const b = document.getElementById('cinematicBanner');
    if (!b) return;
    b.style.display = 'flex';
    document.getElementById('cbPhaseTag').textContent = phaseTag;
    document.getElementById('cbTitle').textContent = title;
    document.getElementById('cbSubText').textContent = subText;
  }

  // ─── 7. Summary Modal Card ──────────────────────────────────────────────────

  function showMissionSummaryModal(sim) {
    const modal = document.getElementById('missionSummaryModal');
    if (!modal) return;

    const before = sim.before_simulation?.information_gap_percent || 86;
    const after = sim.after_simulation?.information_gap_percent || 24;
    const gain = sim.scientific_payoff?.expected_information_gain_percent || 62;
    const reduction = sim.scientific_payoff?.uncertainty_reduction_percent || 72;

    document.getElementById('smBefore').textContent = `${before.toFixed(1)}%`;
    document.getElementById('smAfter').textContent = `${after.toFixed(1)}%`;
    document.getElementById('smGain').textContent = `+${gain.toFixed(1)}%`;
    document.getElementById('smReduction').textContent = `${reduction.toFixed(1)}%`;

    modal.classList.add('open');
  }

  window.closeMissionSummaryModal = function() {
    const modal = document.getElementById('missionSummaryModal');
    if (modal) modal.classList.remove('open');
  };

  // ─── DOM Events Hookup ─────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    // Play Mission button in panel
    const btnPlay = document.getElementById('btnAdaptivePlayMission');
    if (btnPlay) btnPlay.onclick = window.startAdaptiveMissionPlanning;

    // Execute Simulation button
    const btnExec = document.getElementById('btnAdaptiveExecuteSim');
    if (btnExec) btnExec.onclick = window.executeAdaptiveMission;

    // Close panel button
    const btnClosePanel = document.getElementById('btnCloseAdaptivePanel');
    if (btnClosePanel) {
      btnClosePanel.onclick = () => {
        document.getElementById('adaptiveMissionPanel').classList.remove('open');
      };
    }

    // Playback bar buttons
    const btnPlayPause = document.getElementById('btnPbPlay');
    if (btnPlayPause) {
      btnPlayPause.onclick = () => {
        const pb = window.adaptiveState.playback;
        if (!pb) return;
        if (pb.paused) pb.resume();
        else pb.pause();
      };
    }

    const btnRestart = document.getElementById('btnPbRestart');
    if (btnRestart) {
      btnRestart.onclick = () => {
        const pb = window.adaptiveState.playback;
        if (pb) pb.restart();
      };
    }

    // Playback speed buttons
    document.querySelectorAll('.pb-speed-btn').forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll('.pb-speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const sp = parseFloat(btn.dataset.speed || '1.0');
        if (window.adaptiveState.playback) window.adaptiveState.playback.speed = sp;
      };
    });

    // Layer toggle in GIS layers
    const ovGaps = document.getElementById('ovGaps');
    if (ovGaps) {
      ovGaps.onchange = (e) => {
        window.toggleAdaptiveGapsLayer(e.target.checked);
      };
    }

    // Header nav button
    const navBtn = document.getElementById('btnNavAdaptiveMission');
    if (navBtn) {
      navBtn.onclick = (e) => {
        e.preventDefault();
        if (typeof window.switchMainView === 'function') {
          window.switchMainView('adaptive');
        } else if (typeof switchMainView === 'function') {
          switchMainView('adaptive');
        }
        const firstGap = window.adaptiveState && window.adaptiveState.gaps && window.adaptiveState.gaps[0];
        if (firstGap && typeof window.selectAdaptiveGap === 'function') {
          window.selectAdaptiveGap(firstGap);
        }
      };
    }
  });

})();
