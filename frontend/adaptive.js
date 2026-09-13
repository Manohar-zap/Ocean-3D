/* Ocean 3D — Adaptive Observation decision UI */
(function () {
  function boot() {
    const main = document.querySelector('main');
    if (!main || document.getElementById('adaptivePanel')) return;

    const toggle = document.createElement('button');
    toggle.id = 'adaptiveToggle';
    toggle.textContent = 'ADAPTIVE OBSERVATION';
    main.appendChild(toggle);

    const panel = document.createElement('section');
    panel.id = 'adaptivePanel';
    panel.innerHTML = `
      <div class="ap-head">
        <div><div class="ap-title">Adaptive Observation Engine</div><div class="ap-sub">Uncertainty → information gap → mission recommendation</div></div>
        <button class="ap-close" aria-label="Close">×</button>
      </div>
      <div class="ap-body">
        <div class="ap-grid">
          <div class="ap-field"><label>Latitude</label><input id="apLat" type="number" step="0.1" value="12.0"></div>
          <div class="ap-field"><label>Longitude</label><input id="apLon" type="number" step="0.1" value="72.0"></div>
          <div class="ap-field"><label>Depth (m)</label><input id="apDepth" type="number" min="0" step="25" value="100"></div>
          <div class="ap-field"><label>Variable</label><select id="apVar"><option value="temperature">Temperature</option><option value="salinity">Salinity</option></select></div>
          <div class="ap-field" style="grid-column:1/3"><label>Platform</label><select id="apPlatform"><option value="glider">Glider</option><option value="auv">AUV</option><option value="argo">Argo</option></select></div>
        </div>
        <button class="ap-button" id="apAnalyze">ANALYZE INFORMATION GAP</button>
        <div class="ap-status" id="apStatus">Ready.</div>

        <div class="ap-score">
          <div class="ap-card"><div class="ap-label">Uncertainty</div><div class="ap-value warn" id="apUncertainty">—</div><div class="ap-bar"><div id="apUncertaintyBar"></div></div></div>
          <div class="ap-card"><div class="ap-label">Confidence</div><div class="ap-value good" id="apConfidence">—</div><div class="ap-bar"><div id="apConfidenceBar"></div></div></div>
        </div>

        <div class="ap-section">
          <div class="ap-section-title">Why is this a gap?</div>
          <div class="ap-row"><span>Spatial gap</span><b id="apSpatial">—</b></div>
          <div class="ap-row"><span>Temporal staleness</span><b id="apTemporal">—</b></div>
          <div class="ap-row"><span>Model disagreement</span><b id="apDisagreement">—</b></div>
          <div class="ap-row"><span>Nearest observation</span><b id="apNearest">—</b></div>
        </div>

        <div class="ap-section">
          <div class="ap-section-title">Decision</div>
          <div class="ap-recommend monitor" id="apRecommendation">Run analysis to evaluate whether a new observation is justified.</div>
          <div class="ap-row"><span>Feasibility</span><b id="apFeasibility">—</b></div>
          <div class="ap-row"><span>Utility score</span><b id="apUtility">—</b></div>
          <div class="ap-row"><span>Nearest platform</span><b id="apNearestPlatform">—</b></div>
        </div>

        <button class="ap-button secondary" id="apSimulate">RUN WHAT-IF OBSERVATION</button>
        <div class="ap-sim">
          <div class="ap-card"><div class="ap-label">Before</div><div class="ap-value warn" id="apBefore">—</div></div>
          <div class="ap-card"><div class="ap-label">After</div><div class="ap-value good" id="apAfter">—</div></div>
        </div>
        <div class="ap-status" id="apSimStatus">Simulation uses synthetic data only.</div>
      </div>`;
    main.appendChild(panel);

    const $ = (id) => document.getElementById(id);
    const api = (path) => {
      if (typeof window.apiUrl === 'function') return window.apiUrl(path);
      return `http://localhost:8000${path}`;
    };
    const params = () => new URLSearchParams({
      lat: $('apLat').value,
      lon: $('apLon').value,
      depth: $('apDepth').value,
      variable: $('apVar').value,
      platform: $('apPlatform').value
    });

    async function getJson(path) {
      const response = await fetch(api(path));
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    }

    async function analyze() {
      $('apStatus').textContent = 'Computing uncertainty and observation value…';
      try {
        const p = params();
        const [gap, rec] = await Promise.all([
          getJson(`/api/adaptive/score?lat=${p.get('lat')}&lon=${p.get('lon')}&depth=${p.get('depth')}&variable=${p.get('variable')}`),
          getJson(`/api/adaptive/recommend?${p.toString()}`)
        ]);
        $('apUncertainty').textContent = `${gap.uncertainty}%`;
        $('apConfidence').textContent = `${gap.confidence}%`;
        $('apUncertaintyBar').style.width = `${gap.uncertainty}%`;
        $('apConfidenceBar').style.width = `${gap.confidence}%`;
        $('apSpatial').textContent = `${gap.components.spatial_gap}%`;
        $('apTemporal').textContent = `${gap.components.temporal_gap}%`;
        $('apDisagreement').textContent = `${gap.components.model_observation_disagreement}%`;
        $('apNearest').textContent = `${gap.nearest_observation_km} km`;
        $('apFeasibility').textContent = `${rec.feasibility}%`;
        $('apUtility').textContent = `${rec.utility_score}`;
        $('apNearestPlatform').textContent = rec.nearest_platform.platform_id ? `${rec.nearest_platform.platform_id} (${rec.nearest_platform.distance_km} km)` : 'No nearby platform';
        const box = $('apRecommendation');
        box.classList.toggle('monitor', rec.decision !== 'RECOMMEND');
        box.textContent = `${rec.decision}: ${rec.recommended_action}. Target ${rec.waypoint.latitude}°, ${rec.waypoint.longitude}°, ${rec.waypoint.depth_m} m.`;
        $('apStatus').textContent = `Analysis complete • ${gap.provenance}`;
      } catch (err) {
        $('apStatus').textContent = `Analysis failed: ${err.message}`;
      }
    }

    async function simulate() {
      $('apSimStatus').textContent = 'Running virtual observation…';
      try {
        const p = params();
        const data = await getJson(`/api/adaptive/simulate?lat=${p.get('lat')}&lon=${p.get('lon')}&depth=${p.get('depth')}&variable=${p.get('variable')}`);
        $('apBefore').textContent = `${data.before.uncertainty}%`;
        $('apAfter').textContent = `${data.after.uncertainty}%`;
        $('apSimStatus').textContent = `Simulated uncertainty reduction: ${data.uncertainty_reduction_percent}%. ${data.provenance}`;
      } catch (err) {
        $('apSimStatus').textContent = `Simulation failed: ${err.message}`;
      }
    }

    toggle.addEventListener('click', () => panel.classList.toggle('open'));
    panel.querySelector('.ap-close').addEventListener('click', () => panel.classList.remove('open'));
    $('apAnalyze').addEventListener('click', analyze);
    $('apSimulate').addEventListener('click', simulate);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
