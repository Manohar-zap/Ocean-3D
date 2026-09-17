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
    const validLat = typeof lat === 'number' && !isNaN(lat) ? lat : 0;
    const validLon = typeof lon === 'number' && !isNaN(lon) ? lon : 0;
    const validDepth = typeof depthM === 'number' && !isNaN(depthM) ? depthM : 0;
    const alt = validDepth <= 0 ? 0.0 : -Math.abs(validDepth);
    return Cesium.Cartesian3.fromDegrees(validLon, validLat, alt);
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

    const ptype = (inst.platform_type || 'glider').toLowerCase();
    const isSim = inst.is_simulated || (inst.operational_status && inst.operational_status.includes('SIMULATED'));
    
    // Distinct color palette per vehicle class:
    // AUV: #00e5ff (teal/cyan), UUV: #a855f7 (violet), USV: #f59e0b (amber), ROV: #fb923c, Glider: #38bdf8
    let typeCol = '#38bdf8';
    if (ptype === 'auv') typeCol = '#00e5ff';
    else if (ptype === 'uuv') typeCol = '#a855f7';
    else if (ptype === 'usv' || ptype === 'asv') typeCol = '#f59e0b';
    else if (ptype === 'rov') typeCol = '#fb923c';

    let borderColor = isSim ? typeCol : '#38bdf8';
    let bgColor = 'rgba(7, 20, 34, 0.94)';
    let tag = `● ${ptype.toUpperCase()} [AVAILABLE]`;
    let tagCol = typeCol;

    if (isWinner) {
      borderColor = '#f59e0b';
      bgColor = 'rgba(30, 22, 6, 0.96)';
      tag = `★ SELECTED [${ptype.toUpperCase()}]`;
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
      const typeStr = ptype.toUpperCase();
      const spdStr = (inst.cruise_speed_mps || 0.35).toFixed(1) + ' m/s';
      ctx.fillText(`${typeStr} • ${spdStr} • ${inst.battery_percent}% BATT`, 10, 53);
    }

    return canvas.toDataURL();
  }

  function safeAddEntity(viewerInstance, options) {
    if (!viewerInstance || !options) return null;
    if (options.id) {
      const existing = viewerInstance.entities.getById(options.id);
      if (existing) {
        try { viewerInstance.entities.remove(existing); } catch(e) {}
      }
    }
    return viewerInstance.entities.add(options);
  }

  // ─── 1. Automatic Gap Loading and Globe Markers ─────────────────────────────

  window.loadAdaptiveInformationGaps = async function() {
    const viewer = window.viewer; if (!viewer) return;
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
      renderGapEntitiesOnGlobe();
      populateAdaptiveSidebarTab();
    } catch (e) {
      console.warn('Adaptive gap loading notice:', e);
    }
  };

  function clearGapEntities() {
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!viewerInstance) return;
    if (window.adaptiveState.gapEntities && window.adaptiveState.gapEntities.length > 0) {
      window.adaptiveState.gapEntities.forEach(ent => {
        try { viewerInstance.entities.remove(ent); } catch(e) {}
      });
      window.adaptiveState.gapEntities = [];
    }
    try {
      const toRemove = [];
      const col = viewerInstance.entities.values;
      for (let i = 0; i < col.length; i++) {
        const ent = col[i];
        if (ent && (ent.isAdaptiveGap || (ent.id && (ent.id.endsWith('_polygon') || ent.id.endsWith('_boundary') || ent.id.endsWith('_halo') || ent.id.includes('_survey_dot_'))))) {
          toRemove.push(ent);
        }
      }
      toRemove.forEach(ent => {
        try { viewerInstance.entities.remove(ent); } catch(e) {}
      });
    } catch(e) {}
  }

  function renderGapEntitiesOnGlobe() {
    clearGapEntities();
    const ovGapsEl = document.getElementById('ovGaps');
    const isVisible = ovGapsEl ? ovGapsEl.checked : (window.adaptiveState.gapsVisible !== false);
    window.adaptiveState.gapsVisible = isVisible;
    if (!isVisible) return;

    const gaps = window.adaptiveState.gaps;
    const selectedGap = window.adaptiveState.selectedGap;
    const viewerInstance = window.viewer || viewer;
    if (!viewerInstance) return;

    setupGlobeGapPicking(viewerInstance);

    gaps.forEach(gap => {
      const isSelected = selectedGap && (selectedGap.id === gap.id);
      const isResolved = gap.isResolved;

      // Helper: 2D polygon signed area (Shoelace formula)
      const calcPolygonArea = (pts) => {
        if (!pts || pts.length < 3) return 0;
        let area = 0;
        for (let i = 0; i < pts.length; i++) {
          const j = (i + 1) % pts.length;
          area += pts[i][0] * pts[j][1];
          area -= pts[j][0] * pts[i][1];
        }
        return Math.abs(area / 2.0);
      };

      // 1. Organic Contour Polygon & Dashed Boundary (matching reference visualization)
      const polyCoords = gap.polygon_coordinates;
      let cleanedCoords = [];
      let crossesAntimeridian = false;

      if (polyCoords && Array.isArray(polyCoords) && polyCoords.length >= 3) {
        let minLon = 180, maxLon = -180;
        for (let i = 0; i < polyCoords.length; i++) {
          const pt = polyCoords[i];
          if (Array.isArray(pt) && pt.length >= 2 && !isNaN(pt[0]) && !isNaN(pt[1])) {
            let lon = Number(pt[0]);
            let lat = Math.max(-85.0, Math.min(85.0, Number(pt[1])));
            while (lon > 180) lon -= 360;
            while (lon < -180) lon += 360;

            if (lon < minLon) minLon = lon;
            if (lon > maxLon) maxLon = lon;

            const last = cleanedCoords[cleanedCoords.length - 1];
            if (!last || (Math.hypot(last[0] - lon, last[1] - lat) > 0.04)) {
              cleanedCoords.push([lon, lat]);
            }
          }
        }
        if (maxLon - minLon > 180) {
          crossesAntimeridian = true;
        }
        while (cleanedCoords.length >= 3) {
          const first = cleanedCoords[0];
          const last = cleanedCoords[cleanedCoords.length - 1];
          if (Math.hypot(first[0] - last[0], first[1] - last[1]) < 0.04) {
            cleanedCoords.pop();
          } else {
            break;
          }
        }
      }

      const polyArea = calcPolygonArea(cleanedCoords);
      let polygonAdded = false;

      if (!crossesAntimeridian && cleanedCoords.length >= 3 && polyArea >= 0.25) {
        try {
          const flatCoords = [];
          cleanedCoords.forEach(pt => flatCoords.push(pt[0], pt[1]));
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

          const polyEnt = safeAddEntity(viewerInstance, {
            id: `${gap.id}_polygon`,
            polygon: {
              hierarchy: cartesianPositions,
              material: polyColor
            }
          });
          if (polyEnt) {
            polyEnt.gapData = gap;
            polyEnt.gapCentroidPos = cartesianPositions[0] || Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);
            polyEnt.isAdaptiveGap = true;
            window.adaptiveState.gapEntities.push(polyEnt);
            polygonAdded = true;
          }

          // B. Dashed Perimeter Contour Boundary (Closed loop without duplicate vertices)
          const borderColor = isResolved
            ? Cesium.Color.fromCssColorString('#34d399')
            : (isSelected
              ? Cesium.Color.fromCssColorString('#22d3ee')
              : (isRed
                ? Cesium.Color.fromCssColorString('#ef4444')
                : Cesium.Color.fromCssColorString('#f59e0b')));

          const boundaryFlatCoords = [...flatCoords, cleanedCoords[0][0], cleanedCoords[0][1]];
          const boundaryPositions = Cesium.Cartesian3.fromDegreesArray(boundaryFlatCoords);

          const borderEnt = safeAddEntity(viewerInstance, {
            id: `${gap.id}_boundary`,
            polyline: {
              positions: boundaryPositions,
              width: isSelected ? 3.5 : 2.5,
              material: new Cesium.PolylineDashMaterialProperty({
                color: borderColor,
                dashLength: 16.0
              })
            }
          });
          if (borderEnt) {
            borderEnt.gapData = gap;
            borderEnt.gapCentroidPos = cartesianPositions[0] || Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);
            borderEnt.isAdaptiveGap = true;
            window.adaptiveState.gapEntities.push(borderEnt);
          }

          // C. Interior Survey Sampling Grid Dots (Shown inside selected active target region)
          if (isSelected && gap.survey_points && Array.isArray(gap.survey_points)) {
            gap.survey_points.forEach((sPt, sIdx) => {
              const dotPos = Cesium.Cartesian3.fromDegrees(sPt[0], sPt[1], 0);
              const dotEnt = safeAddEntity(viewerInstance, {
                id: `${gap.id}_survey_dot_${sIdx}`,
                position: dotPos,
                point: {
                  pixelSize: 4.5,
                  color: Cesium.Color.fromCssColorString('#38bdf8'),
                  outlineColor: Cesium.Color.BLACK,
                  outlineWidth: 1.0
                }
              });
              if (dotEnt) {
                dotEnt.gapData = gap;
                dotEnt.gapCentroidPos = dotPos;
                dotEnt.isAdaptiveGap = true;
                window.adaptiveState.gapEntities.push(dotEnt);
              }
            });
          }
        } catch (e) {
          console.warn('Polygon rendering error for gap', gap.id, e);
          polygonAdded = false;
        }
      }

      if (!polygonAdded) {
        // Fallback: Pulsing halo if polygon coordinates are not available or degenerate
        const prio = gap.priority_score || 70;
        let haloColorHex = isResolved ? '#34d399' : (isSelected ? '#22d3ee' : (prio >= 80 ? '#f43f5e' : '#f59e0b'));
        let haloRadius = isResolved ? 80000 : (prio >= 80 ? 180000 : 130000);
        const haloColor = Cesium.Color.fromCssColorString(haloColorHex);
        const pos = Cesium.Cartesian3.fromDegrees(gap.longitude, gap.latitude, 0);

        const haloEnt = safeAddEntity(viewerInstance, {
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
        if (haloEnt) {
          haloEnt.gapData = gap;
          haloEnt.gapCentroidPos = pos;
          haloEnt.isAdaptiveGap = true;
          window.adaptiveState.gapEntities.push(haloEnt);
        }
      }

      // Zone billboard badges removed for clean 3D globe visualization
    });

    setupGlobeGapOcclusion(viewerInstance);
    updateBackfaceOcclusion();
  }

  // Camera horizon occlusion: occludes entities located on the far/back hemisphere of the 3D globe
  let _occluder = null;
  let _lastCameraPos = null;
  const _surfaceNormalScratch = new Cesium.Cartesian3();
  const _toCameraScratch = new Cesium.Cartesian3();

  function isPointVisibleOnGlobe(viewerInstance, cartesianPos) {
    if (!viewerInstance || !viewerInstance.camera || !cartesianPos) return false;
    if (isNaN(cartesianPos.x) || isNaN(cartesianPos.y) || isNaN(cartesianPos.z)) return false;
    if (Cesium.Cartesian3.magnitudeSquared(cartesianPos) < 1000.0) return false;
    try {
      const cameraPos = viewerInstance.camera.positionWC;
      if (!cameraPos) return true;

      // 1. Precise Horizon Ellipsoidal Occluder (reusing cached instance)
      if (!_occluder || !_lastCameraPos || !Cesium.Cartesian3.equals(cameraPos, _lastCameraPos)) {
        _occluder = new Cesium.EllipsoidalOccluder(Cesium.Ellipsoid.WGS84, cameraPos);
        _lastCameraPos = Cesium.Cartesian3.clone(cameraPos, _lastCameraPos);
      }
      if (!_occluder.isPointVisible(cartesianPos)) return false;

      // 2. Geodetic Surface Normal dot-product check (guarantees points facing away from camera are 100% culled)
      const surfaceNormal = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(cartesianPos, _surfaceNormalScratch);
      if (!surfaceNormal) return false;
      const toCamera = Cesium.Cartesian3.subtract(cameraPos, cartesianPos, _toCameraScratch);
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
          const isUserVisible = cEnt.userVisible !== false;
          cEnt.show = isUserVisible && isFacingFront;
        }
      }
    } catch (e) {
      // safe fallback
    }
  }

  function setupGlobeGapOcclusion(viewerInstance) {
    if (!viewerInstance || viewerInstance._adaptiveGapOcclusionHooked) return;
    try {
      // Event-driven horizon occlusion: fires only when camera changes, avoiding 60fps postRender thrashing
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
        if (Cesium.defined(picked) && picked.id) {
          if (picked.id.gapData || picked.id.isAdaptiveGap) {
            const gap = picked.id.gapData;
            if (gap && typeof window.selectAdaptiveGap === 'function') {
              window.selectAdaptiveGap(gap);
            }
          } else if (picked.id.candidateData && typeof window.flyToCandidate === 'function') {
            window.flyToCandidate(picked.id.candidateData.instrument_id);
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
    window.adaptiveState.gapsVisible = show;
    updateBackfaceOcclusion();
  };

  // Populate list in the 4th sidebar tab ("tab-adaptive")
  function populateAdaptiveSidebarTab() {
    const listEl = document.getElementById('adaptiveGapList');
    if (!listEl) return;
    const gaps = window.adaptiveState.gaps || [];
    if (!gaps.length) {
      listEl.innerHTML = '<div style="font-size:11px; color:var(--text-dim); padding:8px;">No information gaps detected.</div>';
      return;
    }

    const selectedGap = window.adaptiveState.selectedGap;
    const sortedGaps = [...gaps].sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
    const topGaps = sortedGaps.slice(0, 35);

    listEl.innerHTML = `
      <div style="font-size:10px; color:var(--text-dim); margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
        <span>Top ${topGaps.length} of ${gaps.length} observation gaps:</span>
        <span style="color:var(--adm-accent); font-weight:600;">PRIORITY SORTED</span>
      </div>
    ` + topGaps.map(g => {
      const isCurrent = selectedGap && (selectedGap.id === g.id);
      const prio = g.priority_score || 70;
      const isRed = (g.color === 'red') || (g.priority_level === 'CRITICAL');
      const prioBadge = g.isResolved 
        ? '<span class="badge-priority resolved">✓ RESOLVED</span>' 
        : (isRed 
          ? `<span class="badge-priority critical" style="background:#991b1b; color:#fecaca; border:1px solid #ef4444; font-size:9.5px; padding:2px 6px;">🔴 RED • CRITICAL</span>`
          : `<span class="badge-priority elevated" style="background:#854d0e; color:#fef08a; border:1px solid #f59e0b; font-size:9.5px; padding:2px 6px;">🟡 YELLOW • ELEVATED</span>`);

      const nearestVal = (g.nearest_observation_km != null) ? `${Number(g.nearest_observation_km).toFixed(0)} km away` : 'Sparse';
      const depthVal = (g.depth_m != null) ? `${Number(g.depth_m).toFixed(0)} m` : '500 m';
      const mlVal = (g.ml_expected_value != null) ? `${Number(g.ml_expected_value).toFixed(1)} °C` : '10.8 °C';
      const piVal = (g.ml_prediction_interval_90pct && Array.isArray(g.ml_prediction_interval_90pct)) 
        ? `[${g.ml_prediction_interval_90pct.join(', ')} °C]` : '[7.8, 12.8 °C]';

      return `
        <div class="adm-card ${isCurrent ? 'active-target' : ''}" style="cursor:pointer; transition:all .15s; border-left: 4px solid ${isCurrent ? '#38bdf8' : (isRed ? '#ef4444' : '#f59e0b')}; ${isCurrent ? 'background:rgba(56, 189, 248, 0.12); border-color:#38bdf8;' : ''}" onclick="window.selectAdaptiveGapById('${g.id}')">
          <div class="adm-card-hdr">
            <span style="color:#fff; font-weight:600;">${g.id}</span>
            ${prioBadge}
          </div>
          <div style="font-size:11.5px; font-weight:700; color:var(--text); margin-top:2px;">${g.name}</div>
          <div class="adm-row"><span class="adm-label">Nearest Float</span><span class="adm-val" style="color:${isRed ? '#f87171' : '#fbbf24'}; font-weight:700;">${nearestVal}</span></div>
          <div class="adm-row"><span class="adm-label">Target Depth</span><span class="adm-val" style="color:var(--adm-cyan);">${depthVal}</span></div>
          <div class="adm-row"><span class="adm-label">ML Prediction</span><span class="adm-val" style="color:#38bdf8;">${mlVal}</span></div>
          <div class="adm-row"><span class="adm-label">90% PI</span><span class="adm-val" style="color:#fb7185; font-size:10px;">${piVal}</span></div>
        </div>
      `;
    }).join('');
  }
  window.populateAdaptiveSidebarTab = populateAdaptiveSidebarTab;

  window.selectAdaptiveGapById = function(gapId) {
    const gap = window.adaptiveState.gaps.find(g => g.id === gapId);
    if (gap && typeof window.selectAdaptiveGap === 'function') {
      window.selectAdaptiveGap(gap);
    }
  };

  window.flyToCandidate = function(instrumentId) {
    const plan = window.adaptiveState.currentPlan;
    const candidates = (plan && plan.all_candidates) ? plan.all_candidates : [];
    const c = candidates.find(x => x.instrument_id === instrumentId);
    if (!c) return;
    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (viewerInstance && viewerInstance.camera) {
      if (viewerInstance.camera._flight) viewerInstance.camera.cancelFlight();
      viewerInstance.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      const lat = c.latitude;
      const lon = c.longitude;
      const lonOffset = 0.20 / Math.max(0.3, Math.cos(Cesium.Math.toRadians(lat)));
      const targetLon = lon + lonOffset;
      const bs = new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(targetLon, lat, 0), 0);
      viewerInstance.camera.flyToBoundingSphere(bs, {
        offset: new Cesium.HeadingPitchRange(0.0, Cesium.Math.toRadians(-45.0), 380000),
        duration: 1.2
      });
    }
  };

  // ─── 2. Gap Selection & Focused Information Panel ───────────────────────────

  window.selectAdaptiveGap = function(gap) {
    if (!gap) return;
    const isSameGap = window.adaptiveState.selectedGap && window.adaptiveState.selectedGap.id === gap.id;

    // Clean up any ongoing mission simulation playback first so it doesn't fight camera
    if (window.adaptiveState.playback) {
      try { window.adaptiveState.playback.destroy(); } catch(e) {}
      window.adaptiveState.playback = null;
    }

    const viewerInstance = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (viewerInstance && viewerInstance.camera) {
      if (viewerInstance.camera._flight) viewerInstance.camera.cancelFlight();
      viewerInstance.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      if (viewerInstance.scene && viewerInstance.scene.screenSpaceCameraController) {
        const ssc = viewerInstance.scene.screenSpaceCameraController;
        ssc.enableRotate = true;
        ssc.enableTranslate = true;
        ssc.enableZoom = true;
        ssc.enableTilt = true;
        ssc.enableLook = true;
      }
    }

    window.adaptiveState.selectedGap = gap;
    window.adaptiveState.currentPlan = null;
    clearMissionGraphics();
    renderGapEntitiesOnGlobe();
    populateAdaptiveSidebarTab();

    // Smooth camera transition to center of selected gap zone
    if (viewerInstance && viewerInstance.camera) {
      const lat = gap.latitude;
      const lon = gap.longitude;
      const lonOffset = 0.20 / Math.max(0.3, Math.cos(Cesium.Math.toRadians(lat)));
      const targetLon = lon + lonOffset;
      const bs = new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(targetLon, lat, 0), 0);
      viewerInstance.camera.flyToBoundingSphere(bs, {
        offset: new Cesium.HeadingPitchRange(0.0, Cesium.Math.toRadians(-45.0), 650000),
        duration: 1.2
      });
    }

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
    const profPanel = document.getElementById('profilePanel');
    if (profPanel) profPanel.classList.remove('open');

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

    // Hide overlapping UI banners
    const hint = document.getElementById('hint');
    if (hint) hint.style.display = 'none';
    const depthBanner = document.getElementById('depthDisplayBanner');
    if (depthBanner) depthBanner.style.display = 'none';

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

      const reqSensor = (gap.variables && gap.variables[0]) || 'temperature';
      const pfilter = window.adaptiveState.platformFilter || 'all';
      const planUrl = apiUrl(`/api/adaptive/plan?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${encodeURIComponent(reqSensor)}&platform=${encodeURIComponent(pfilter)}`);
      const planRes = await fetch(planUrl);
      const plan = await planRes.json();
      window.adaptiveState.currentPlan = plan;

      // Populate Candidate list in panel
      const planSec = document.getElementById('admPlanningSection');
      planSec.style.display = 'flex';

      // Automatically remove/hide label and path for unsuitable platforms on the 3D globe
      filterUnsuitableCandidateGraphics(plan.all_candidates || []);

      renderCandidateListUI(plan.all_candidates || [], plan.selected_winner?.instrument_id, plan);

      // Check for FAILURE CASE (Requirement 16)
      if (plan.decision === 'NO_FEASIBLE_PLATFORM' || !plan.selected_winner) {
        setActivePhase(2);
        updateCinematicBanner('PHASE 03 — FEASIBILITY REJECTED: NO FEASIBLE PLATFORM', 'CANNOT REACH TARGET WITH CONTROLLABLE ASSETS', 'All candidate platforms exceed maximum range or depth threshold for this remote gap.');

        // Hide all candidate search rays and markers from globe on complete failure to prevent stray lines
        (window.adaptiveState.candidateEntities || []).forEach(ent => {
          ent.userVisible = false;
          ent.show = false;
        });
        updateBackfaceOcclusion();

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
    if (lat == null || lon == null || isNaN(lat) || isNaN(lon)) return;
    let radius = 10000;
    const maxRadius = 1000000;
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v) return;
    const scanEnt = safeAddEntity(v, {
      id: `radar_wave_${Date.now()}`,
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
    if (scanEnt) {
      window.adaptiveState.missionEntities.push(scanEnt);
      setTimeout(() => {
        try { v.entities.remove(scanEnt); } catch(e) {}
      }, 2400);
    }
  }

  // Render candidate observing platforms on the globe
  function renderCandidatePlatformsOnGlobe(candidates, gap) {
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v || !gap) return;

    const gLon = typeof gap.longitude === 'number' ? gap.longitude : gap.lon;
    const gLat = typeof gap.latitude === 'number' ? gap.latitude : gap.lat;
    if (gLon == null || gLat == null || isNaN(gLon) || isNaN(gLat)) return;
    const targetPos = Cesium.Cartesian3.fromDegrees(gLon, gLat, 0);

    candidates.forEach(c => {
      const isControllable = c.controllable;
      const cLon = typeof c.longitude === 'number' ? c.longitude : c.lon;
      const cLat = typeof c.latitude === 'number' ? c.latitude : c.lat;
      if (cLon == null || cLat == null || isNaN(cLon) || isNaN(cLat)) return;
      const pos = Cesium.Cartesian3.fromDegrees(cLon, cLat, 0);

      // Connecting search ray
      const rayEnt = safeAddEntity(v, {
        id: `search_ray_${c.instrument_id}`,
        polyline: {
          positions: [pos, targetPos],
          width: 2,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString(isControllable ? '#38bdf8' : '#f43f5e').withAlpha(0.6),
            dashLength: 14.0
          })
        }
      });
      const isInitiallyVisible = !!(c.feasible && isControllable);
      if (rayEnt) {
        rayEnt.candidatePos = pos;
        rayEnt.instrumentId = c.instrument_id;
        rayEnt.userVisible = isInitiallyVisible;
        rayEnt.show = isInitiallyVisible;
        window.adaptiveState.candidateEntities.push(rayEnt);
      }

      // Badge Billboard
      const badgeImg = generateCandidateBadgeCanvas(c, false, !c.feasible);
      const bEnt = safeAddEntity(v, {
        id: `candidate_badge_${c.instrument_id}`,
        position: pos,
        billboard: {
          image: badgeImg,
          scale: 0.85,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM
        }
      });
      if (bEnt) {
        bEnt.candidateData = c;
        bEnt.candidatePos = pos;
        bEnt.instrumentId = c.instrument_id;
        bEnt.userVisible = isInitiallyVisible;
        bEnt.show = isInitiallyVisible;
        window.adaptiveState.candidateEntities.push(bEnt);
      }
    });
  }

  // Filter unsuitable candidate graphics: automatically remove/hide their label & search ray
  function filterUnsuitableCandidateGraphics(allCandidates) {
    const feasMap = {};
    const candMap = {};
    (allCandidates || []).forEach(c => {
      feasMap[c.instrument_id] = !!(c.feasible && c.controllable);
      candMap[c.instrument_id] = c;
    });

    (window.adaptiveState.candidateEntities || []).forEach(ent => {
      if (ent && ent.instrumentId) {
        const isFeasible = !!feasMap[ent.instrumentId];
        ent.userVisible = isFeasible;
        ent.show = isFeasible;
        if (ent.billboard && candMap[ent.instrumentId]) {
          ent.candidateData = candMap[ent.instrumentId];
          ent.billboard.image = generateCandidateBadgeCanvas(ent.candidateData, false, !isFeasible);
        }
      }
    });

    updateBackfaceOcclusion();
  }
  window.filterUnsuitableCandidateGraphics = filterUnsuitableCandidateGraphics;

  // Manual per-platform toggle to show/hide its label and search path on the 3D globe
  window.toggleCandidateGlobeVisibility = function(instrumentId, e) {
    if (e && e.stopPropagation) e.stopPropagation();

    const relatedEntities = (window.adaptiveState.candidateEntities || []).filter(ent => ent.instrumentId === instrumentId);
    if (!relatedEntities.length) return;

    // Toggle current visibility state
    const newState = !relatedEntities[0].userVisible;
    relatedEntities.forEach(ent => {
      ent.userVisible = newState;
      ent.show = newState;
    });

    // Update button styling and text in candidate card
    const btn = document.getElementById(`btnToggleCand_${instrumentId}`);
    if (btn) {
      if (newState) {
        btn.innerHTML = '<span>👁️</span><span>3D Track: ON</span>';
        btn.style.background = 'rgba(56, 189, 248, 0.2)';
        btn.style.borderColor = '#38bdf8';
        btn.style.color = '#38bdf8';
        btn.title = 'Click to hide this platform from 3D globe';
      } else {
        btn.innerHTML = '<span>👁️‍🗨️</span><span>3D Track: OFF</span>';
        btn.style.background = 'rgba(255, 255, 255, 0.05)';
        btn.style.borderColor = 'rgba(255, 255, 255, 0.15)';
        btn.style.color = 'var(--text-dim)';
        btn.title = 'Click to display this platform on 3D globe';
      }
    }

    // If enabling, fly camera to candidate location
    if (newState && relatedEntities[0].candidatePos) {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (v && v.camera) {
        const cData = relatedEntities.find(ent => ent.candidateData)?.candidateData;
        if (cData) {
          v.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(cData.longitude, cData.latitude, 750000),
            duration: 1.2
          });
        }
      }
    }

    updateBackfaceOcclusion();
  };

  function clearCandidateEntities() {
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v) return;
    if (window.adaptiveState.candidateEntities) {
      window.adaptiveState.candidateEntities.forEach(ent => {
        try { v.entities.remove(ent); } catch(e) {}
      });
      window.adaptiveState.candidateEntities = [];
    }
  }

  function clearMissionGraphics() {
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v) return;
    if (window.adaptiveState.missionEntities) {
      window.adaptiveState.missionEntities.forEach(ent => {
        try { v.entities.remove(ent); } catch(e) {}
      });
      window.adaptiveState.missionEntities = [];
    }
    clearCandidateEntities();
    const veh = v.entities.getById('mission_active_vehicle');
    if (veh) try { v.entities.remove(veh); } catch(e) {}
  }

  // Highlight selected winner platform
  function highlightWinnerPlatform(winner, gap) {
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v) return;
    const startLon = winner.route_details?.start?.longitude ?? winner.route_details?.start_lon ?? winner.longitude ?? gap.longitude;
    const startLat = winner.route_details?.start?.latitude ?? winner.route_details?.start_lat ?? winner.latitude ?? gap.latitude;
    if (startLon == null || startLat == null || isNaN(startLon) || isNaN(startLat)) return;
    const pos = Cesium.Cartesian3.fromDegrees(startLon, startLat, 0);
    const ringEnt = safeAddEntity(v, {
      id: `winner_ring_${winner.instrument_id}`,
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
    if (ringEnt) {
      window.adaptiveState.missionEntities.push(ringEnt);
    }
  }

  // Draw current-aware route and current vector field
  function renderRouteOnGlobe(route) {
    if (!route || !route.waypoints) return;
    const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
    if (!v) return;

    const waypoints = route.waypoints;
    const coords = (waypoints || [])
      .map(w => {
        const lon = typeof w.longitude === 'number' ? w.longitude : w.lon;
        const lat = typeof w.latitude === 'number' ? w.latitude : w.lat;
        if (lon == null || lat == null || isNaN(lon) || isNaN(lat)) return null;
        return Cesium.Cartesian3.fromDegrees(lon, lat, 0);
      })
      .filter(c => c && !isNaN(c.x));

    // Route polyline with neon glow (requires at least 2 points)
    if (coords.length >= 2) {
      const lineEnt = safeAddEntity(v, {
        id: 'mission_route_glow',
        polyline: {
          positions: coords,
          width: 4,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.35,
            color: Cesium.Color.fromCssColorString('#3fe0c5')
          })
        }
      });
      if (lineEnt) {
        window.adaptiveState.missionEntities.push(lineEnt);
      }
    }

    // Current vector field arrows
    const field = route.current_field || [];
    field.forEach((pt, pIdx) => {
      const lon = typeof pt.longitude === 'number' ? pt.longitude : pt.lon;
      const lat = typeof pt.latitude === 'number' ? pt.latitude : pt.lat;
      if (lon == null || lat == null || isNaN(lon) || isNaN(lat)) return;

      const dir = typeof pt.direction_deg === 'number' ? pt.direction_deg : (typeof pt.dir_deg === 'number' ? pt.dir_deg : 0);
      const spd = typeof pt.speed_mps === 'number' ? pt.speed_mps : 0.2;
      const rad = Cesium.Math.toRadians(dir);
      const dist = Math.max(spd, 0.05) * 15000;
      const endLon = lon + (Math.sin(rad) * dist) / 111320;
      const endLat = lat + (Math.cos(rad) * dist) / 110540;
      if (isNaN(endLon) || isNaN(endLat)) return;

      const p1 = Cesium.Cartesian3.fromDegrees(lon, lat, 0);
      const p2 = Cesium.Cartesian3.fromDegrees(endLon, endLat, 0);
      if (!p1 || !p2 || isNaN(p1.x) || isNaN(p2.x)) return;
      if (Cesium.Cartesian3.distanceSquared(p1, p2) < 1.0) return;

      const arrow = safeAddEntity(v, {
        id: `current_vector_arrow_${pIdx}`,
        polyline: {
          positions: [p1, p2],
          width: 2,
          material: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.5)
        }
      });
      if (arrow) {
        window.adaptiveState.missionEntities.push(arrow);
      }
    });
  }

  // Render candidate platform cards in the sidebar/panel with individual 3D globe toggle & fleet platform filter bar
  function renderCandidateListUI(candidates, winnerId, planObj) {
    const listEl = document.getElementById('admCandidateList');
    if (!listEl) return;

    const curFilter = window.adaptiveState.platformFilter || 'all';

    // 1. Platform Filter Bar
    const filterBar = `
      <div class="adm-filter-bar">
        <button class="adm-pfilter ${curFilter === 'all' ? 'active' : ''}" onclick="window.setAdaptivePlatformFilter('all')">ALL FLEET</button>
        <button class="adm-pfilter ${curFilter === 'auv' ? 'active' : ''}" onclick="window.setAdaptivePlatformFilter('auv')">AUVs (Fast)</button>
        <button class="adm-pfilter ${curFilter === 'uuv' ? 'active' : ''}" onclick="window.setAdaptivePlatformFilter('uuv')">UUVs</button>
        <button class="adm-pfilter ${curFilter === 'glider' ? 'active' : ''}" onclick="window.setAdaptivePlatformFilter('glider')">GLIDERS</button>
        <button class="adm-pfilter ${curFilter === 'usv' ? 'active' : ''}" onclick="window.setAdaptivePlatformFilter('usv')">USVs</button>
      </div>
    `;

    // Filter displayed candidates if a specific platform filter is active
    const filteredCandidates = curFilter === 'all'
      ? candidates
      : candidates.filter(c => (c.platform_type || '').toLowerCase().includes(curFilter.toLowerCase()));

    const suitableCount = filteredCandidates.filter(c => c.feasible && c.controllable).length;
    const unsuitableCount = filteredCandidates.length - suitableCount;

    const summaryHeader = `
      <div style="font-size:10px; color:var(--text-dim); display:flex; justify-content:space-between; align-items:center; margin:4px 0 2px 0; padding:2px 2px;">
        <span style="color:#34d399;"><strong>${suitableCount}</strong> Suitable (Visible on Globe)</span>
        <span style="color:#f43f5e;"><strong>${unsuitableCount}</strong> Unsuitable (Hidden)</span>
      </div>
    `;

    const cardsHtml = filteredCandidates.map(c => {
      const isWinner = c.instrument_id === winnerId;
      const isFeasible = c.feasible && c.controllable;
      const isSim = c.is_simulated || (c.operational_status && c.operational_status.includes('SIMULATED'));
      const statusBadge = isWinner ? '<span class="badge-priority resolved">★ SELECTED</span>' : (isFeasible ? '<span class="badge-priority elevated">SUITABLE</span>' : '<span class="badge-priority critical">UNSUITABLE</span>');
      const provTag = isSim
        ? '<span style="font-size:9px; padding:1px 5px; border-radius:3px; background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.4); font-weight:600; font-family:\'IBM Plex Mono\',monospace;">◬ SIMULATED</span>'
        : '<span style="font-size:9px; padding:1px 5px; border-radius:3px; background:rgba(56,189,248,0.15); color:#38bdf8; border:1px solid rgba(56,189,248,0.4); font-weight:600; font-family:\'IBM Plex Mono\',monospace;">● IN-SITU</span>';

      const ptypeLower = (c.platform_type || '').toLowerCase();
      let pColor = '#38bdf8';
      let speedText = '0.35 m/s (~1.3 km/h)';
      if (ptypeLower.includes('auv')) { pColor = '#00e5ff'; speedText = '1.50 m/s (~5.4 km/h)'; }
      else if (ptypeLower.includes('uuv')) { pColor = '#a855f7'; speedText = '2.20 m/s (~7.9 km/h)'; }
      else if (ptypeLower.includes('usv') || ptypeLower.includes('asv')) { pColor = '#f59e0b'; speedText = '1.80 m/s (~6.5 km/h)'; }
      else if (ptypeLower.includes('rov')) { pColor = '#fb923c'; speedText = '0.80 m/s (~2.9 km/h)'; }

      const ptypeBadge = `<span style="font-size:9.5px; padding:1px 6px; border-radius:3px; background:${pColor}20; color:${pColor}; border:1px solid ${pColor}60; font-weight:700; font-family:'IBM Plex Mono',monospace;">${c.platform_type.toUpperCase()}</span>`;

      let reasonHtml = '';
      if (!isFeasible) {
        reasonHtml = `<div style="color:#f43f5e; font-size:10px; margin-top:3px; font-weight:600;">✕ Rejected: ${c.rejection_reason || 'Constraints exceeded'}</div>`;
      }

      // Transit speed & ETA comparison
      const distKm = c.distance_to_target_km || c.distance_km || 0;
      const cruiseSpd = c.cruise_speed_mps || (ptypeLower.includes('auv') ? 1.5 : (ptypeLower.includes('uuv') ? 2.2 : (ptypeLower.includes('usv') ? 1.8 : 0.35)));
      const estHours = (distKm * 1000.0) / (cruiseSpd * 3600.0);
      const estDays = estHours / 24.0;
      const distLabel = c.distance_label || (distKm ? `${distKm.toFixed(1)} km [SIMULATED ESTIMATE]` : '0 km');
      const transitLabel = estHours < 48 ? `~${estHours.toFixed(1)}h (${speedText})` : `~${estDays.toFixed(1)} days (${speedText})`;
      const battLabel = isSim ? `${c.battery_percent}% • ${c.remaining_range_km} km [SIMULATED]` : `${c.battery_percent}% • ${c.remaining_range_km} km`;

      return `
        <div class="adm-card" onclick="window.flyToCandidate('${c.instrument_id}')" style="cursor:pointer; border-color:${isWinner ? 'var(--adm-accent)' : (isFeasible ? 'var(--adm-line)' : 'rgba(244,63,94,0.4)')}; background:${isWinner ? 'rgba(245,158,11,0.1)' : 'var(--adm-panel-card)'};">
          <div class="adm-card-hdr" style="flex-wrap:wrap; gap:4px;">
            <span style="font-size:11.5px; font-weight:700; color:#fff;">${c.name || c.instrument_id}</span>
            <div style="display:flex; gap:4px; align-items:center;">${provTag} ${statusBadge}</div>
          </div>
          <div class="adm-row"><span class="adm-label">Platform Class</span><span class="adm-val">${ptypeBadge}</span></div>
          <div class="adm-row"><span class="adm-label">Distance to Gap</span><span class="adm-val">${distLabel}</span></div>
          <div class="adm-row"><span class="adm-label">Speed & Transit ETA</span><span class="adm-val" style="color:${isFeasible ? pColor : 'var(--text-dim)'}; font-weight:600;">${transitLabel}</span></div>
          <div class="adm-row"><span class="adm-label">Max Depth Rating</span><span class="adm-val">${c.maximum_depth_m} m</span></div>
          <div class="adm-row"><span class="adm-label">Battery & Range</span><span class="adm-val">${battLabel}</span></div>
          ${reasonHtml}
          
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid rgba(255,255,255,0.08); padding-top:6px;">
            <span style="font-size:10px; color:var(--text-dim);">3D Globe Path & Label:</span>
            <button id="btnToggleCand_${c.instrument_id}" 
                    onclick="window.toggleCandidateGlobeVisibility('${c.instrument_id}', event)"
                    style="display:flex; align-items:center; gap:4px; font-size:10px; font-weight:600; padding:3px 8px; border-radius:3px; cursor:pointer; transition:all .15s; ${isFeasible ? 'background:rgba(56, 189, 248, 0.2); border:1px solid #38bdf8; color:#38bdf8;' : 'background:rgba(255, 255, 255, 0.05); border:1px solid rgba(255, 255, 255, 0.15); color:var(--text-dim);'}"
                    title="${isFeasible ? 'Click to hide this platform from 3D globe' : 'Click to display this platform and ray on 3D globe'}">
              <span>${isFeasible ? '👁️' : '👁️‍🗨️'}</span>
              <span>${isFeasible ? '3D Track: ON' : '3D Track: OFF'}</span>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Distant Void & Sparse Fleet Alternatives Card
    const airDrop = planObj?.air_drop_alternative;
    const vessel = planObj?.vessel_alternative;
    const alternativesHtml = `
      <div class="adm-card" style="margin-top:10px; border-color:rgba(56, 189, 248, 0.4); background:rgba(14, 165, 233, 0.07);">
        <div class="adm-card-hdr" style="color:var(--adm-cyan);">
          <span style="font-weight:700; display:flex; align-items:center; gap:5px;">🛩️ Distant Void Rapid Solution</span>
          <span class="badge-priority elevated" style="background:rgba(56,189,248,0.2); color:#38bdf8; border-color:#38bdf8;">AIR-DEPLOYED</span>
        </div>
        <div style="font-size:11px; color:#f1f5f9; line-height:1.45; margin-top:3px;">
          <strong>Air-Deployed Autonomous Profiling Float (C-130 / Cargo Drone)</strong>: When in-situ assets are sparse or days away, rapid parachute deployment drops an autonomous float directly into the target void.
        </div>
        <div class="adm-row" style="margin-top:4px;"><span class="adm-label">Deployment ETA</span><span class="adm-val" style="color:#34d399; font-weight:700;">~1.5 hours (vs days)</span></div>
        <div class="adm-row"><span class="adm-label">Profiling Depth</span><span class="adm-val">0 to ${airDrop?.target_depth_m ? Math.round(airDrop.target_depth_m) : 2000}m CTD</span></div>
        <div class="adm-row"><span class="adm-label">Expected Info Gain</span><span class="adm-val" style="color:var(--adm-cyan);">+${airDrop?.expected_information_gain || 34}%</span></div>
        <div class="adm-row"><span class="adm-label">Alternative Vessel</span><span class="adm-val">${vessel?.name || 'ORV Sagar Kanya (CTD Rosette)'}</span></div>
      </div>
    `;

    listEl.innerHTML = filterBar + summaryHeader + cardsHtml + alternativesHtml;
  }

  // Interactive Platform Filter Switching
  window.setAdaptivePlatformFilter = async function(filterType) {
    window.adaptiveState.platformFilter = filterType;
    const gap = window.adaptiveState.selectedGap;
    if (!gap) return;

    try {
      const reqSensor = (gap.variables && gap.variables[0]) || 'temperature';
      const planUrl = apiUrl(`/api/adaptive/plan?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${encodeURIComponent(reqSensor)}&platform=${encodeURIComponent(filterType)}`);
      const planRes = await fetch(planUrl);
      if (!planRes.ok) return;
      const plan = await planRes.json();
      window.adaptiveState.currentPlan = plan;

      filterUnsuitableCandidateGraphics(plan.all_candidates || []);
      renderCandidateListUI(plan.all_candidates || [], plan.selected_winner?.instrument_id, plan);

      if (plan.decision === 'NO_FEASIBLE_PLATFORM' || !plan.selected_winner) {
        document.getElementById('admFailureSection').style.display = 'flex';
        document.getElementById('admFailReason').textContent = plan.recommended_action || `No candidate ${filterType.toUpperCase()} asset meets range, speed, or depth threshold for this remote gap.`;
        document.getElementById('admExecutionSection').style.display = 'none';
        return;
      }

      document.getElementById('admFailureSection').style.display = 'none';
      const winner = plan.selected_winner;
      updateCinematicBanner('PHASE 04 — PLATFORM SELECTED & ROUTE OPTIMIZED', `${winner.name.toUpperCase()} ASSIGNED TO MISSION`, `Transit Distance: ${winner.distance_km.toFixed(1)} km | Duration: ${winner.estimated_duration_hours.toFixed(1)}h | Safety Reserve: ${winner.energy_details?.safety_reserve_percent?.toFixed(1)}%`);

      highlightWinnerPlatform(winner, gap);
      renderRouteOnGlobe(winner.route_details);

      document.getElementById('admExecutionSection').style.display = 'flex';
      document.getElementById('admWinnerName').textContent = `${winner.name} [SIMULATED ASSET]`;
      document.getElementById('admWinnerType').textContent = `${(winner.platform_type || 'glider').toUpperCase()} (SIMULATED PLANNING PLATFORM)`;
      document.getElementById('admWinnerDist').textContent = winner.distance_label || `${winner.distance_km.toFixed(1)} km [SIMULATED ESTIMATE]`;
      document.getElementById('admWinnerDuration').textContent = winner.duration_label || `${winner.estimated_duration_hours.toFixed(1)} hrs [SIMULATED ESTIMATE]`;
      document.getElementById('admWinnerEnergy').textContent = `${winner.energy_label || (winner.energy_required_percent?.toFixed(1) + '%')} (${winner.remaining_battery_after_mission?.toFixed(1)}% battery remaining) [SIMULATED]`;
      document.getElementById('admWinnerReserve').textContent = `${winner.energy_details?.safety_reserve_percent?.toFixed(1)}% (Passes ≥15% threshold) [PLANNING SAFETY]`;
    } catch (err) {
      console.error('Error applying adaptive platform filter:', err);
    }
  };

  // ─── 4. Cinematic 3D Mission Execution ──────────────────────────────────────

  window.executeAdaptiveMission = async function() {
    const gap = window.adaptiveState.selectedGap;
    const plan = window.adaptiveState.currentPlan;
    if (!gap || !plan || !plan.selected_winner) return;

    const execBtn = document.getElementById('btnAdaptiveExecuteSim');
    execBtn.disabled = true;

    // Ensure OBSERVATION INFO and adaptive mission panels are closed during 3D mission playback
    const profPanel = document.getElementById('profilePanel');
    if (profPanel) profPanel.classList.remove('open');
    const admPanel = document.getElementById('adaptiveMissionPanel');
    if (admPanel) admPanel.classList.remove('open');

    try {
      const pfilter = window.adaptiveState.platformFilter || 'all';
      const url = apiUrl(`/api/adaptive/simulate?lat=${gap.latitude}&lon=${gap.longitude}&depth=${gap.depth_m}&variable=${(gap.variables && gap.variables[0]) || 'temperature'}&platform=${encodeURIComponent(pfilter)}`);
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
      this.state = 'TRANSIT'; // 'TRANSIT' | 'SAMPLING' | 'REASSESS' | 'COMPLETED'
      this.running = false;
      this.paused = false;
      this.speed = 1.0;
      this.lastTs = 0;
      this.vehicleEnt = null;
      this.vehicleParts = [];
      this.vehiclePos = null;
      this.vehicleOrient = null;
      this.depthPillarEnt = null;
      this.trailEnt = null;
      this.completedPositions = [];
      this.depthPillarPositions = [];
      this.cameraFollow = true;
      this.currentFrame = null;
      this.hiddenEntities = [];
      this.camMode = 'TOP'; // 'TOP' (Top-down aerial view) | 'CHASE' | 'FREE'
      this.topViewOffset = new Cesium.Cartesian3(0.0, -2500.0, 75000.0);
      this.chaseViewOffset = new Cesium.Cartesian3(0.0, -32000.0, 24000.0);
    }

    getPartWorldPosition(localX, localY, localZ) {
      if (!this.vehiclePos) return Cesium.Cartesian3.ZERO;
      if (!this.vehicleOrient) return this.vehiclePos;
      try {
        const rot = Cesium.Matrix3.fromQuaternion(this.vehicleOrient, new Cesium.Matrix3());
        const mat = Cesium.Matrix4.fromRotationTranslation(rot, this.vehiclePos, new Cesium.Matrix4());
        return Cesium.Matrix4.multiplyByPoint(mat, new Cesium.Cartesian3(localX, localY, localZ), new Cesium.Cartesian3());
      } catch (err) {
        return this.vehiclePos;
      }
    }

    _generateMicroTagCanvas(name, ptype, colHex) {
      const canvas = document.createElement('canvas');
      canvas.width = 190;
      canvas.height = 44;
      const ctx = canvas.getContext('2d');

      const col = colHex || '#38bdf8';
      ctx.fillStyle = 'rgba(7, 20, 34, 0.90)';
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(3, 3, 184, 38, 6);
      else ctx.rect(3, 3, 184, 38);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = col;
      ctx.font = 'bold 9px "IBM Plex Mono", monospace';
      ctx.fillText(`★ ${ptype.toUpperCase()} [3D TWIN]`, 10, 16);

      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 8.5px "IBM Plex Mono", monospace';
      ctx.fillText(`● ACTIVE`, 130, 16);

      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 11px "IBM Plex Mono", monospace';
      ctx.fillText(name, 10, 32);

      return canvas.toDataURL();
    }

    _generateVehicleBadgeCanvas(name, ptype, depthM, speedMps, colHex) {
      return this._generateMicroTagCanvas(name, ptype, colHex);
    }

    createVehicleModel() {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v) return;

      const winner = this.sim.selected_platform || window.adaptiveState.currentPlan?.selected_winner;
      const ptype = (winner?.platform_type || this.sim.selected_platform?.platform_type || 'glider').toUpperCase();
      const name = winner?.instrument_id || winner?.name || this.sim.selected_platform?.instrument_id || 'GLIDER';
      const winnerId = winner?.instrument_id || name;
      const ptypeLower = ptype.toLowerCase();
      let colHex = '#38bdf8'; // glider cyan
      if (ptypeLower.includes('auv')) colHex = '#00e5ff'; // auv teal
      else if (ptypeLower.includes('uuv')) colHex = '#a855f7'; // uuv violet
      else if (ptypeLower.includes('usv') || ptypeLower.includes('asv')) colHex = '#f59e0b'; // usv amber
      else if (ptypeLower.includes('rov')) colHex = '#fb923c'; // rov orange
      this.vehicleColorHex = colHex;
      this.vehiclePType = ptype;
      this.vehicleName = name;

      // 1. ISOLATE SELECTED INSTRUMENT ON THE 3D GLOBE:
      if (window.adaptiveState.candidateEntities) {
        window.adaptiveState.candidateEntities.forEach(ent => {
          try { v.entities.remove(ent); } catch(e) {}
        });
        window.adaptiveState.candidateEntities = [];
      }

      // 2. Remove static candidate badges and prior parts
      if (winnerId) {
        const oldBadge = v.entities.getById(`candidate_badge_${winnerId}`);
        if (oldBadge) try { v.entities.remove(oldBadge); } catch(e) {}
        const oldRay = v.entities.getById(`search_ray_${winnerId}`);
        if (oldRay) try { v.entities.remove(oldRay); } catch(e) {}
        const oldRing = v.entities.getById(`winner_ring_${winnerId}`);
        if (oldRing) try { v.entities.remove(oldRing); } catch(e) {}
      }
      const prevVeh = v.entities.getById('mission_active_vehicle');
      if (prevVeh) try { v.entities.remove(prevVeh); } catch(e) {}

      if (this.vehicleParts) {
        this.vehicleParts.forEach(p => { try { v.entities.remove(p); } catch(e){} });
        this.vehicleParts = [];
      }

      // 3. Hide any base observation platform entity at the origin for this selected platform
      this.hiddenEntities = [];
      if (v.entities && v.entities.values) {
        const allEnts = v.entities.values;
        for (let i = 0; i < allEnts.length; i++) {
          const ent = allEnts[i];
          if (ent && ent.userData && ent.userData.platform_id) {
            const pId = String(ent.userData.platform_id);
            if (pId === winnerId || (winnerId && (pId.includes(winnerId) || winnerId.includes(pId)))) {
              ent.show = false;
              this.hiddenEntities.push(ent);
            }
          }
        }
      }

      const firstFrame = this.frames[0] || {};
      const startLon = firstFrame.longitude || winner?.longitude || 88.0;
      const startLat = firstFrame.latitude || winner?.latitude || 15.0;

      // Initialize dynamic 3D world position and heading orientation
      this.vehiclePos = Cesium.Cartesian3.fromDegrees(startLon, startLat, 2500.0);
      const initHeading = firstFrame.ground_track_deg != null ? firstFrame.ground_track_deg : (firstFrame.heading_deg || 0);
      const initPitch = firstFrame.pitch_deg || 0;
      this.vehicleOrient = Cesium.Transforms.headingPitchRollQuaternion(
        this.vehiclePos,
        new Cesium.HeadingPitchRoll(Cesium.Math.toRadians(initHeading), Cesium.Math.toRadians(initPitch), 0.0)
      );

      // ─── PROCEDURAL 3D VEHICLE MODEL (TRUE 3D GEOMETRY) ───

      if (ptypeLower.includes('usv') || ptypeLower.includes('asv')) {
        // ── USV / Saildrone 3D Model ──
        // 1. Trimaran Central Hull
        this.vehicleEnt = safeAddEntity(v, {
          id: 'mission_active_vehicle',
          position: new Cesium.CallbackProperty(() => this.vehiclePos, false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(1200.0, 5200.0, 500.0),
            material: Cesium.Color.fromCssColorString(colHex).withAlpha(0.95),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6)
          }
        });
        // 2. Rigid Wing Sail (extends vertically 4.6 km above waterline)
        this.vehicleWingSail = safeAddEntity(v, {
          id: 'mission_active_wingsail',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, 400.0, 2400.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(80.0, 1100.0, 4600.0),
            material: Cesium.Color.WHITE.withAlpha(0.96),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString(colHex).withAlpha(0.7)
          }
        });
        // 3. Port & Starboard Outrigger Floats
        this.vehicleFloatL = safeAddEntity(v, {
          id: 'mission_active_float_l',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(-1400.0, -200.0, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: { dimensions: new Cesium.Cartesian3(350.0, 4200.0, 350.0), material: Cesium.Color.fromCssColorString(colHex) }
        });
        this.vehicleFloatR = safeAddEntity(v, {
          id: 'mission_active_float_r',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(1400.0, -200.0, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: { dimensions: new Cesium.Cartesian3(350.0, 4200.0, 350.0), material: Cesium.Color.fromCssColorString(colHex) }
        });
        this.vehicleParts.push(this.vehicleWingSail, this.vehicleFloatL, this.vehicleFloatR);

      } else if (ptypeLower.includes('rov')) {
        // ── ROV Deep Submergence 3D Frame ──
        this.vehicleEnt = safeAddEntity(v, {
          id: 'mission_active_vehicle',
          position: new Cesium.CallbackProperty(() => this.vehiclePos, false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(2600.0, 3400.0, 1800.0),
            material: Cesium.Color.fromCssColorString(colHex).withAlpha(0.92),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6)
          }
        });
        this.vehicleFoam = safeAddEntity(v, {
          id: 'mission_active_foam',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, 0.0, 950.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: { dimensions: new Cesium.Cartesian3(2400.0, 3200.0, 500.0), material: Cesium.Color.fromCssColorString('#facc15') }
        });
        this.vehicleParts.push(this.vehicleFoam);

      } else {
        // ── AUV / UUV / Glider Hydrodynamic 3D Submersible ──
        const isGlider = ptypeLower.includes('glider');
        const hullRadii = isGlider
          ? new Cesium.Cartesian3(380.0, 2100.0, 380.0) // Glider: slender torpedo
          : new Cesium.Cartesian3(480.0, 2500.0, 480.0); // AUV/UUV: heavy torpedo

        // 1. Primary 3D Torpedo Fuselage (Ellipsoid aligned longitudinally with heading)
        this.vehicleEnt = safeAddEntity(v, {
          id: 'mission_active_vehicle',
          position: new Cesium.CallbackProperty(() => this.vehiclePos, false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          ellipsoid: {
            radii: hullRadii,
            material: Cesium.Color.fromCssColorString(colHex).withAlpha(0.95),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6)
          }
        });

        // 2. High-Visibility 3D Nose Cone / Sonar Array
        const noseColor = isGlider ? '#f59e0b' : '#0284c7';
        const noseY = isGlider ? 2000.0 : 2300.0;
        this.vehicleNose = safeAddEntity(v, {
          id: 'mission_active_nose',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, noseY, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          ellipsoid: {
            radii: new Cesium.Cartesian3(isGlider ? 320.0 : 400.0, 800.0, isGlider ? 320.0 : 400.0),
            material: Cesium.Color.fromCssColorString(noseColor).withAlpha(0.98),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.7)
          }
        });
        this.vehicleParts.push(this.vehicleNose);

        // 3. 3D Lateral Swept Wings / Dive Planes (Seen clearly from top view)
        const wingSpan = isGlider ? 7600.0 : 5200.0;
        const wingChord = isGlider ? 650.0 : 850.0;
        this.vehicleWings = safeAddEntity(v, {
          id: 'mission_active_wings',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, 250.0, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(wingSpan, wingChord, 80.0),
            material: Cesium.Color.fromCssColorString(isGlider ? '#0284c7' : colHex).withAlpha(0.92),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6)
          }
        });
        this.vehicleParts.push(this.vehicleWings);

        // 4. Vertical Tail Fin (Rudder)
        const tailY = isGlider ? -1600.0 : -1900.0;
        this.vehicleTail = safeAddEntity(v, {
          id: 'mission_active_tail',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, tailY, 700.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(75.0, 850.0, 1400.0),
            material: Cesium.Color.fromCssColorString(colHex).withAlpha(0.92),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.6)
          }
        });
        this.vehicleParts.push(this.vehicleTail);

        // 5. Stern Horizontal Elevators / Stabilizer
        this.vehicleElevators = safeAddEntity(v, {
          id: 'mission_active_elevators',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, tailY, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          box: {
            dimensions: new Cesium.Cartesian3(2400.0, 800.0, 70.0),
            material: Cesium.Color.fromCssColorString(isGlider ? '#0284c7' : colHex).withAlpha(0.88),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.5)
          }
        });
        this.vehicleParts.push(this.vehicleElevators);

        // 6. Dynamic Pulsing Propulsion Wake behind Stern
        this.vehicleWake = safeAddEntity(v, {
          id: 'mission_active_wake',
          position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, tailY - 1100.0, 0.0), false),
          orientation: new Cesium.CallbackProperty(() => this.vehicleOrient, false),
          ellipsoid: {
            radii: new Cesium.CallbackProperty(() => {
              const pulse = 320.0 + Math.sin(Date.now() * 0.009) * 110.0;
              return new Cesium.Cartesian3(pulse, 950.0, pulse);
            }, false),
            material: Cesium.Color.fromCssColorString(colHex).withAlpha(0.4)
          }
        });
        this.vehicleParts.push(this.vehicleWake);
      }

      if (this.vehicleEnt) {
        this.vehicleParts.push(this.vehicleEnt);
        // Default to TOP VIEW camera offset: looking directly down from 75km altitude
        this.vehicleEnt.viewFrom = this.topViewOffset;
      }

      // 7. Floating 3D Micro Telemetry HUD (Elevated cleanly above 3D model)
      this.vehicleTagEnt = safeAddEntity(v, {
        id: 'mission_active_tag',
        position: new Cesium.CallbackProperty(() => this.getPartWorldPosition(0.0, 0.0, 4200.0), false),
        billboard: {
          image: this._generateMicroTagCanvas(name, ptype, colHex),
          scale: 0.82,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          eyeOffset: new Cesium.Cartesian3(0, 0, -600.0),
          scaleByDistance: new Cesium.NearFarScalar(1.0e4, 0.9, 5.0e6, 0.65)
        }
      });
      if (this.vehicleTagEnt) this.vehicleParts.push(this.vehicleTagEnt);

      // 8. 3D Glowing Depth Sounding Pillar
      this.depthPillarPositions = [
        Cesium.Cartesian3.fromDegrees(startLon, startLat, 2500.0),
        Cesium.Cartesian3.fromDegrees(startLon, startLat, 0.0)
      ];
      this.depthPillarEnt = safeAddEntity(v, {
        id: 'mission_playback_depth_pillar',
        polyline: {
          positions: new Cesium.CallbackProperty(() => this.depthPillarPositions, false),
          width: 3.5,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.4,
            color: Cesium.Color.fromCssColorString(colHex).withAlpha(0.85)
          })
        }
      });

      // 9. Dynamic Breadcrumb Trail (Completed Track)
      this.completedPositions = [Cesium.Cartesian3.fromDegrees(startLon, startLat, 1000.0)];
      this.trailEnt = safeAddEntity(v, {
        id: 'mission_playback_trail',
        polyline: {
          positions: new Cesium.CallbackProperty(() => this.completedPositions, false),
          width: 4.0,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.35,
            color: Cesium.Color.fromCssColorString(colHex)
          })
        }
      });

      // Register with global adaptiveState for cleanup
      this.vehicleParts.forEach(p => {
        if (p && !window.adaptiveState.missionEntities.includes(p)) {
          window.adaptiveState.missionEntities.push(p);
        }
      });
      if (this.depthPillarEnt) window.adaptiveState.missionEntities.push(this.depthPillarEnt);
      if (this.trailEnt) window.adaptiveState.missionEntities.push(this.trailEnt);
    }

    async start() {
      this.running = true;
      this.paused = false;
      this.frameIdx = 0;
      this.sampleIdx = 0;
      this.state = 'TRANSIT';
      this.lastTs = 0;
      this.cameraFollow = true;

      // Hide hint & depth display banner to prevent overlapping HUD elements
      const hint = document.getElementById('hint');
      if (hint) hint.style.display = 'none';
      const depthBanner = document.getElementById('depthDisplayBanner');
      if (depthBanner) depthBanner.style.display = 'none';

      // Ensure side panels are closed during 3D mission playback
      const profPanel = document.getElementById('profilePanel');
      if (profPanel) profPanel.classList.remove('open');
      const admPanel = document.getElementById('adaptiveMissionPanel');
      if (admPanel) admPanel.classList.remove('open');

      // Show HUDs
      document.getElementById('phaseTimeline').style.display = 'flex';
      document.getElementById('cinematicBanner').style.display = 'flex';
      document.getElementById('missionTelemetryHud').style.display = 'flex';
      document.getElementById('adaptiveWaterColumnOverlay').style.display = 'flex';
      document.getElementById('missionPlaybackBar').style.display = 'flex';

      document.getElementById('btnPbPlay').textContent = '⏸';

      this.createVehicleModel();
      this.updateCameraFollowUI();

      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      const firstFrame = this.frames[0];
      const targetGap = this.sim.target || (this.sim.target_gap || {});

      if (firstFrame) {
        this.updateFrame(firstFrame);
      }

      setActivePhase(5);
      updateCinematicBanner(
        'PHASE 06 — MISSION DEPLOYMENT',
        'CONTROLLABLE OBSERVING PLATFORM DEPLOYED',
        `${this.sim.selected_platform?.name || 'Observing platform'} departed position toward target gap.`
      );

      // Smooth camera framing: show FULL route end-to-end first, then lock onto vehicle
      if (v && v.camera && firstFrame) {
        const tLon = (targetGap && targetGap.longitude) || firstFrame.longitude;
        const tLat = (targetGap && targetGap.latitude) || firstFrame.latitude;
        const midLon = (firstFrame.longitude + tLon) / 2.0;
        const midLat = (firstFrame.latitude + tLat) / 2.0;

        // Great-circle distance in km → drive altitude so both ends fit in frame
        const dLon = (tLon - firstFrame.longitude) * Math.PI / 180.0;
        const dLat = (tLat - firstFrame.latitude) * Math.PI / 180.0;
        const sinDLat = Math.sin(dLat / 2.0);
        const sinDLon = Math.sin(dLon / 2.0);
        const a = sinDLat * sinDLat +
          Math.cos(firstFrame.latitude * Math.PI / 180.0) *
          Math.cos(tLat * Math.PI / 180.0) *
          sinDLon * sinDLon;
        const distKm = 6371.0 * 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));

        // Altitude: 1.8× the great-circle distance, clamped between 120 km and 1200 km
        const overviewAlt = Math.max(120000.0, Math.min(1200000.0, distKm * 1800.0));

        v.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(midLon, midLat, overviewAlt),
          orientation: {
            heading: Cesium.Math.toRadians(firstFrame.heading_deg || 0),
            pitch: Cesium.Math.toRadians(-85.0), // Top-down view to see the full route path
            roll: 0.0
          },
          duration: 1.8,
          complete: () => {
            // After 2 s overview, shrink down to the vehicle and start tracking
            if (!this.running) return;
            setTimeout(() => {
              if (!this.running) return;
              v.camera.flyTo({
                destination: Cesium.Cartesian3.fromDegrees(
                  this.currentFrame?.longitude ?? firstFrame.longitude,
                  this.currentFrame?.latitude ?? firstFrame.latitude,
                  75000.0
                ),
                orientation: {
                  heading: Cesium.Math.toRadians(this.currentFrame?.heading_deg || firstFrame.heading_deg || 0),
                  pitch: Cesium.Math.toRadians(-85.0),
                  roll: 0.0
                },
                duration: 1.2,
                complete: () => {
                  if (this.running && this.cameraFollow && v && this.vehicleEnt) {
                    this.vehicleEnt.viewFrom = this.topViewOffset;
                    v.trackedEntity = this.vehicleEnt;
                  }
                }
              });
            }, 2000);
          }
        });
      } else {
        this.setCameraFollow(true);
      }

      // Initial pacing pause: 1.6 seconds for route framing & deployment
      await new Promise(r => setTimeout(r, 1600));
      if (!this.running) return;

      requestAnimationFrame(ts => this.tick(ts));
    }

    setCameraFollow(enable) {
      this.cameraFollow = !!enable;
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (v) {
        if (this.cameraFollow && this.vehicleEnt) {
          this.camMode = this.camMode === 'FREE' ? 'TOP' : this.camMode;
          this.vehicleEnt.viewFrom = this.camMode === 'TOP' ? this.topViewOffset : this.chaseViewOffset;
          v.trackedEntity = this.vehicleEnt;
        } else {
          this.camMode = 'FREE';
          v.trackedEntity = undefined;
          if (v.camera) {
            v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          }
        }
      }
      this.updateCameraFollowUI();
    }

    cycleCameraMode() {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v) return;

      if (this.camMode === 'TOP') {
        // Switch to Chase 3D (Elevated perspective)
        this.camMode = 'CHASE';
        this.cameraFollow = true;
        if (this.vehicleEnt) {
          this.vehicleEnt.viewFrom = this.chaseViewOffset;
          v.trackedEntity = this.vehicleEnt;
        }
      } else if (this.camMode === 'CHASE') {
        // Switch to Free Orbit
        this.camMode = 'FREE';
        this.cameraFollow = false;
        v.trackedEntity = undefined;
        if (v.camera) v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
      } else {
        // Switch back to Top View (Default)
        this.camMode = 'TOP';
        this.cameraFollow = true;
        if (this.vehicleEnt) {
          this.vehicleEnt.viewFrom = this.topViewOffset;
          v.trackedEntity = this.vehicleEnt;
        }
      }
      this.updateCameraFollowUI();
    }

    updateCameraFollowUI() {
      const btn = document.getElementById('btnPbCamMode');
      const icon = document.getElementById('pbCamModeIcon');
      const text = document.getElementById('pbCamModeText');
      if (btn) {
        if (this.camMode === 'TOP') {
          btn.classList.remove('free');
          btn.style.borderColor = '#38bdf8';
          btn.style.background = 'rgba(56, 189, 248, 0.2)';
          btn.style.color = '#38bdf8';
          if (icon) icon.textContent = '🛰️';
          if (text) text.textContent = 'Camera: Top View';
          btn.title = 'Current View: Top-Down Aerial (85° Overhead). Click to switch to Chase 3D.';
        } else if (this.camMode === 'CHASE') {
          btn.classList.remove('free');
          btn.style.borderColor = 'var(--adm-accent)';
          btn.style.background = 'rgba(245, 158, 11, 0.2)';
          btn.style.color = 'var(--adm-accent)';
          if (icon) icon.textContent = '🎥';
          if (text) text.textContent = 'Camera: Chase 3D';
          btn.title = 'Current View: Chase 3D (Elevated Chase Angle). Click to switch to Free Orbit.';
        } else {
          btn.classList.add('free');
          btn.style.borderColor = 'rgba(255, 255, 255, 0.25)';
          btn.style.background = 'rgba(255, 255, 255, 0.08)';
          btn.style.color = '#94a3b8';
          if (icon) icon.textContent = '🌐';
          if (text) text.textContent = 'Camera: Free Orbit';
          btn.title = 'Current View: Free Orbit (Manual Mouse Drag & Pan). Click to switch to Top View.';
        }
      }
    }

    tick(ts) {
      if (!this.running) return;
      if (this.paused) return;

      if (!this.lastTs) this.lastTs = ts;
      const delta = (ts - this.lastTs) / 1000.0;
      const effectiveSpeed = Math.max(0.2, this.speed || 1.0);

      if (this.state === 'TRANSIT') {
        const frameInterval = 0.14 / effectiveSpeed;
        if (delta >= frameInterval) {
          this.lastTs = ts;
          if (this.frameIdx < this.frames.length) {
            const frame = this.frames[this.frameIdx];
            this.updateFrame(frame);
            this.frameIdx++;
          } else {
            // Arrived at target gap! Transition to 3D Depth Sampling
            this.state = 'SAMPLING';
            this.sampleIdx = 0;
            this.lastTs = ts;
            if (this.vehicleEnt) {
              if (this.camMode === 'TOP') {
                this.vehicleEnt.viewFrom = new Cesium.Cartesian3(0.0, -1500.0, 42000.0);
              } else if (this.camMode === 'CHASE') {
                this.vehicleEnt.viewFrom = new Cesium.Cartesian3(0.0, -22000.0, 18000.0);
              }
            }
          }
        }
      } else if (this.state === 'SAMPLING') {
        const sampleInterval = 1.0 / effectiveSpeed;
        if (delta >= sampleInterval) {
          this.lastTs = ts;
          if (this.sampleIdx < this.samples.length) {
            const sample = this.samples[this.sampleIdx];
            this.updateSamplingStep(sample);
            this.sampleIdx++;
          } else {
            // Transition to Bayesian Gap Reassessment
            this.state = 'REASSESS';
            this.showGapReassessment();
            this.lastTs = ts;
          }
        }
      } else if (this.state === 'REASSESS') {
        const reassessInterval = 1.2 / effectiveSpeed;
        if (delta >= reassessInterval) {
          this.completeMission();
          return;
        }
      }

      requestAnimationFrame(t => this.tick(t));
    }

    updateFrame(frame) {
      if (!frame) return;
      this.currentFrame = frame;

      // 1. Dynamic 3D Position
      this.vehiclePos = Cesium.Cartesian3.fromDegrees(frame.longitude, frame.latitude, 2500.0);

      // 2. Dynamic 3D Heading & Pitch Orientation
      const headingDeg = frame.ground_track_deg != null ? frame.ground_track_deg : (frame.heading_deg || 0);
      const pitchDeg = frame.pitch_deg || 0;
      const rollDeg = frame.roll_deg || 0;
      const hpr = new Cesium.HeadingPitchRoll(
        Cesium.Math.toRadians(headingDeg),
        Cesium.Math.toRadians(pitchDeg),
        Cesium.Math.toRadians(rollDeg)
      );
      this.vehicleOrient = Cesium.Transforms.headingPitchRollQuaternion(this.vehiclePos, hpr);

      // 3. 3D Depth Sounding Pillar
      const vertExagg = (window.state && window.state.verticalExaggeration) || 1.0;
      const curDepth = frame.depth_m || 0;
      this.depthPillarPositions = Cesium.Cartesian3.fromDegreesArrayHeights([
        frame.longitude, frame.latitude, 2500.0,
        frame.longitude, frame.latitude, -curDepth * 4.0 * vertExagg
      ]);

      // 4. Dynamic Breadcrumb Trail
      this.completedPositions.push(Cesium.Cartesian3.fromDegrees(frame.longitude, frame.latitude, 1000.0));

      // 5. Update Micro Tag periodically
      if (this.frameIdx % 4 === 0 && this.vehicleTagEnt && this.vehicleTagEnt.billboard) {
        this.vehicleTagEnt.billboard.image = this._generateMicroTagCanvas(
          this.vehicleName,
          this.vehiclePType,
          this.vehicleColorHex
        );
      }

      // 6. Telemetry HUD Readout
      const telDepth = document.getElementById('telDepthVal');
      if (telDepth) telDepth.textContent = `${curDepth.toFixed(0)} m [SIM]`;
      const telSpeed = document.getElementById('telSpeedVal');
      if (telSpeed) telSpeed.textContent = `${(frame.effective_speed_mps || 0.35).toFixed(2)} m/s [SIM]`;
      const telHeading = document.getElementById('telHeadingVal');
      if (telHeading) telHeading.textContent = `${(frame.heading_deg || 0).toFixed(0)}° [SIM]`;
      const telBatt = document.getElementById('telBattVal');
      if (telBatt) telBatt.textContent = `${(frame.battery_percent || 80).toFixed(1)}% [SIM]`;
      const telBattFill = document.getElementById('telBattFill');
      if (telBattFill) telBattFill.style.width = `${frame.battery_percent || 80}%`;

      const baseTemp = this.sim.target_gap?.model_value || 28.2;
      const tempC = Math.max(4.0, baseTemp - (curDepth * 0.024));
      const salPSU = 34.8 + (curDepth * 0.0003);
      const pressDbar = curDepth * 0.101 + 10.0;

      const telTemp = document.getElementById('telTempVal');
      if (telTemp) telTemp.textContent = `${tempC.toFixed(2)} °C [SIM]`;
      const telSal = document.getElementById('telSalVal');
      if (telSal) telSal.textContent = `${salPSU.toFixed(2)} PSU [SIM]`;
      const telPress = document.getElementById('telPressVal');
      if (telPress) telPress.textContent = `${pressDbar.toFixed(1)} dbar [SIM]`;

      // 6. Scrubber & Time Display
      const totalSteps = Math.max(1, this.frames.length + this.samples.length + 1);
      const scrubber = document.getElementById('timelineScrubber');
      if (scrubber) scrubber.value = Math.floor((this.frameIdx / totalSteps) * 1000);
      const pbTime = document.getElementById('playbackTime');
      if (pbTime) pbTime.textContent = `T+ ${Math.floor(frame.elapsed_hours || 0)}h ${Math.floor(((frame.elapsed_hours || 0) % 1) * 60)}m`;

      // 7. Synchronize Right-Panel Three.js Digital Twin
      if (typeof wcVehicleGroup !== 'undefined' && wcVehicleGroup) {
        const CYL_H = 3.4;
        const normDepth = Math.max(0.0, Math.min(1.0, curDepth / 2000.0));
        wcVehicleGroup.position.set(0, -normDepth * CYL_H, 0);
      }

      // 8. Phase & Banner updates
      if (curDepth > 0) {
        setActivePhase(8); // 3D Descent
        updateCinematicBanner(
          'PHASE 09 — 3D DEPTH DIVE & PROFILING [SIMULATED]',
          `UNDERWATER DESCENT TO ${curDepth.toFixed(0)} METERS [SIMULATED]`,
          'Simulated platform diving through thermocline collecting continuous physical parameters…'
        );
        this.updateWaterColumnRuler(curDepth);

        if (this.frameIdx % 3 === 0) {
          this.emitSonarPulse(frame.latitude, frame.longitude, curDepth);
        }
      } else {
        setActivePhase(6); // Transit
        updateCinematicBanner(
          'PHASE 07 — TRANSIT ALONG CURRENT-AFFECTED ROUTE [SIMULATED]',
          `EN ROUTE: ${(frame.distance_remaining_km || 0).toFixed(1)} KM REMAINING [SIM]`,
          `Ground Track: ${(frame.ground_track_deg || 0).toFixed(0)}° | Speed: ${(frame.effective_speed_mps || 0.35).toFixed(2)} m/s [SIM]`
        );
      }
    }

    seekPercent(ratio) {
      if (!this.frames || !this.frames.length) return;
      const totalSteps = Math.max(1, this.frames.length + this.samples.length + 1);
      const targetStep = Math.max(0, Math.min(totalSteps - 1, Math.floor(ratio * (totalSteps - 1))));

      if (targetStep < this.frames.length) {
        this.state = 'TRANSIT';
        this.frameIdx = targetStep;
        this.sampleIdx = 0;
        this.completedPositions = [];
        for (let i = 0; i <= targetStep; i++) {
          const f = this.frames[i];
          if (f) this.completedPositions.push(Cesium.Cartesian3.fromDegrees(f.longitude, f.latitude, 1000.0));
        }
        this.updateFrame(this.frames[targetStep]);
      } else {
        this.state = 'SAMPLING';
        this.frameIdx = this.frames.length;
        const sIdx = Math.min(this.samples.length - 1, targetStep - this.frames.length);
        this.sampleIdx = sIdx;
        this.completedPositions = [];
        for (let i = 0; i < this.frames.length; i++) {
          const f = this.frames[i];
          if (f) this.completedPositions.push(Cesium.Cartesian3.fromDegrees(f.longitude, f.latitude, 1000.0));
        }
        if (this.frames.length > 0) {
          this.updateFrame(this.frames[this.frames.length - 1]);
        }
        if (this.samples[sIdx]) {
          this.updateSamplingStep(this.samples[sIdx]);
        }
      }
      this.lastTs = 0;

      // BUG-01/04/09 FIX: If playback is running and not paused, restart the tick loop
      // (seeking kills the previous rAF chain — we must re-launch it)
      if (this.running && !this.paused) {
        requestAnimationFrame(ts => this.tick(ts));
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
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v) return;
      const pulseEnt = safeAddEntity(v, {
        id: `sonar_pulse_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 100.0),
        ellipse: {
          semiMajorAxis: 3000,
          semiMinorAxis: 3000,
          height: 100,
          material: Cesium.Color.fromCssColorString('#3fe0c5').withAlpha(0.6),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#3fe0c5')
        }
      });
      if (pulseEnt) {
        window.adaptiveState.missionEntities.push(pulseEnt);
        setTimeout(() => {
          try { v.entities.remove(pulseEnt); } catch(e) {}
        }, 1200);
      }
    }

    updateSamplingStep(sample) {
      if (!sample) return;
      setActivePhase(10);
      updateCinematicBanner(
        'PHASE 11 — SENSOR SAMPLING AT TARGET HORIZON [SIMULATED SOUNDINGS]',
        `ACQUIRING SYNTHETIC SOUNDING AT ${sample.depth_m} METERS [SIMULATED]`,
        `T: ${sample.temperature_c}°C | S: ${sample.salinity_psu} PSU | Pressure: ${sample.pressure_dbar} dbar (Simulated data stream)`
      );

      const telDepth = document.getElementById('telDepthVal');
      if (telDepth) telDepth.textContent = `${sample.depth_m} m [SIM]`;
      const telTemp = document.getElementById('telTempVal');
      if (telTemp) telTemp.textContent = `${sample.temperature_c} °C [SIM]`;
      const telSal = document.getElementById('telSalVal');
      if (telSal) telSal.textContent = `${sample.salinity_psu} PSU [SIM]`;
      const telPress = document.getElementById('telPressVal');
      if (telPress) telPress.textContent = `${sample.pressure_dbar} dbar [SIM]`;
      const telOxy = document.getElementById('telOxyVal');
      if (telOxy) telOxy.textContent = '194 µmol/kg [SIM]';
      const telChl = document.getElementById('telChlVal');
      if (telChl) telChl.textContent = '0.52 mg/m³ [SIM]';

      // Update Sounding Pillar to this sample depth
      const vertExagg = (window.state && window.state.verticalExaggeration) || 1.0;
      const target = this.sim.target || (this.sim.target_gap || {});
      const tLon = target.longitude || (this.currentFrame && this.currentFrame.longitude) || 88.7;
      const tLat = target.latitude || (this.currentFrame && this.currentFrame.latitude) || 15.4;

      this.depthPillarPositions = Cesium.Cartesian3.fromDegreesArrayHeights([
        tLon, tLat, 2500.0,
        tLon, tLat, -sample.depth_m * 4.0 * vertExagg
      ]);

      this.updateWaterColumnRuler(sample.depth_m);

      // Animate right-panel Three.js twin
      if (typeof wcVehicleGroup !== 'undefined' && wcVehicleGroup) {
        const CYL_H = 3.4;
        const normDepth = Math.max(0.0, Math.min(1.0, sample.depth_m / 2000.0));
        wcVehicleGroup.position.set(0, -normDepth * CYL_H, 0);
      }

      this.emitSonarPulse(tLat, tLon, sample.depth_m);

      // Scrubber update
      const totalSteps = Math.max(1, this.frames.length + this.samples.length + 1);
      const curStep = this.frames.length + this.sampleIdx;
      const scrubber = document.getElementById('timelineScrubber');
      if (scrubber) scrubber.value = Math.floor((curStep / totalSteps) * 1000);
    }

    showGapReassessment() {
      setActivePhase(12);
      const before = this.sim.before_simulation?.information_gap_percent || 86;
      const after = this.sim.after_simulation?.information_gap_percent || 24;
      const gain = this.sim.scientific_payoff?.expected_information_gain_percent || 38;

      updateCinematicBanner(
        'PHASE 13 — INFORMATION GAP REASSESSED [SIMULATION]',
        `BAYESIAN UNCERTAINTY REDUCTION: ${before}% → ${after}%`,
        `Synthetic deep soundings assimilated into 3D Digital Twin. Expected Information Gain: +${gain}%.`
      );

      // Visually shrink and turn gap green
      const gap = window.adaptiveState.selectedGap;
      if (gap) {
        gap.isResolved = true;
        gap.priority_score = after;
        gap.priority_level = 'RESOLVED';
        clearGapEntities();
        renderGapEntitiesOnGlobe();
      }
    }

    completeMission() {
      this.running = false;
      this.cameraFollow = false;
      document.getElementById('btnPbPlay').textContent = '▶';
      setActivePhase(13);
      updateCinematicBanner(
        'PHASE 14 — MISSION COMPLETE & GAP RESOLVED [SIMULATION]',
        'DIGITAL TWIN REASSESSED & UNCERTAINTY REDUCED',
        'Synthetic deep ocean soundings ingested. Bayesian posterior uncertainty updated.'
      );

      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (v) {
        v.trackedEntity = undefined;
        if (v.camera) {
          if (v.camera._flight) v.camera.cancelFlight();
          v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
        }
      }

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

      // Hide ALL overlapping HUD overlays and banners when mission completes
      // (phaseTimeline and cinematicBanner were missing — they blocked panel clicks)
      const wcOverlay = document.getElementById('adaptiveWaterColumnOverlay');
      if (wcOverlay) wcOverlay.style.display = 'none';
      const telHud = document.getElementById('missionTelemetryHud');
      if (telHud) telHud.style.display = 'none';
      const pbBar = document.getElementById('missionPlaybackBar');
      if (pbBar) pbBar.style.display = 'none';
      const phaseBar = document.getElementById('phaseTimeline');
      if (phaseBar) phaseBar.style.display = 'none';
      const cinBanner = document.getElementById('cinematicBanner');
      if (cinBanner) cinBanner.style.display = 'none';

      // Ensure OBSERVATION INFO profile panel and adaptive panel are NOT auto opened
      const profPanel = document.getElementById('profilePanel');
      if (profPanel) profPanel.classList.remove('open');
      const admPanel = document.getElementById('adaptiveMissionPanel');
      if (admPanel) admPanel.classList.remove('open');

      // Show Summary Modal (closeMissionSummaryModal will call destroy() for full cleanup)
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
      requestAnimationFrame(ts => this.tick(ts));
    }

    restart() {
      this.destroy();
      window.executeAdaptiveMission();
    }

    destroy() {
      this.running = false;
      this.cameraFollow = false;
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (v) {
        v.trackedEntity = undefined;
        if (v.camera) {
          if (v.camera._flight) v.camera.cancelFlight();
          v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
        }
      }
      if (this.vehicleParts && v) {
        this.vehicleParts.forEach(p => {
          try { v.entities.remove(p); } catch(e) {}
        });
        this.vehicleParts = [];
      }
      if (this.vehicleEnt && v) try { v.entities.remove(this.vehicleEnt); } catch(e){}
      if (this.depthPillarEnt && v) try { v.entities.remove(this.depthPillarEnt); } catch(e){}
      if (this.trailEnt && v) try { v.entities.remove(this.trailEnt); } catch(e){}
      this.vehicleEnt = null;
      this.depthPillarEnt = null;
      this.trailEnt = null;
      this.completedPositions = [];
      clearMissionGraphics();

      if (this.hiddenEntities) {
        this.hiddenEntities.forEach(ent => {
          try { ent.show = true; } catch(e) {}
        });
        this.hiddenEntities = [];
      }

      const hint = document.getElementById('hint');
      if (hint) hint.style.display = '';
      const depthBanner = document.getElementById('depthDisplayBanner');
      if (depthBanner) depthBanner.style.display = '';
      const wcOverlay = document.getElementById('adaptiveWaterColumnOverlay');
      if (wcOverlay) wcOverlay.style.display = 'none';
      const telHud = document.getElementById('missionTelemetryHud');
      if (telHud) telHud.style.display = 'none';
      const pbBar = document.getElementById('missionPlaybackBar');
      if (pbBar) pbBar.style.display = 'none';
      const cinBanner = document.getElementById('cinematicBanner');
      if (cinBanner) cinBanner.style.display = 'none';
      const ptLine = document.getElementById('phaseTimeline');
      if (ptLine) ptLine.style.display = 'none';
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
    // Ensure OBSERVATION INFO profile panel and adaptive panel remain closed
    const profPanel = document.getElementById('profilePanel');
    if (profPanel) profPanel.classList.remove('open');
    const admPanel = document.getElementById('adaptiveMissionPanel');
    if (admPanel) admPanel.classList.remove('open');
    const hint = document.getElementById('hint');
    if (hint) hint.style.display = '';
    const depthBanner = document.getElementById('depthDisplayBanner');
    if (depthBanner) depthBanner.style.display = '';
    if (window.adaptiveState && window.adaptiveState.playback) {
      window.adaptiveState.playback.destroy();
    }
  };

  // ─── DOM Events Hookup ─────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    // Play Mission button in panel
    const btnPlay = document.getElementById('btnAdaptivePlayMission');
    if (btnPlay) btnPlay.onclick = window.startAdaptiveMissionPlanning;

    // Execute Simulation button
    const btnExec = document.getElementById('btnAdaptiveExecuteSim');
    if (btnExec) btnExec.onclick = window.executeAdaptiveMission;

    // Close panel button — always closes regardless of camera state
    const btnClosePanel = document.getElementById('btnCloseAdaptivePanel');
    if (btnClosePanel) {
      btnClosePanel.onclick = () => {
        // 1. Close the panel first — unconditionally
        const panel = document.getElementById('adaptiveMissionPanel');
        if (panel) panel.classList.remove('open');

        // 2. Also clean up any lingering simulation HUDs that could block the globe
        const hids = ['phaseTimeline', 'cinematicBanner', 'missionTelemetryHud',
                       'adaptiveWaterColumnOverlay', 'missionPlaybackBar'];
        hids.forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.display = 'none';
        });

        // 3. Release camera lock (safe — wrapped so a locked camera can't block the close)
        try {
          const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
          if (v && v.camera) {
            if (v.trackedEntity) v.trackedEntity = undefined;
            v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          }
        } catch (e) { /* camera unlock failed — panel is already closed, safe to ignore */ }
      };
    }

    // Playback bar Camera Mode button
    const btnCamMode = document.getElementById('btnPbCamMode');
    if (btnCamMode) {
      btnCamMode.onclick = () => {
        const pb = window.adaptiveState.playback;
        if (pb) {
          pb.cycleCameraMode();
        }
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

    // Timeline Scrubber Seeking
    const scrubber = document.getElementById('timelineScrubber');
    if (scrubber) {
      scrubber.oninput = (e) => {
        const pb = window.adaptiveState.playback;
        if (pb) {
          pb.seekPercent(parseFloat(e.target.value) / 1000.0);
        }
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
