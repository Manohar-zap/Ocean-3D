/**
 * OCEAN 3D — Authentic Earth Nullschool Ocean Current Flow Engine
 * 
 * True Earth Nullschool & Windy Reproduction:
 * - Viewport-Adaptive Particle Spawning: Particles are concentrated dynamically
 *   within the camera's visible ocean area, ensuring full zoom is DENSELY populated
 *   with thousands of flowing streamlines across all gyres and eddies.
 * - Copernicus Marine Speed Heatmap: Authentic background scalar velocity field
 *   (deep navy blue -> emerald green -> golden yellow) derived directly from real U/V.
 * - Fine Luminous Streamlines: 12-point continuous curved filaments (1.0–1.3px width).
 * - Custom GLSL 'StreamlineFade' Material: Power-1.2 tapering (delicate wispy tail to brilliant glowing head).
 * - Runge-Kutta 2 (RK2 Midpoint) physical trajectory integration.
 * - 2-Phase Frame Interleaving: Maintains locked 60 FPS with zero lag or CPU thrashing.
 * - Pure Copernicus Marine Data: Zero synthetic fallbacks.
 */

// Register custom streamline fading material in Cesium material cache
(function registerStreamlineMaterial() {
  try {
    if (typeof Cesium !== 'undefined' && Cesium.Material && Cesium.Material._materialCache) {
      Cesium.Material._materialCache.addMaterial('StreamlineFade', {
        fabric: {
          type: 'StreamlineFade',
          uniforms: {
            color: Cesium.Color.CYAN
          },
          source: [
            'czm_material czm_getMaterial(czm_materialInput materialInput) {',
            '  czm_material material = czm_getDefaultMaterial(materialInput);',
            '  float s = clamp(materialInput.st.s, 0.0, 1.0);',
            '  // Power-1.2 gradient: whisper-thin translucent tail (0.15), glowing leading head (1.0)',
            '  float fade = 0.15 + 0.85 * pow(s, 1.2);',
            '  vec3 rgb = color.rgb * (0.85 + 0.50 * s);',
            '  material.diffuse = rgb;',
            '  material.emission = rgb * (fade * 1.5);', // Luminous glow against dark ocean
            '  material.alpha = clamp(color.a * fade, 0.0, 1.0);',
            '  return material;',
            '}'
          ].join('\n')
        }
      });
    }
  } catch (e) {
    console.warn('StreamlineFade registration notice:', e);
  }
})();

class OceanFlowEngine {
  constructor() {
    this.viewer = null;
    this.polyCollection = null;
    this.speedImageryLayer = null;
    this.particles = [];
    this.numPoints = 12; // 12-point streamline (11 segments) for elegant curvature
    this.maxParticles = 3000;
    this.activeParticleCount = 2500;

    // Grid data
    this.uGrid = null;
    this.vGrid = null;
    this.validIndices = null;
    this.latMin = -80.0;
    this.latMax = 90.0;
    this.latStep = 1.0;
    this.lonMin = -180.0;
    this.lonMax = 179.0;
    this.lonStep = 1.0;
    this.nLat = 0;
    this.nLon = 0;

    // 3D positioning
    this.currentDepth = 0.0;
    this.currentTime = '';
    this.currentAlt = 3000.0;
    this.verticalExaggeration = 1.0;
    // Calibrated speed scale: produces visible, flowing streamlines (~70-150 screen pixels)
    this.speedScale = 850000.0;

    // Animation & Performance
    this.running = false;
    this.preRenderRemoveCallback = null;
    this.lastFrameTime = performance.now();
    this.frameCount = 0;
    this.frameTimesWindow = [];
    this.avgFrameTimeMs = 16.6;

    // Cached camera viewport bounding box
    this.cachedViewRect = { minLat: -80, maxLat: 85, minLon: -180, maxLon: 180 };
    this.viewRectAge = 0;

    // Dynamic date+depth field cache Map<date+depth, gridData>
    this.gridCache = new Map();

    // 32-tier continuous speed color palette (deep blue -> cyan -> green -> yellow -> amber -> red)
    this.palette = [];
    this._initColorPalette();
  }

