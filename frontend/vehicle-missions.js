/**
 * OCEAN 3D — Autonomous Underwater Vehicle (AUV), Uncrewed Underwater Vehicle (UUV),
 * and Remotely Operated Vehicle (ROV) Observation & Mission Planning Module.
 *
 * Provides:
 * 1. 3D Globe Pinning with vertical depth sounding pillars.
 * 2. Instrument Information Panel & Telemetry Viewer.
 * 3. Interactive Globe-Click Targeting & Route Generation.
 * 4. 3D Water-Column Depth Mission & Digital Twin Visualization.
 * 5. Realistic Mission Simulation (AVAILABLE -> MISSION_PLANNED -> EN_ROUTE -> DIVING -> SAMPLING -> TARGET_REACHED -> DATA_COLLECTED).
 * 6. In-Situ / Baseline Ocean Observation Data Collection.
 * 7. Observation / Vehicle Layer Filters and Map Legend.
 *
 * NOTE: All vehicle trajectories, positions, and commands are SIMULATED for autonomous
 * ocean mission planning unless connected to an authorized live telemetry feed.
 */

(function(window) {
  'use strict';

  // Distinct styling specifications for each vehicle type
  const VEHICLE_CONFIG = {
    AUV: {
      label: 'AUV (Autonomous Underwater Vehicle)',
      shortLabel: 'AUV',
      colorCss: '#00e5ff',
      cesiumColor: Cesium.Color.fromCssColorString('#00e5ff'),
      altColor: '#0891b2',
      badgeClass: 'auv',
      defaultDepth: 650,
      iconSymbol: '⬡'
    },
    UUV: {
      label: 'UUV (Uncrewed Underwater Vehicle)',
      shortLabel: 'UUV',
      colorCss: '#a855f7',
      cesiumColor: Cesium.Color.fromCssColorString('#a855f7'),
      altColor: '#7c3aed',
      badgeClass: 'uuv',
      defaultDepth: 250,
      iconSymbol: '⬢'
    },
    ROV: {
      label: 'ROV (Remotely Operated Vehicle)',
      shortLabel: 'ROV',
      colorCss: '#ff9100',
      cesiumColor: Cesium.Color.fromCssColorString('#ff9100'),
      altColor: '#ea580c',
      badgeClass: 'rov',
      defaultDepth: 1800,
      iconSymbol: '⬡'
    }
  };

  class VehicleMissionManager {
    constructor() {
      this.vehicles = [];
      this.selectedVehicle = null;
      this.activeMission = null;
      this.isSelectingTarget = false;
      this.simulationInterval = null;

      // Cesium entities cache
      this.vehicleEntities = [];
      this.pillarEntities = [];
      this.routeEntities = [];
      this.targetEntity = null;
      this.targetPulseEntity = null;

      // Filter states
      this.filters = {
        AUV: true,
        UUV: true,
        ROV: true
      };
      this.showLabels = false;

      this._init();
    }

    async _init() {
      try {
        await this.fetchVehicles();
        this._setupGlobeIntegration();
        this._setupFilterListeners();
      } catch (err) {
        console.warn('VehicleMissionManager initialization deferred:', err);
      }
    }

    async fetchVehicles() {
      const endpoint = (typeof apiUrl === 'function') ? apiUrl('/api/vehicles') : '/api/vehicles';
      const res = await fetch(endpoint);
      if (!res.ok) throw new Error('Failed to fetch vehicle fleet');
      this.vehicles = await res.json();
      this.updateVehicleCounts();
      this.renderVehiclesOnGlobe();
    }

    updateVehicleCounts() {
      const counts = { AUV: 0, UUV: 0, ROV: 0 };
      this.vehicles.forEach(v => {
        if (counts[v.type] !== undefined) counts[v.type]++;
      });
      const elAuv = document.getElementById('cntAuv');
      const elUuv = document.getElementById('cntUuv');
      const elRov = document.getElementById('cntRov');
      if (elAuv) elAuv.textContent = counts.AUV;
      if (elUuv) elUuv.textContent = counts.UUV;
      if (elRov) elRov.textContent = counts.ROV;
    }

    _setupGlobeIntegration() {
      const checkViewer = () => {
        const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
        if (v && v.entities) {
          this.renderVehiclesOnGlobe();
        } else {
          setTimeout(checkViewer, 400);
        }
      };
      checkViewer();
    }

    _setupFilterListeners() {
      ['ovAUV', 'ovUUV', 'ovROV'].forEach(id => {
        const chk = document.getElementById(id);
        if (chk) {
          chk.addEventListener('change', (e) => {
            const vType = id.replace('ov', '').toUpperCase();
            this.filters[vType] = e.target.checked;
            this.applyFilters();
          });
        }
      });
    }

    applyFilters() {
      this.vehicleEntities.forEach(ent => {
        if (ent.vehicleData) {
          const isAllowed = this.filters[ent.vehicleData.type] !== false;
          ent.show = isAllowed;
        }
      });
      this.pillarEntities.forEach(ent => {
        if (ent.vehicleData) {
          const isAllowed = this.filters[ent.vehicleData.type] !== false;
          ent.show = isAllowed;
        }
      });
    }

    // ── 1. GLOBE RENDERING & 3D VERTICAL DEPTH REPRESENTATION ───────────────

    _generateVehicleIconCanvas(vehicle) {
      const canvas = document.createElement('canvas');
      canvas.width = 24;
      canvas.height = 24;
      const ctx = canvas.getContext('2d');
      const cfg = VEHICLE_CONFIG[vehicle.type] || VEHICLE_CONFIG.AUV;

      // Simple glowing colored dot — no text label
      ctx.shadowColor = cfg.colorCss;
      ctx.shadowBlur = 10;
      ctx.fillStyle = cfg.colorCss;
      ctx.beginPath();
      ctx.arc(12, 12, 7, 0, Math.PI * 2);
      ctx.fill();

      ctx.shadowBlur = 0;
      ctx.strokeStyle = 'rgba(255,255,255,0.7)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      return canvas.toDataURL();
    }

    _generateVehicleBadgeCanvas(vehicle) {
      const canvas = document.createElement('canvas');
      canvas.width = 180;
      canvas.height = 68;
      const ctx = canvas.getContext('2d');
      const cfg = VEHICLE_CONFIG[vehicle.type] || VEHICLE_CONFIG.AUV;

      // Glow background box
      ctx.fillStyle = 'rgba(7, 16, 25, 0.94)';
      ctx.strokeStyle = cfg.colorCss;
      ctx.lineWidth = 2;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(4, 4, 172, 60, 6);
      else ctx.rect(4, 4, 172, 60);
      ctx.fill();
      ctx.stroke();

      // Type Badge Header Tag
      ctx.fillStyle = cfg.colorCss;
      ctx.font = 'bold 10px "IBM Plex Mono", monospace';
      ctx.fillText(`[${vehicle.type}] ${vehicle.id}`, 10, 20);

      // Status pill
      ctx.fillStyle = vehicle.status === 'AVAILABLE' ? '#34d399' : '#fbbf24';
      ctx.font = 'bold 9px "IBM Plex Mono", monospace';
      ctx.fillText(`● ${vehicle.status}`, 110, 20);

      // Depth line
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 12px "IBM Plex Mono", monospace';
      ctx.fillText(`Depth: ${vehicle.depth} m`, 10, 39);

      // Provenance badge
      ctx.fillStyle = '#94a3b8';
      ctx.font = '9px "IBM Plex Mono", monospace';
      ctx.fillText(`SIMULATED SUBSEA ASSET`, 10, 54);

      return canvas.toDataURL();
    }

    toggleVehicleLabels(show) {
      this.showLabels = (show !== undefined) ? !!show : !this.showLabels;
      this.renderVehiclesOnGlobe();
      return this.showLabels;
    }

    renderVehiclesOnGlobe() {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v || !v.entities) return;

      // Clear existing vehicle entities
      this.vehicleEntities.forEach(e => { try { v.entities.remove(e); } catch(err){} });
      this.pillarEntities.forEach(e => { try { v.entities.remove(e); } catch(err){} });
      this.vehicleEntities = [];
      this.pillarEntities = [];

      this.vehicles.forEach(veh => {
        const cfg = VEHICLE_CONFIG[veh.type] || VEHICLE_CONFIG.AUV;
        const pos = Cesium.Cartesian3.fromDegrees(veh.longitude, veh.latitude, 3000.0);
        const markerImg = this.showLabels 
          ? this._generateVehicleBadgeCanvas(veh)
          : this._generateVehicleIconCanvas(veh);

        // 1. Vehicle Billboard & Marker Pin
        const entity = v.entities.add({
          id: `veh_${veh.id}`,
          position: pos,
          billboard: {
            image: markerImg,
            scale: this.showLabels ? 0.82 : 0.95,
            verticalOrigin: this.showLabels ? Cesium.VerticalOrigin.BOTTOM : Cesium.VerticalOrigin.CENTER,
            scaleByDistance: new Cesium.NearFarScalar(1.0e5, 1.0, 2.0e7, 0.6)
          },
          show: this.filters[veh.type] !== false
        });
        entity.vehicleData = veh;
        this.vehicleEntities.push(entity);

        // 2. 3D Depth Sounding Pillar descending down to vehicle's actual depth
        const vertExagg = (window.state && window.state.verticalExaggeration) || 1.0;
        const targetDepthAlt = -veh.depth * 4.0 * vertExagg;

        const pillar = v.entities.add({
          id: `veh_pillar_${veh.id}`,
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArrayHeights([
              veh.longitude, veh.latitude, 3000.0,
              veh.longitude, veh.latitude, targetDepthAlt
            ]),
            width: 3.0,
            material: new Cesium.PolylineGlowMaterialProperty({
              glowPower: 0.4,
              taperPower: 0.8,
              color: cfg.cesiumColor.withAlpha(0.85)
            })
          },
          show: this.filters[veh.type] !== false
        });
        pillar.vehicleData = veh;
        this.pillarEntities.push(pillar);
      });
    }

    // ── 2. SELECTION & INSTRUMENT INFORMATION PANEL ─────────────────────────

    selectVehicle(vehicleId) {
      const veh = this.vehicles.find(v => v.id === vehicleId);
      if (!veh) return;
      this.selectedVehicle = veh;

      // Open right profile panel and render instrument card
      const profilePanel = document.getElementById('profilePanel');
      if (profilePanel) profilePanel.classList.add('open');

      const admPanel = document.getElementById('adaptiveMissionPanel');
      if (admPanel) admPanel.classList.remove('open');

      document.getElementById('profileTitle').textContent = `${veh.type} · SUBSEA ASSET`;
      document.getElementById('profileMeta').textContent = `${veh.name} · ${veh.operator}`;

      // Update Three.js water column digital twin
      this.updateThreeDigitalTwin(veh);

      // Render Information Panel in obsCard
      this.renderVehicleInfoCard(veh);

      // Fly camera to center of vehicle
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (v && v.camera) {
        if (v.camera._flight) v.camera.cancelFlight();
        v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
        const lat = veh.latitude;
        const lon = veh.longitude;
        const lonOffset = 0.20 / Math.max(0.3, Math.cos(Cesium.Math.toRadians(lat)));
        const targetLon = lon + lonOffset;
        const bs = new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(targetLon, lat, 0), 0);
        v.camera.flyToBoundingSphere(bs, {
          offset: new Cesium.HeadingPitchRange(0.0, Cesium.Math.toRadians(-45.0), 180000),
          duration: 1.2
        });
      }
    }

    updateThreeDigitalTwin(veh) {
      const badge = document.getElementById('wcPlatformBadge');
      if (badge) {
        badge.textContent = `${veh.type} · DIGITAL TWIN`;
        badge.style.background = VEHICLE_CONFIG[veh.type]?.altColor || '#0284c7';
      }

      // If global Three.js water column is available, switch vehicle model
      if (typeof wcVehicleGroup !== 'undefined' && wcVehicleGroup && typeof THREE !== 'undefined') {
        while (wcVehicleGroup.children.length > 0) {
          wcVehicleGroup.remove(wcVehicleGroup.children[0]);
        }

        if (veh.type === 'AUV') {
          wcVehicleGroup.add(this.buildAUVModel());
        } else if (veh.type === 'UUV') {
          wcVehicleGroup.add(this.buildUUVModel());
        } else if (veh.type === 'ROV') {
          wcVehicleGroup.add(this.buildROVModel());
        }

        // Position model according to depth (mapped to cylinder height)
        const CYL_H = 3.4;
        const normDepth = Math.max(0.0, Math.min(1.0, veh.depth / 2000.0));
        wcVehicleGroup.position.set(0, -normDepth * CYL_H, 0);
        if (typeof updateWCCamera === 'function') updateWCCamera();
      }
    }

    renderVehicleInfoCard(v) {
      const card = document.getElementById('obsCard');
      if (!card) return;

      const cfg = VEHICLE_CONFIG[v.type] || VEHICLE_CONFIG.AUV;

      card.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:8px; font-family:'IBM Plex Sans', sans-serif;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding-bottom:6px;">
            <div>
              <span style="font-size:14px; font-weight:700; color:#fff; font-family:'IBM Plex Mono', monospace;">${v.id}</span>
              <div style="font-size:11px; color:${cfg.colorCss}; font-weight:600;">${v.type} — ${v.type === 'AUV' ? 'Autonomous Underwater Vehicle' : v.type === 'UUV' ? 'Uncrewed Underwater Vehicle' : 'Remotely Operated Vehicle'}</div>
            </div>
            <span style="font-size:9.5px; padding:2px 7px; border-radius:3px; background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.4); font-weight:700; font-family:'IBM Plex Mono';">
              ${v.source}
            </span>
          </div>

          <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:11px; background:rgba(15,23,42,0.6); padding:8px; border-radius:4px; border:1px solid rgba(255,255,255,0.06);">
            <div><span style="color:var(--text-dim);">Status:</span> <strong style="color:#34d399;">● ${v.status}</strong></div>
            <div><span style="color:var(--text-dim);">Max Depth:</span> <strong>${v.max_depth_m} m</strong></div>
            <div><span style="color:var(--text-dim);">Latitude:</span> <strong>${v.latitude.toFixed(3)}° N</strong></div>
            <div><span style="color:var(--text-dim);">Longitude:</span> <strong>${v.longitude.toFixed(3)}° E</strong></div>
            <div><span style="color:var(--text-dim);">Current Depth:</span> <strong style="color:${cfg.colorCss};">${v.depth} m</strong></div>
            <div><span style="color:var(--text-dim);">Speed:</span> <strong>${v.cruise_speed_mps} m/s</strong></div>
            <div><span style="color:var(--text-dim);">Battery:</span> <strong>${v.battery_percent}%</strong></div>
            <div><span style="color:var(--text-dim);">Range:</span> <strong>${v.remaining_range_km} km</strong></div>
          </div>

          <div>
            <div style="font-size:10px; font-weight:700; color:#94a3b8; letter-spacing:0.5px; margin-bottom:4px;">EQUIPPED SENSORS:</div>
            <div style="display:flex; flex-wrap:wrap; gap:4px;">
              ${v.sensors.map(s => `
                <span style="font-size:10px; padding:2px 6px; border-radius:3px; background:rgba(56,189,248,0.12); color:#38bdf8; border:1px solid rgba(56,189,248,0.3); font-weight:500;">
                  ✓ ${s.toUpperCase()}
                </span>
              `).join('')}
            </div>
          </div>

          <div style="font-size:10px; color:var(--text-dim); display:flex; justify-content:space-between; border-top:1px solid var(--line); padding-top:4px;">
            <span>Operator: <strong>${v.operator.split('/')[0]}</strong></span>
            <span>Update: <strong>${new Date(v.lastUpdate).toLocaleTimeString()}</strong></span>
          </div>

          <button id="btnOpenMissionPlanner" class="action primary" style="margin-top:6px; font-weight:700; display:flex; align-items:center; justify-content:center; gap:6px; padding:10px;">
            <span>🚀</span><span>PLAN MISSION</span>
          </button>
        </div>
      `;

      document.getElementById('btnOpenMissionPlanner')?.addEventListener('click', () => {
        this.renderMissionPlanningForm(v);
      });
    }

    // ── 3. MISSION PLANNING WORKFLOW & GLOBE CLICK TARGETING ────────────────

    renderMissionPlanningForm(v) {
      const card = document.getElementById('obsCard');
      if (!card) return;

      const cfg = VEHICLE_CONFIG[v.type] || VEHICLE_CONFIG.AUV;
      const defaultTargetLat = (v.latitude + 0.30).toFixed(3);
      const defaultTargetLon = (v.longitude + 0.25).toFixed(3);
      const defaultTargetDepth = Math.min(v.max_depth_m, v.depth + 200);

      card.innerHTML = `
        <div style="display:flex; flex-direction:column; gap:10px; font-family:'IBM Plex Sans', sans-serif;">
          <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); padding-bottom:6px;">
            <div>
              <span style="font-size:13px; font-weight:700; color:#fff;">MISSION PLANNING: ${v.id}</span>
              <div style="font-size:10.5px; color:${cfg.colorCss};">${cfg.label}</div>
            </div>
            <span style="font-size:9px; padding:2px 6px; border-radius:3px; background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.4); font-weight:700; font-family:'IBM Plex Mono';">
              SIMULATED MISSION
            </span>
          </div>

          <div style="background:rgba(15,23,42,0.6); padding:8px; border-radius:4px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:6px;">
            <div style="font-size:10.5px; font-weight:700; color:#e2e8f0;">1. Target Location:</div>
            <div style="display:flex; gap:6px;">
              <div style="flex:1;">
                <label style="font-size:9.5px; color:var(--text-dim);">Target Latitude (°N)</label>
                <input type="number" step="0.001" id="inpTargetLat" value="${defaultTargetLat}" style="width:100%; font-family:'IBM Plex Mono'; font-size:12px; padding:5px 7px;">
              </div>
              <div style="flex:1;">
                <label style="font-size:9.5px; color:var(--text-dim);">Target Longitude (°E)</label>
                <input type="number" step="0.001" id="inpTargetLon" value="${defaultTargetLon}" style="width:100%; font-family:'IBM Plex Mono'; font-size:12px; padding:5px 7px;">
              </div>
            </div>

            <button id="btnPickTargetOnGlobe" style="display:flex; align-items:center; justify-content:center; gap:6px; font-size:11px; font-weight:600; padding:6px; border-radius:3px; background:rgba(0,229,255,0.15); border:1px solid #00e5ff; color:#00e5ff; cursor:pointer; margin-top:2px;">
              <span>📍</span><span>Click on Globe to Set Target</span>
            </button>
            <div id="targetPickHint" style="display:none; font-size:10px; color:#38bdf8; text-align:center; font-style:italic;">
              Click anywhere on the 3D globe surface to drop target waypoint…
            </div>
          </div>

          <div style="background:rgba(15,23,42,0.6); padding:8px; border-radius:4px; border:1px solid rgba(255,255,255,0.08); display:flex; flex-direction:column; gap:4px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-size:10.5px; font-weight:700; color:#e2e8f0;">2. Target Depth:</span>
              <span id="lblTargetDepthVal" style="color:#00e5ff; font-weight:700; font-family:'IBM Plex Mono';">${defaultTargetDepth} m</span>
            </div>
            <input type="range" id="rngTargetDepth" min="0" max="${v.max_depth_m}" value="${defaultTargetDepth}" step="10" style="width:100%; accent-color:#00e5ff; cursor:pointer;">
            <div style="display:flex; justify-content:space-between; font-size:9px; color:var(--text-dim); font-family:'IBM Plex Mono';">
              <span>Surface (0 m)</span>
              <span>Max Rated (${v.max_depth_m} m)</span>
            </div>
          </div>

          <div style="background:rgba(15,23,42,0.6); padding:8px; border-radius:4px; border:1px solid rgba(255,255,255,0.08);">
            <div style="font-size:10.5px; font-weight:700; color:#e2e8f0; margin-bottom:4px;">3. Target Sampling Sensors:</div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:10.5px;">
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" id="chkSensTemp" checked> Temperature</label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" id="chkSensSal" checked> Salinity</label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" id="chkSensOxy" checked> Dissolved O₂</label>
              <label style="display:flex; align-items:center; gap:4px; cursor:pointer;"><input type="checkbox" id="chkSensChl" checked> Chlorophyll-a</label>
            </div>
          </div>

          <button id="btnGenerateMissionRoute" class="action primary" style="font-weight:700; display:flex; align-items:center; justify-content:center; gap:6px; padding:10px;">
            <span>🧭</span><span>GENERATE MISSION ROUTE</span>
          </button>

          <!-- Route Preview & Simulation Launcher Container -->
          <div id="missionPreviewContainer" style="display:none; flex-direction:column; gap:8px;"></div>
        </div>
      `;

      // Wire Depth Slider
      const rngDepth = document.getElementById('rngTargetDepth');
      const lblDepth = document.getElementById('lblTargetDepthVal');
      if (rngDepth && lblDepth) {
        rngDepth.addEventListener('input', (e) => {
          lblDepth.textContent = `${e.target.value} m`;
        });
      }

      // Wire Globe Pick Button
      const btnPick = document.getElementById('btnPickTargetOnGlobe');
      const hint = document.getElementById('targetPickHint');
      if (btnPick) {
        btnPick.addEventListener('click', () => {
          this.isSelectingTarget = !this.isSelectingTarget;
          if (this.isSelectingTarget) {
            btnPick.style.background = '#00e5ff';
            btnPick.style.color = '#041019';
            btnPick.innerHTML = '<span>🎯</span><span>Click on Globe Now (Active)…</span>';
            if (hint) hint.style.display = 'block';
          } else {
            btnPick.style.background = 'rgba(0,229,255,0.15)';
            btnPick.style.color = '#00e5ff';
            btnPick.innerHTML = '<span>📍</span><span>Click on Globe to Set Target</span>';
            if (hint) hint.style.display = 'none';
          }
        });
      }

      // Wire Route Generator Button
      document.getElementById('btnGenerateMissionRoute')?.addEventListener('click', () => {
        this.generateMissionPlan();
      });
    }

    handleGlobeTargetClick(lat, lon) {
      if (!this.isSelectingTarget) return;
      this.isSelectingTarget = false;

      const inpLat = document.getElementById('inpTargetLat');
      const inpLon = document.getElementById('inpTargetLon');
      if (inpLat) inpLat.value = lat.toFixed(3);
      if (inpLon) inpLon.value = lon.toFixed(3);

      const btnPick = document.getElementById('btnPickTargetOnGlobe');
      const hint = document.getElementById('targetPickHint');
      if (btnPick) {
        btnPick.style.background = 'rgba(0,229,255,0.15)';
        btnPick.style.color = '#00e5ff';
        btnPick.innerHTML = '<span>📍</span><span>Target Set from Globe Click ✓</span>';
      }
      if (hint) hint.style.display = 'none';

      const depth = parseFloat(document.getElementById('rngTargetDepth')?.value || 800);
      this.renderTargetWaypointOnGlobe(lat, lon, depth);

      // Auto-preview route
      this.generateMissionPlan();
    }

    renderTargetWaypointOnGlobe(lat, lon, depth) {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v || !v.entities) return;

      if (this.targetEntity) try { v.entities.remove(this.targetEntity); } catch(e){}
      if (this.targetPulseEntity) try { v.entities.remove(this.targetPulseEntity); } catch(e){}

      const targetPos = Cesium.Cartesian3.fromDegrees(lon, lat, 2000.0);

      // Distinct target pin
      this.targetEntity = v.entities.add({
        id: 'mission_target_waypoint',
        position: targetPos,
        point: {
          pixelSize: 14,
          color: Cesium.Color.fromCssColorString('#f43f5e'),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 3
        },
        label: {
          text: `◎ TARGET\n${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E\nDepth: ${depth}m`,
          font: 'bold 11px "IBM Plex Mono", monospace',
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.fromCssColorString('#f43f5e'),
          outlineWidth: 3,
          pixelOffset: new Cesium.Cartesian2(0, -42),
          scaleByDistance: new Cesium.NearFarScalar(1.0e5, 1.0, 2.0e7, 0.6)
        }
      });

      // Target pulsing ring
      let ringRadius = 5000;
      this.targetPulseEntity = v.entities.add({
        id: 'mission_target_pulse',
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
        ellipse: {
          semiMajorAxis: new Cesium.CallbackProperty(() => {
            ringRadius = (ringRadius + 1200) % 65000;
            return Math.max(3000, ringRadius);
          }, false),
          semiMinorAxis: new Cesium.CallbackProperty(() => {
            return Math.max(3000, ringRadius);
          }, false),
          height: 0,
          material: Cesium.Color.fromCssColorString('#f43f5e').withAlpha(0.35),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#f43f5e')
        }
      });
    }

    async generateMissionPlan() {
      if (!this.selectedVehicle) return;

      const targetLat = parseFloat(document.getElementById('inpTargetLat')?.value);
      const targetLon = parseFloat(document.getElementById('inpTargetLon')?.value);
      const targetDepth = parseFloat(document.getElementById('rngTargetDepth')?.value);

      if (isNaN(targetLat) || isNaN(targetLon) || isNaN(targetDepth)) {
        alert('Please specify valid numerical target coordinates and depth.');
        return;
      }

      const sensors = [];
      if (document.getElementById('chkSensTemp')?.checked) sensors.push('temperature');
      if (document.getElementById('chkSensSal')?.checked) sensors.push('salinity');
      if (document.getElementById('chkSensOxy')?.checked) sensors.push('oxygen');
      if (document.getElementById('chkSensChl')?.checked) sensors.push('chlorophyll');

      try {
        const endpoint = (typeof apiUrl === 'function') ? apiUrl('/api/missions/plan') : '/api/missions/plan';
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            vehicle_id: this.selectedVehicle.id,
            target_lat: targetLat,
            target_lon: targetLon,
            target_depth: targetDepth,
            sensors: sensors
          })
        });

        if (!res.ok) {
          const errData = await res.json();
          alert(`Mission Plan Error: ${errData.detail || 'Could not generate route'}`);
          return;
        }

        const mission = await res.json();
        this.activeMission = mission;

        // Render target waypoint & planned route on Cesium globe
        this.renderTargetWaypointOnGlobe(targetLat, targetLon, targetDepth);
        this.renderPlannedRouteOnGlobe(mission.waypoints);

        // Display preview section
        const prevContainer = document.getElementById('missionPreviewContainer');
        if (prevContainer) {
          prevContainer.style.display = 'flex';
          prevContainer.innerHTML = `
            <div style="background:rgba(6,78,59,0.3); border:1px solid rgba(52,211,153,0.4); border-radius:4px; padding:8px; font-size:11px; display:flex; flex-direction:column; gap:4px;">
              <div style="font-weight:700; color:#34d399; font-size:11.5px; display:flex; justify-content:space-between;">
                <span>ROUTE GENERATED</span>
                <span>${mission.mission_id}</span>
              </div>
              <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-dim);">Direct Distance:</span><strong>${mission.direct_distance_km} km</strong></div>
              <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-dim);">Estimated Duration:</span><strong>${mission.estimated_duration_hours} hrs</strong></div>
              <div style="display:flex; justify-content:space-between;"><span style="color:var(--text-dim);">Transit Stages:</span><span>Cruising (${mission.origin.depth_m}m) → Diving → Sampling (${mission.target.depth_m}m)</span></div>
            </div>

            <button id="btnStartMissionSim" class="action" style="background:#10b981; border:1px solid #059669; color:#fff; font-weight:700; padding:10px; display:flex; align-items:center; justify-content:center; gap:6px; cursor:pointer;">
              <span>▶</span><span>START MISSION SIMULATION</span>
            </button>
          `;

          document.getElementById('btnStartMissionSim')?.addEventListener('click', () => {
            this.startMissionSimulation();
          });
        }
      } catch (err) {
        console.error('Failed to generate mission plan:', err);
        alert('Network error communicating with mission planning engine.');
      }
    }

    renderPlannedRouteOnGlobe(waypoints) {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v || !v.entities) return;

      this.routeEntities.forEach(e => { try { v.entities.remove(e); } catch(err){} });
      this.routeEntities = [];

      const coords = waypoints.map(w => Cesium.Cartesian3.fromDegrees(w.longitude, w.latitude, 2000.0));

      // Dashed planned route line
      const routeLine = v.entities.add({
        id: 'mission_planned_route',
        polyline: {
          positions: coords,
          width: 3.5,
          material: new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString('#00e5ff'),
            dashLength: 16.0
          })
        }
      });
      this.routeEntities.push(routeLine);
    }

    // ── 4. MISSION SIMULATION ENGINE ────────────────────────────────────────

    startMissionSimulation() {
      if (!this.activeMission || !this.selectedVehicle) return;

      const mission = this.activeMission;
      const rawWaypoints = mission.waypoints || [];
      if (rawWaypoints.length === 0) return;

      // Densely interpolate waypoints for smooth subsea transit animation (minimum 25 steps)
      const waypoints = [];
      const totalSteps = Math.max(25, rawWaypoints.length * 3);
      for (let s = 0; s <= totalSteps; s++) {
        const globalT = s / totalSteps;
        const rawIdx = globalT * (rawWaypoints.length - 1);
        const low = Math.floor(rawIdx);
        const high = Math.min(rawWaypoints.length - 1, Math.ceil(rawIdx));
        const subT = rawIdx - low;

        const p1 = rawWaypoints[low];
        const p2 = rawWaypoints[high];

        const lat = p1.latitude + (p2.latitude - p1.latitude) * subT;
        const lon = p1.longitude + (p2.longitude - p1.longitude) * subT;
        const depth = p1.depth_m + (p2.depth_m - p1.depth_m) * subT;
        const stage = subT > 0.5 ? p2.stage : p1.stage;

        waypoints.push({
          latitude: lat,
          longitude: lon,
          depth_m: depth,
          stage: stage,
          progress_percent: Math.round(globalT * 100)
        });
      }

      let currentIndex = 0;
      let isPaused = false;
      let cameraFollow = true;

      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);

      // Smoothly frame the entire route end-to-end from origin to target in top-down view
      if (v && v.camera && waypoints.length >= 2) {
        const origin = waypoints[0];
        const target = waypoints[waypoints.length - 1];
        const centerLon = (origin.longitude + target.longitude) / 2.0;
        const centerLat = (origin.latitude + target.latitude) / 2.0;

        // Great-circle distance → altitude proportional so both ends fit in view
        const dLon = (target.longitude - origin.longitude) * Math.PI / 180.0;
        const dLat = (target.latitude - origin.latitude) * Math.PI / 180.0;
        const sinDLat = Math.sin(dLat / 2.0);
        const sinDLon = Math.sin(dLon / 2.0);
        const aHav = sinDLat * sinDLat +
          Math.cos(origin.latitude * Math.PI / 180.0) *
          Math.cos(target.latitude * Math.PI / 180.0) *
          sinDLon * sinDLon;
        const distKm = 6371.0 * 2.0 * Math.atan2(Math.sqrt(aHav), Math.sqrt(1.0 - aHav));

        // 1.8× great-circle distance, clamped 120 km – 1200 km
        const routeAlt = Math.max(120000.0, Math.min(1200000.0, distKm * 1800.0));

        v.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(centerLon, centerLat, routeAlt),
          orientation: {
            heading: Cesium.Math.toRadians(0.0),
            pitch: Cesium.Math.toRadians(-85.0),
            roll: 0.0
          },
          duration: 1.2
        });
      }

      const prevContainer = document.getElementById('missionPreviewContainer');
      if (prevContainer) {
        prevContainer.innerHTML = `
          <div id="simStatusWrap" style="background:rgba(15,23,42,0.85); border:1px solid #38bdf8; border-radius:4px; padding:10px; display:flex; flex-direction:column; gap:6px; font-family:'IBM Plex Mono', monospace; font-size:11px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span id="simPhase" style="font-weight:700; color:#38bdf8;">EN ROUTE</span>
              <span id="simPct" style="color:#34d399; font-weight:700;">0%</span>
            </div>
            <div style="width:100%; height:6px; background:#0f172a; border-radius:3px; overflow:hidden; border:1px solid rgba(255,255,255,0.1);">
              <div id="simBar" style="width:0%; height:100%; background:linear-gradient(to right, #00e5ff, #10b981); transition:width .2s;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-dim); margin-top:2px;">
              <span>Pos: <strong id="simCoords" style="color:#fff;">--</strong></span>
              <span>Depth: <strong id="simDepth" style="color:#00e5ff;">--</strong></span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--text-dim);">
              <span>Stage: <strong id="simStage" style="color:#fbbf24;">TRANSIT</strong></span>
              <span>Speed: <strong>${this.selectedVehicle.cruise_speed_mps} m/s</strong></span>
            </div>
            <div style="display:flex; gap:6px; margin-top:4px;">
              <button id="btnPauseMissionSim" style="flex:1; padding:4px 8px; font-size:10px; font-weight:700; background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#fff; border-radius:3px; cursor:pointer;">
                ⏸ Pause
              </button>
              <button id="btnCamFollowMissionSim" style="flex:1; padding:4px 8px; font-size:10px; font-weight:700; background:rgba(56,189,248,0.15); border:1px solid #38bdf8; color:#38bdf8; border-radius:3px; cursor:pointer;">
                🎥 Track
              </button>
              <button id="btnStopMissionSim" style="flex:1; padding:4px 8px; font-size:10px; font-weight:700; background:rgba(239,68,68,0.2); border:1px solid #ef4444; color:#ef4444; border-radius:3px; cursor:pointer;">
                ⏹ Abort
              </button>
            </div>
          </div>
        `;

        document.getElementById('btnPauseMissionSim')?.addEventListener('click', (e) => {
          isPaused = !isPaused;
          e.target.textContent = isPaused ? '▶ Resume' : '⏸ Pause';
        });

        document.getElementById('btnCamFollowMissionSim')?.addEventListener('click', (e) => {
          cameraFollow = !cameraFollow;
          e.target.textContent = cameraFollow ? '🎥 Track' : '🌐 Free';
          e.target.style.color = cameraFollow ? '#38bdf8' : '#94a3b8';
          e.target.style.borderColor = cameraFollow ? '#38bdf8' : 'rgba(255,255,255,0.2)';
        });

        document.getElementById('btnStopMissionSim')?.addEventListener('click', () => {
          if (this.simulationInterval) {
            clearInterval(this.simulationInterval);
            this.simulationInterval = null;
          }
          if (v && v.camera) v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
          this.clearMissionGraphics();
          this.renderVehicleInfoCard(this.selectedVehicle);
        });
      }

      if (this.simulationInterval) clearInterval(this.simulationInterval);

      // Track completed positions
      const completedPositions = [];

      let completedTrackEntity = null;
      if (v) {
        completedTrackEntity = v.entities.add({
          id: 'mission_completed_track',
          polyline: {
            positions: new Cesium.CallbackProperty(() => completedPositions, false),
            width: 4,
            material: new Cesium.PolylineGlowMaterialProperty({
              glowPower: 0.3,
              color: Cesium.Color.fromCssColorString('#a855f7')
            })
          }
        });
        this.routeEntities.push(completedTrackEntity);
      }

      this.simulationInterval = setInterval(async () => {
        if (isPaused) return;

        if (currentIndex >= waypoints.length) {
          clearInterval(this.simulationInterval);
          this.simulationInterval = null;
          await this.completeMissionAtTarget();
          return;
        }

        const wp = waypoints[currentIndex];
        const pct = wp.progress_percent;
        const curDepth = wp.depth_m;

        // Determine phase state
        let phase = 'EN ROUTE';
        if (pct >= 85) phase = 'SAMPLING';
        else if (pct >= 50) phase = 'DIVING';

        // Update UI
        const elPhase = document.getElementById('simPhase');
        const elPct = document.getElementById('simPct');
        const elBar = document.getElementById('simBar');
        const elCoords = document.getElementById('simCoords');
        const elDepth = document.getElementById('simDepth');
        const elStage = document.getElementById('simStage');

        if (elPhase) elPhase.textContent = phase;
        if (elPct) elPct.textContent = `${pct}%`;
        if (elBar) elBar.style.width = `${pct}%`;
        if (elCoords) elCoords.textContent = `${wp.latitude.toFixed(2)}°N, ${wp.longitude.toFixed(2)}°E`;
        if (elDepth) elDepth.textContent = `${curDepth.toFixed(0)} m`;
        if (elStage) elStage.textContent = wp.stage;

        // Move Cesium vehicle entity
        const vehEnt = this.vehicleEntities.find(e => e.vehicleData && e.vehicleData.id === this.selectedVehicle.id);
        if (vehEnt) {
          const newPos = Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, 3000.0);
          vehEnt.position = newPos;

          // Dynamically update vehicle badge image
          if (vehEnt.billboard && currentIndex % 3 === 0) {
            const tempVeh = { ...vehEnt.vehicleData, depth: curDepth, status: phase };
            vehEnt.billboard.image = this._generateVehicleBadgeCanvas(tempVeh);
          }
        }

        // Update pillar depth
        const pillarEnt = this.pillarEntities.find(e => e.vehicleData && e.vehicleData.id === this.selectedVehicle.id);
        if (pillarEnt) {
          const vertExagg = (window.state && window.state.verticalExaggeration) || 1.0;
          pillarEnt.polyline.positions = Cesium.Cartesian3.fromDegreesArrayHeights([
            wp.longitude, wp.latitude, 3000.0,
            wp.longitude, wp.latitude, -curDepth * 4.0 * vertExagg
          ]);
        }

        // Add to completed track
        completedPositions.push(Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, 2000.0));

        // Smooth camera follow in top-down view without subterranean locking
        if (cameraFollow && v && v.camera && currentIndex % 4 === 0) {
          const camAlt = curDepth > 0 ? 60000.0 : 120000.0;
          v.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, camAlt),
            orientation: {
              heading: v.camera.heading,
              pitch: Cesium.Math.toRadians(-85.0),
              roll: 0.0
            },
            duration: 0.7
          });
        }

        // Animate Three.js water column depth
        if (typeof wcVehicleGroup !== 'undefined' && wcVehicleGroup) {
          const CYL_H = 3.4;
          const normDepth = Math.max(0.0, Math.min(1.0, curDepth / 2000.0));
          wcVehicleGroup.position.set(0, -normDepth * CYL_H, 0);
        }

        currentIndex++;
      }, 220);
    }

    async completeMissionAtTarget() {
      if (!this.activeMission) return;
      const target = this.activeMission.target;

      // Do NOT auto open OBSERVATION INFO profile panel upon mission completion
      const profilePanel = document.getElementById('profilePanel');
      if (profilePanel) profilePanel.classList.remove('open');
      const admPanel = document.getElementById('adaptiveMissionPanel');
      if (admPanel) admPanel.classList.remove('open');

      const elPhase = document.getElementById('simPhase');
      const elPct = document.getElementById('simPct');
      const elStage = document.getElementById('simStage');
      if (elPhase) elPhase.textContent = 'TARGET REACHED & DATA COLLECTED';
      if (elPct) elPct.textContent = '100%';
      if (elStage) elStage.textContent = 'DATA LOGGED';

      const hint = document.getElementById('hint');
      if (hint) {
        hint.style.display = 'block';
        hint.textContent = `🎯 Mission Complete — Soundings Acquired for ${this.selectedVehicle?.name || 'Asset'} (Click asset on globe to inspect)`;
      }

      // Fetch co-located / simulated ocean observations
      try {
        const sampleUrl = (typeof apiUrl === 'function')
          ? apiUrl(`/api/missions/sample?lat=${target.latitude}&lon=${target.longitude}&depth=${target.depth_m}`)
          : `/api/missions/sample?lat=${target.latitude}&lon=${target.longitude}&depth=${target.depth_m}`;

        const res = await fetch(sampleUrl);
        const sample = res.ok ? await res.json() : null;

        const prevContainer = document.getElementById('missionPreviewContainer');
        if (prevContainer && sample) {
          const m = sample.measurements;
          prevContainer.innerHTML = `
            <div style="background:rgba(6,78,59,0.35); border:1px solid #10b981; border-radius:5px; padding:10px; display:flex; flex-direction:column; gap:6px; font-family:'IBM Plex Sans', sans-serif;">
              <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(16,185,129,0.3); padding-bottom:4px;">
                <span style="font-weight:700; color:#34d399; font-size:12px;">🎯 TARGET OBSERVATION COLLECTED</span>
                <span style="font-size:9px; padding:1px 5px; border-radius:3px; background:rgba(245,158,11,0.2); color:#f59e0b; border:1px solid #f59e0b; font-weight:700;">SIMULATED</span>
              </div>

              <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:11px; margin-top:2px;">
                <div>Depth: <strong style="color:#00e5ff;">${sample.target.depth_m} m</strong></div>
                <div>Temperature: <strong style="color:#38bdf8;">${m.temperature ?? '--'} °C</strong></div>
                <div>Salinity: <strong style="color:#34d399;">${m.salinity ?? '--'} PSU</strong></div>
                <div>Dissolved O₂: <strong style="color:#a78bfa;">${m.oxygen ?? '--'} µmol/kg</strong></div>
                <div>Chlorophyll-a: <strong style="color:#fde047;">${m.chlorophyll ?? '--'} mg/m³</strong></div>
                <div>Quality: <strong style="color:#34d399;">PASSED (1)</strong></div>
              </div>

              <div style="font-size:9.5px; color:var(--text-dim); border-top:1px solid rgba(255,255,255,0.06); padding-top:4px; margin-top:4px;">
                <div>Time: ${sample.timestamp}</div>
                <div>Source: ${sample.provenance}</div>
              </div>

              <button id="btnResetMissionPlanner" class="action" style="margin-top:6px; font-size:11px; font-weight:600; padding:8px;">
                Plan Another Subsea Mission
              </button>
            </div>
          `;

          document.getElementById('btnResetMissionPlanner')?.addEventListener('click', () => {
            this.clearMissionGraphics();
            if (this.selectedVehicle) this.renderVehicleInfoCard(this.selectedVehicle);
          });
        }
      } catch (err) {
        console.error('Failed to sample target observation:', err);
      }
    }

    clearMissionGraphics() {
      const v = window.viewer || (typeof viewer !== 'undefined' ? viewer : null);
      if (!v || !v.entities) return;

      this.routeEntities.forEach(e => { try { v.entities.remove(e); } catch(err){} });
      this.routeEntities = [];

      if (this.targetEntity) try { v.entities.remove(this.targetEntity); } catch(e){}
      if (this.targetPulseEntity) try { v.entities.remove(this.targetPulseEntity); } catch(e){}
      this.targetEntity = null;
      this.targetPulseEntity = null;
      this.activeMission = null;

      // BUG-08 FIX: Restore vehicle entities to their home position and rebuild
      // their badge, then re-render all vehicles so the globe is clean after Abort
      if (this.vehicleEntities && this.vehicleEntities.length) {
        this.vehicleEntities.forEach(ent => {
          try {
            if (ent.vehicleData) {
              const vd = ent.vehicleData;
              ent.position = Cesium.Cartesian3.fromDegrees(vd.longitude, vd.latitude, 3000.0);
              if (ent.billboard) {
                ent.billboard.image = this._generateVehicleBadgeCanvas(vd);
              }
            }
          } catch (err) {}
        });
      }
      if (this.pillarEntities && this.pillarEntities.length) {
        this.pillarEntities.forEach(ent => {
          try {
            if (ent.vehicleData) {
              const vd = ent.vehicleData;
              ent.polyline.positions = Cesium.Cartesian3.fromDegreesArrayHeights([
                vd.longitude, vd.latitude, 3000.0,
                vd.longitude, vd.latitude, 0.0
              ]);
            }
          } catch (err) {}
        });
      }

      // Reset camera free orbit mode
      if (v.camera) {
        try { v.camera.lookAtTransform(Cesium.Matrix4.IDENTITY); } catch (e) {}
      }
    }

    // ── 5. THREE.JS PROCEDURAL VEHICLE DIGITAL TWINS ────────────────────────

    buildAUVModel() {
      const group = new THREE.Group();
      // Yellow / Cyan torpedo fuselage
      const fuse = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.18, 1.8, 32),
        new THREE.MeshStandardMaterial({ color: 0x06b6d4, roughness: 0.2, metalness: 0.4 })
      );
      fuse.rotation.z = Math.PI / 2;
      group.add(fuse);

      // Rounded nose dome
      const nose = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 24, 24, 0, Math.PI * 2, 0, Math.PI / 2),
        new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.25, metalness: 0.2 })
      );
      nose.rotation.z = -Math.PI / 2;
      nose.position.x = 0.90;
      group.add(nose);

      // Rear propulsion shroud & propeller
      const shroud = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.12, 0.22, 16, 1, true),
        new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.5, metalness: 0.7, side: THREE.DoubleSide })
      );
      shroud.rotation.z = Math.PI / 2;
      shroud.position.x = -1.0;
      group.add(shroud);

      // Cruciform tail control fins
      const finMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.3 });
      const finTop = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.28, 0.02), finMat);
      finTop.position.set(-0.75, 0.20, 0); group.add(finTop);
      const finBot = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.28, 0.02), finMat);
      finBot.position.set(-0.75, -0.20, 0); group.add(finBot);
      const finL = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.02, 0.28), finMat);
      finL.position.set(-0.75, 0, 0.20); group.add(finL);
      const finR = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.02, 0.28), finMat);
      finR.position.set(-0.75, 0, -0.20); group.add(finR);

      // Sensor acoustic dome underneath
      const sensorDome = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 0.06, 16),
        new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.8, roughness: 0.1 })
      );
      sensorDome.position.set(0.3, -0.19, 0);
      group.add(sensorDome);

      group.scale.setScalar(0.70);
      return group;
    }

    buildUUVModel() {
      const group = new THREE.Group();
      // Streamlined twin-hull stealth subsea drone in electric purple
      const hullMat = new THREE.MeshStandardMaterial({ color: 0x7c3aed, roughness: 0.3, metalness: 0.5 });
      const mainBody = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.22, 0.55), hullMat);
      group.add(mainBody);

      // Nose wedge
      const nose = new THREE.Mesh(new THREE.ConeGeometry(0.28, 0.50, 4), hullMat);
      nose.rotation.z = -Math.PI / 2;
      nose.rotation.y = Math.PI / 4;
      nose.position.x = 1.05;
      group.add(nose);

      // Dual side thrusters
      const thrusterMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8, roughness: 0.2 });
      const thrusterL = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.35, 16), thrusterMat);
      thrusterL.rotation.z = Math.PI / 2;
      thrusterL.position.set(-0.75, 0, 0.38);
      group.add(thrusterL);

      const thrusterR = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.35, 16), thrusterMat);
      thrusterR.rotation.z = Math.PI / 2;
      thrusterR.position.set(-0.75, 0, -0.38);
      group.add(thrusterR);

      // Top sensor mast
      const mast = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 0.45, 8),
        new THREE.MeshStandardMaterial({ color: 0xa855f7, metalness: 0.9 })
      );
      mast.position.set(-0.2, 0.32, 0);
      group.add(mast);

      group.scale.setScalar(0.68);
      return group;
    }

    buildROVModel() {
      const group = new THREE.Group();
      // Open structural titanium cage frame
      const cageMat = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.9, roughness: 0.2 });
      const frame = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.75, 0.85), new THREE.MeshBasicMaterial({ wireframe: true, color: 0x94a3b8 }));
      group.add(frame);

      // Yellow buoyant syntactic foam block on top
      const foam = new THREE.Mesh(
        new THREE.BoxGeometry(0.95, 0.28, 0.75),
        new THREE.MeshStandardMaterial({ color: 0xf59e0b, roughness: 0.35, metalness: 0.1 })
      );
      foam.position.set(0, 0.24, 0);
      group.add(foam);

      // Articulated robotic manipulator arm extending forward
      const armMat = new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.8 });
      const armBase = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.12, 0.12), armMat);
      armBase.position.set(0.55, -0.15, 0.22);
      group.add(armBase);

      const armSegment = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.38, 8), armMat);
      armSegment.rotation.z = -Math.PI / 3;
      armSegment.position.set(0.72, -0.22, 0.22);
      group.add(armSegment);

      // Forward pan-and-tilt camera dome with LED floodlights
      const cam = new THREE.Mesh(
        new THREE.SphereGeometry(0.09, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.9, roughness: 0.1 })
      );
      cam.position.set(0.55, 0, 0);
      group.add(cam);

      // Top umbilical tether cable reaching upward
      const tether = new THREE.Mesh(
        new THREE.CylinderGeometry(0.015, 0.015, 0.65, 8),
        new THREE.MeshStandardMaterial({ color: 0xf97316 })
      );
      tether.position.set(-0.2, 0.65, 0);
      group.add(tether);

      group.scale.setScalar(0.75);
      return group;
    }
  }

  // Initialize and expose globally
  window.VehicleMissionManager = new VehicleMissionManager();
  window.vehicleMissions = window.VehicleMissionManager;
  window.toggleVehicleLabels = (show) => window.VehicleMissionManager.toggleVehicleLabels(show);

})(window);