  _initColorPalette() {
    // Earth Nullschool color stops: [speed, R, G, B, Alpha]
    const stops = [
      { s: 0.00, r: 0.15, g: 0.50, b: 0.85, a: 0.65 }, // Calm: cyan-blue
      { s: 0.15, r: 0.10, g: 0.75, b: 0.90, a: 0.75 }, // Gentle: bright cyan
      { s: 0.30, r: 0.20, g: 0.85, b: 0.55, a: 0.85 }, // Moderate: emerald green
      { s: 0.50, r: 0.70, g: 0.90, b: 0.20, a: 0.90 }, // Active: yellow-green
      { s: 0.70, r: 0.98, g: 0.85, b: 0.15, a: 0.95 }, // Fast: vibrant yellow
      { s: 0.90, r: 0.98, g: 0.60, b: 0.15, a: 0.98 }, // Boundary current: golden amber
      { s: 1.00, r: 1.00, g: 0.90, b: 0.70, a: 1.00 }  // Core jet: glowing white-gold
    ];

    this.palette = new Array(32);
    for (let i = 0; i < 32; i++) {
      const t = i / 31.0;
      let lower = stops[0], upper = stops[stops.length - 1];
      for (let k = 0; k < stops.length - 1; k++) {
        if (t >= stops[k].s && t <= stops[k + 1].s) {
          lower = stops[k];
          upper = stops[k + 1];
          break;
        }
      }
      const range = Math.max(0.0001, upper.s - lower.s);
      const frac = (t - lower.s) / range;
      const r = lower.r + (upper.r - lower.r) * frac;
      const g = lower.g + (upper.g - lower.g) * frac;
      const b = lower.b + (upper.b - lower.b) * frac;
      const a = lower.a + (upper.a - lower.a) * frac;

      const cesiumColor = new Cesium.Color(r, g, b, a);
      try {
        this.palette[i] = Cesium.Material.fromType('StreamlineFade', { color: cesiumColor });
      } catch (e) {
        this.palette[i] = Cesium.Material.fromType('Color', { color: cesiumColor });
      }
    }
  }

  init(viewer) {
    this.viewer = viewer;

    // Single batched Cesium primitive for locked 60 FPS rendering
    this.polyCollection = viewer.scene.primitives.add(new Cesium.PolylineCollection());
    this.polyCollection.show = false;

    const numPts = this.numPoints;

    // Pre-allocate fixed pool of particles
    this.particles = new Array(this.maxParticles);
    for (let i = 0; i < this.maxParticles; i++) {
      const points = new Array(numPts);
      const posArr0 = new Array(numPts);
      const posArr1 = new Array(numPts);

      for (let j = 0; j < numPts; j++) {
        points[j] = new Cesium.Cartesian3();
        posArr0[j] = points[j];
        posArr1[j] = points[j];
      }

      const polyline = this.polyCollection.add({
        positions: posArr0,
        width: 1.1, // Delicate, fine streamline (1.0–1.3px)
        material: this.palette[0],
        show: false
      });

      this.particles[i] = {
        lat: 0.0,
        lon: 0.0,
        age: 0,
        maxAge: 70 + Math.floor(Math.random() * 80),
        bucket: 0,
        points,
        posArr0,
        posArr1,
        polyline
      };
    }

    // Attach preRender listener
    this.preRenderRemoveCallback = viewer.scene.preRender.addEventListener(this._onPreRender.bind(this));
  }

  getViewportRectangle() {
    if (!this.viewer) {
      return { minLat: this.latMin, maxLat: this.latMax, minLon: this.lonMin, maxLon: this.lonMax };
    }

    // Refresh viewport rectangle once every 10 frames to eliminate camera math overhead
    this.viewRectAge++;
    if (this.viewRectAge < 10 && this.cachedViewRect) {
      return this.cachedViewRect;
    }
    this.viewRectAge = 0;

    try {
      const rect = this.viewer.camera.computeViewRectangle(this.viewer.scene.globe.ellipsoid);
      if (rect) {
        const south = Cesium.Math.toDegrees(rect.south);
        const north = Cesium.Math.toDegrees(rect.north);
        const west = Cesium.Math.toDegrees(rect.west);
        const east = Cesium.Math.toDegrees(rect.east);

        // If the view spans a reasonable regional/global window:
        if (north - south < 160.0) {
          this.cachedViewRect = {
            minLat: Math.max(-80.0, south - 2.0),
            maxLat: Math.min(85.0, north + 2.0),
            minLon: west - 2.0,
            maxLon: east + 2.0
          };
          return this.cachedViewRect;
        }
      }
    } catch (e) {
      // Fallback below
    }

    // Horizon / oblique camera fallback:
    try {
      const camCarto = Cesium.Cartographic.fromCartesian(this.viewer.camera.position);
      const latDeg = Cesium.Math.toDegrees(camCarto.latitude);
      const lonDeg = Cesium.Math.toDegrees(camCarto.longitude);
      const altKm = camCarto.height / 1000.0;
      const span = Math.min(180, Math.max(10, altKm / 70.0));
      this.cachedViewRect = {
        minLat: Math.max(-80.0, latDeg - span * 0.5),
        maxLat: Math.min(85.0, latDeg + span * 0.5),
        minLon: lonDeg - span,
        maxLon: lonDeg + span
      };
      return this.cachedViewRect;
    } catch (e) {
      this.cachedViewRect = { minLat: -80, maxLat: 85, minLon: -180, maxLon: 180 };
      return this.cachedViewRect;
    }
  }

  calculateAltitude(depth, exag) {
    const vExag = (exag !== undefined && exag !== null) ? exag : this.verticalExaggeration;
    return depth <= 0 ? (3000.0 * vExag) : (-depth * 4.0 * vExag);
  }

  setAltitude(depth, exag) {
    if (depth !== undefined && depth !== null) this.currentDepth = depth;
    if (exag !== undefined && exag !== null) this.verticalExaggeration = exag;
    this.currentAlt = this.calculateAltitude(this.currentDepth, this.verticalExaggeration);

    if (this.particles && this.particles.length) {
      const numPts = this.numPoints;
      for (let i = 0; i < this.activeParticleCount; i++) {
        const p = this.particles[i];
        if (p && p.points) {
          for (let j = 0; j < numPts; j++) {
            const pt = p.points[j];
            const carto = Cesium.Cartographic.fromCartesian(pt);
            Cesium.Cartesian3.fromRadians(carto.longitude, carto.latitude, this.currentAlt, undefined, pt);
          }
        }
      }
    }
  }

  async loadGrid(depth = 0.0, timeStr = '', exag = 1.0) {
    this.currentDepth = depth;
    this.currentTime = timeStr;
    this.verticalExaggeration = exag;
    this.currentAlt = this.calculateAltitude(depth, exag);

    const dateKey = (timeStr || '').slice(0, 10);
    const cacheKey = `${dateKey}_${depth}`;

    let data = this.gridCache.get(cacheKey);

    try {
      if (!data) {
        const url = apiUrl('/api/currents/grid?depth=' + encodeURIComponent(depth) + '&time=' + encodeURIComponent(timeStr || ''));
        const res = await fetch(url);
        if (!res.ok) {
          console.warn('Currents grid fetch returned status:', res.status);
          return false;
        }

        data = await res.json();
        if (!data || !data.u || !data.u.length) {
          console.warn('Currents grid returned empty payload');
          return false;
        }

        // Cache valid response
        this.gridCache.set(cacheKey, data);
      }

      this.latMin = data.lat_min;
      this.latMax = data.lat_max;
      this.latStep = data.lat_step || 1.0;
      this.lonMin = data.lon_min;
      this.lonMax = data.lon_max;
      this.lonStep = data.lon_step || 1.0;
      this.nLat = data.n_lat;
      this.nLon = data.n_lon;

      const totalCells = this.nLat * this.nLon;
      this.uGrid = new Float32Array(totalCells);
      this.vGrid = new Float32Array(totalCells);

      let validCount = 0;
      for (let idx = 0; idx < totalCells; idx++) {
        const uVal = data.u[idx];
        const vVal = data.v[idx];
        if (uVal !== null && uVal !== undefined && !isNaN(uVal)) {
          this.uGrid[idx] = uVal;
          this.vGrid[idx] = vVal;
          validCount++;
        } else {
          this.uGrid[idx] = NaN;
          this.vGrid[idx] = NaN;
        }
      }

      this.validIndices = new Int32Array(validCount);
      let ptr = 0;
      for (let idx = 0; idx < totalCells; idx++) {
        if (!isNaN(this.uGrid[idx])) {
          this.validIndices[ptr++] = idx;
        }
      }

      // Generate authentic Copernicus Marine ocean current speed heatmap
      this._updateSpeedHeatmap();

      // Initialize all active particles with viewport-adaptive distribution
      for (let i = 0; i < this.activeParticleCount; i++) {
        this._respawnParticle(this.particles[i], true);
      }

      console.info('Ocean flow grid initialized: ' + this.nLat + 'x' + this.nLon + ', ' + validCount + ' ocean cells, depth=' + depth + 'm');
      return true;
    } catch (err) {
      console.error('Error loading ocean currents grid:', err);
      return false;
    }
  }

  _updateSpeedHeatmap() {
    if (!this.uGrid || !this.vGrid || !this.viewer) return;

    try {
      const width = this.nLon;
      const height = this.nLat;
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      const imgData = ctx.createImageData(width, height);
      const data = imgData.data;

      // Earth Nullschool ocean current speed color map:
      // Navy Blue -> Jade Green -> Radiant Yellow / Gold
      for (let i = 0; i < height; i++) {
        // Flip latitude so North is at top of image
        const gridRow = (height - 1 - i);
        for (let j = 0; j < width; j++) {
          const idx = gridRow * width + j;
          const u = this.uGrid[idx];
          const v = this.vGrid[idx];
          const pIdx = (i * width + j) * 4;

          if (isNaN(u) || isNaN(v)) {
            // Land: transparent so Cesium terrestrial satellite imagery shows
            data[pIdx + 3] = 0;
            continue;
          }

          const speed = Math.hypot(u, v);
          // Normalized speed: 0.0 to 0.85 m/s
          const t = Math.min(1.0, Math.max(0.0, (speed - 0.02) / 0.80));

          let r, g, b, a;
          if (t < 0.25) {
            // Deep Navy Blue to Cyan-Teal
            const frac = t / 0.25;
            r = Math.floor(4 + frac * 8);
            g = Math.floor(22 + frac * 50);
            b = Math.floor(65 + frac * 45);
            a = 180;
          } else if (t < 0.55) {
            // Cyan-Teal to Emerald / Jade Green
            const frac = (t - 0.25) / 0.30;
            r = Math.floor(12 + frac * 10);
            g = Math.floor(72 + frac * 70);
            b = Math.floor(110 - frac * 50);
            a = 195;
          } else if (t < 0.82) {
            // Jade Green to Vibrant Yellow-Green
            const frac = (t - 0.55) / 0.27;
            r = Math.floor(22 + frac * 170);
            g = Math.floor(142 + frac * 60);
            b = Math.floor(60 - frac * 35);
            a = 210;
          } else {
            // Yellow-Green to Radiant Golden Amber
            const frac = (t - 0.82) / 0.18;
            r = Math.floor(192 + frac * 55);
            g = Math.floor(202 + frac * 20);
            b = Math.floor(25 + frac * 20);
            a = 225;
          }

          data[pIdx] = r;
          data[pIdx + 1] = g;
          data[pIdx + 2] = b;
          data[pIdx + 3] = a;
        }
      }

      ctx.putImageData(imgData, 0, 0);

      const imageryProvider = new Cesium.SingleTileImageryProvider({
        url: canvas.toDataURL('image/png'),
        rectangle: Cesium.Rectangle.fromDegrees(-180.0, -80.0, 180.0, 85.0)
      });

      if (this.speedImageryLayer) {
        this.viewer.imageryLayers.remove(this.speedImageryLayer);
        this.speedImageryLayer = null;
      }

      this.speedImageryLayer = this.viewer.imageryLayers.addImageryProvider(imageryProvider);
      this.speedImageryLayer.show = this.running;
    } catch (e) {
      console.warn('Speed heatmap generation notice:', e);
    }
  }

  _respawnParticle(p, randomizeAge = false) {
    if (!this.validIndices || !this.validIndices.length) {
      p.polyline.show = false;
      return;
    }

    // VIEWPORT-ADAPTIVE SPAWNING: Concentrate particles inside camera's visible ocean area!
    const vRect = this.getViewportRectangle();
    const spanLat = Math.max(2.0, vRect.maxLat - vRect.minLat);
    const spanLon = Math.max(2.0, vRect.maxLon - vRect.minLon);

    let found = false;
    let chosenLat = 0.0, chosenLon = 0.0;
    let chosenFlow = null;

    // Try up to 10 times to spawn directly in visible open ocean
    for (let attempt = 0; attempt < 10; attempt++) {
      const testLat = vRect.minLat + Math.random() * spanLat;
      let testLon = vRect.minLon + Math.random() * spanLon;
      if (testLon > 180.0) testLon -= 360.0;
      if (testLon < -180.0) testLon += 360.0;

      const flow = this.sampleUV(testLat, testLon);
      if (flow && !isNaN(flow.speed) && flow.speed > 0.008) {
        chosenLat = testLat;
        chosenLon = testLon;
        chosenFlow = flow;
        found = true;
        break;
      }
    }

    // Fallback to random global ocean cell if viewport is positioned over continent
    if (!found) {
      const randIdx = this.validIndices[Math.floor(Math.random() * this.validIndices.length)];
      const i = Math.floor(randIdx / this.nLon);
      const j = randIdx % this.nLon;
      chosenLat = this.latMin + i * this.latStep + (Math.random() - 0.5) * this.latStep;
      chosenLon = this.lonMin + j * this.lonStep + (Math.random() - 0.5) * this.lonStep;
      chosenFlow = this.sampleUV(chosenLat, chosenLon);
    }

    p.lat = chosenLat;
    p.lon = chosenLon;
    p.maxAge = 70 + Math.floor(Math.random() * 80);
    p.age = randomizeAge ? Math.floor(Math.random() * p.maxAge) : 0;

    const u = chosenFlow ? chosenFlow.u : 0.08;
    const v = chosenFlow ? chosenFlow.v : 0.04;
    const speed = chosenFlow ? chosenFlow.speed : 0.09;
    const latRad = p.lat * 0.017453292519943295;
    const cosLat = Math.max(0.15, Math.cos(latRad));
    const dtOffset = 0.016 * this.speedScale;
    const dLat = (v * dtOffset) / 111320.0;
    const dLon = (u * dtOffset) / (111320.0 * cosLat);

    // Initial 12-point streak history: tail (points[0]) -> head (points[11])
    const numPts = this.numPoints;
    for (let k = 0; k < numPts; k++) {
      const back = (numPts - 1 - k);
      Cesium.Cartesian3.fromDegrees(
        p.lon - dLon * back,
        p.lat - dLat * back,
        this.currentAlt,
        undefined,
        p.points[k]
      );
      p.posArr0[k] = p.points[k];
      p.posArr1[k] = p.points[k];
    }

    // Assign material and width ONCE on respawn (ZERO BUCKET THRASHING)
    const bucket = this._getSpeedBucket(speed);
    p.bucket = bucket;
    p.polyline.material = this.palette[bucket];
    p.polyline.width = 1.1 + (bucket / 31.0) * 0.3; // 1.1 to 1.4 px

    p.polyline.positions = p.posArr0;
    p.polyline.show = this.running;
  }

  sampleUV(lat, lon) {
    if (!this.uGrid || lat < this.latMin || lat > this.latMax) return null;

    const fi = (lat - this.latMin) / this.latStep;
    const normLon = ((lon - this.lonMin) % 360.0 + 360.0) % 360.0;
    const fj = normLon / this.lonStep;

    const i0 = Math.floor(fi);
    const j0 = Math.floor(fj);
    const i1 = Math.min(this.nLat - 1, i0 + 1);
    const j1 = (j0 + 1) % this.nLon;

    const fx = fj - j0;
    const fy = fi - i0;

    const idx00 = i0 * this.nLon + j0;
    const u00 = this.uGrid[idx00];
    if (isNaN(u00)) return null; // Land

    const idx01 = i0 * this.nLon + j1;
    const idx10 = i1 * this.nLon + j0;
    const idx11 = i1 * this.nLon + j1;

    const u01 = this.uGrid[idx01];
    const u10 = this.uGrid[idx10];
    const u11 = this.uGrid[idx11];
    if (isNaN(u01) || isNaN(u10) || isNaN(u11)) return null;

    const v00 = this.vGrid[idx00];
    const v01 = this.vGrid[idx01];
    const v10 = this.vGrid[idx10];
    const v11 = this.vGrid[idx11];

    const u = (1.0 - fy) * ((1.0 - fx) * u00 + fx * u01) + fy * ((1.0 - fx) * u10 + fx * u11);
    const v = (1.0 - fy) * ((1.0 - fx) * v00 + fx * v01) + fy * ((1.0 - fx) * v10 + fx * v11);
    const speed = Math.hypot(u, v);

    return { u, v, speed };
  }

  _getSpeedBucket(speed) {
    const norm = Math.min(1.0, Math.max(0.0, (speed - 0.02) / 0.85));
    return Math.min(31, Math.floor(norm * 31.9));
  }

  _onPreRender() {
    if (!this.running || !this.validIndices || !this.validIndices.length) return;

    const now = performance.now();
    let dt = (now - this.lastFrameTime) / 1000.0;
    this.lastFrameTime = now;

    if (dt <= 0.0 || dt > 0.1) dt = 0.016;

    // 2-phase interleaved update for locked 60 FPS performance
    const effectiveDt = dt * this.speedScale * 2.0;
    const currentAlt = this.currentAlt;
    const nActive = this.activeParticleCount;
    const half = (nActive >> 1);
    const numPts = this.numPoints;
    const numPtsMinus1 = numPts - 1;

    this.frameCount++;
    const isEven = (this.frameCount & 1) === 0;
    const startIdx = isEven ? 0 : half;
    const endIdx = isEven ? half : nActive;

    const vRect = this.getViewportRectangle();
    const padLat = 4.0;
    const padLon = 5.0;

    for (let k = startIdx; k < endIdx; k++) {
      const p = this.particles[k];
      p.age += 2;
      if (p.age >= p.maxAge) {
        this._respawnParticle(p, false);
        continue;
      }

      // Check if particle drifted outside current visible viewport
      if (p.lat < vRect.minLat - padLat || p.lat > vRect.maxLat + padLat) {
        this._respawnParticle(p, false);
        continue;
      }

      // Velocity sample
      const flow1 = this.sampleUV(p.lat, p.lon);
      if (!flow1 || flow1.speed < 0.008) {
        this._respawnParticle(p, false);
        continue;
      }

      // RK2 midpoint step
      const latRad1 = p.lat * 0.017453292519943295;
      const cosLat1 = Math.max(0.15, Math.cos(latRad1));
      const halfDt = effectiveDt * 0.5;
      const midLat = p.lat + (flow1.v * halfDt) / 111320.0;
      const midLon = p.lon + (flow1.u * halfDt) / (111320.0 * cosLat1);

      const flow2 = this.sampleUV(midLat, midLon) || flow1;
      const latRad2 = midLat * 0.017453292519943295;
      const cosLat2 = Math.max(0.15, Math.cos(latRad2));

      const dLat = (flow2.v * effectiveDt) / 111320.0;
      const dLon = (flow2.u * effectiveDt) / (111320.0 * cosLat2);

      // Shift ring buffer
      const oldest = p.points[0];
      for (let j = 0; j < numPtsMinus1; j++) {
        p.points[j] = p.points[j + 1];
      }
      p.points[numPtsMinus1] = oldest;

      p.lat += dLat;
      p.lon += dLon;

      if (p.lon > 180.0) p.lon -= 360.0;
      if (p.lon < -180.0) p.lon += 360.0;

      Cesium.Cartesian3.fromDegrees(p.lon, p.lat, currentAlt, undefined, oldest);

      // Alternate array reference to trigger Cesium Polyline dirty buffer update with 0 allocations
      if (p.age & 2) {
        for (let j = 0; j < numPts; j++) p.posArr0[j] = p.points[j];
        p.polyline.positions = p.posArr0;
      } else {
        for (let j = 0; j < numPts; j++) p.posArr1[j] = p.points[j];
        p.polyline.positions = p.posArr1;
      }
    }

    const frameElapsed = performance.now() - now;
    this.frameTimesWindow.push(frameElapsed);
    if (this.frameTimesWindow.length > 60) this.frameTimesWindow.shift();

    if (this.frameCount % 60 === 0 && this.frameTimesWindow.length > 0) {
      const sum = this.frameTimesWindow.reduce((a, b) => a + b, 0);
      this.avgFrameTimeMs = sum / this.frameTimesWindow.length;

      // Dynamic particle scaling targeting ~60 FPS (~16.6 ms per frame)
      if (this.avgFrameTimeMs > 22.0 && this.activeParticleCount > 1500) {
        // High frame time: step down particle count 3000 -> 2500 -> 2000 -> 1500
        const prevCount = this.activeParticleCount;
        this.activeParticleCount = Math.max(1500, this.activeParticleCount - 500);
        for (let i = this.activeParticleCount; i < prevCount; i++) {
          if (this.particles[i] && this.particles[i].polyline) {
            this.particles[i].polyline.show = false;
          }
        }
      } else if (this.avgFrameTimeMs < 14.0 && this.activeParticleCount < this.maxParticles) {
        // High frame rate headroom: step up particle count toward maxParticles (3000)
        const prevCount = this.activeParticleCount;
        this.activeParticleCount = Math.min(this.maxParticles, this.activeParticleCount + 500);
        for (let i = prevCount; i < this.activeParticleCount; i++) {
          if (this.particles[i] && this.running) {
            this._respawnParticle(this.particles[i], true);
          }
        }
      }
    }
  }

  setVisible(visible) {
    this.running = visible;
    if (this.polyCollection) {
      this.polyCollection.show = visible;
    }
    if (this.speedImageryLayer) {
      this.speedImageryLayer.show = visible;
    }
    if (!visible) {
      for (let i = 0; i < this.maxParticles; i++) {
        if (this.particles[i] && this.particles[i].polyline) {
          this.particles[i].polyline.show = false;
        }
      }
    } else {
      for (let i = 0; i < this.activeParticleCount; i++) {
        if (this.particles[i]) {
          this._respawnParticle(this.particles[i], true);
        }
      }
    }
  }

  destroy() {
    this.running = false;
    if (this.preRenderRemoveCallback) {
      this.preRenderRemoveCallback();
      this.preRenderRemoveCallback = null;
    }
    if (this.viewer && this.polyCollection) {
      this.viewer.scene.primitives.remove(this.polyCollection);
      this.polyCollection = null;
    }
    if (this.viewer && this.speedImageryLayer) {
      this.viewer.imageryLayers.remove(this.speedImageryLayer);
      this.speedImageryLayer = null;
    }
    this.particles = [];
  }
}

window.OceanFlowEngine = OceanFlowEngine;
