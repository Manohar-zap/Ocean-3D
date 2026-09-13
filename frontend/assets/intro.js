/**
 * OCEAN 3D — Refined Interactive Intro Manager
 * Orchestrates a 5-stage interactive story with user controls.
 */

class Ocean3DIntro {
  constructor() {
    this.container = null;
    this.currentStage = 1;
    this.totalStages = 5;
    this.particles = [];
    this.isSkipped = false;

    // Auto-advance is disabled to give user control, but we keep timing references for initial fades
    this.timings = {
      fade: 600
    };
  }

  init() {
    // Check if intro was already shown in this session
    if (sessionStorage.getItem('ocean3d_intro_shown')) {
      this.removeIntro();
      return;
    }

    this.createDOM();
    this.generateParticles();
    this.updateUI();

    // Staggered entrance for Stage 1
    setTimeout(() => {
      this.goToStage(1);
    }, 100);

    // Keyboard navigation
    window.addEventListener('keydown', this.handleKeydown.bind(this));
  }

  handleKeydown(e) {
    if (this.isSkipped) return;
    if (e.key === 'ArrowRight' || e.key === 'Enter' || e.key === ' ') {
      this.next();
    } else if (e.key === 'ArrowLeft' || e.key === 'Backspace') {
      this.prev();
    } else if (e.key === 'Escape') {
      this.skip();
    }
  }

  createDOM() {
    this.container = document.createElement('div');
    this.container.id = 'ocean3d-intro';

    // Define SVG Illustrations
    const svgIcons = {
      argo: `<svg viewBox="0 0 40 100" class="svg-instrument">
        <rect x="15" y="20" width="10" height="60" rx="5" fill="#f2a65a" />
        <line x1="20" y1="20" x2="20" y2="5" stroke="#7c93a0" stroke-width="1.5" />
        <circle cx="20" y="5" r="2" fill="#fff" />
        <rect x="14" y="30" width="12" height="2" fill="rgba(0,0,0,0.2)" />
        <rect x="14" y="70" width="12" height="2" fill="rgba(0,0,0,0.2)" />
      </svg>`,
      buoy: `<svg viewBox="0 0 60 100" class="svg-instrument">
        <ellipse cx="30" y="30" rx="20" ry="8" fill="#38bdf8" />
        <rect x="28" y="5" width="4" height="25" fill="#7c93a0" />
        <circle cx="30" y="5" r="3" fill="#e8654f" />
        <line x1="30" y1="38" x2="30" y2="95" stroke="#38bdf8" stroke-width="1" stroke-dasharray="4 2" />
      </svg>`,
      glider: `<svg viewBox="0 0 80 60" class="svg-instrument glider-svg">
        <path d="M10,30 Q10,20 40,20 L70,30 L40,40 Q10,40 10,30" fill="#8ec9e0" />
        <path d="M40,20 L30,5 L50,5 L45,20" fill="#1a2f3c" />
        <path d="M40,40 L30,55 L50,55 L45,40" fill="#1a2f3c" />
        <circle cx="65" cy="30" r="2" fill="#fff" opacity="0.5" />
      </svg>`,
      ctd: `<svg viewBox="0 0 60 100" class="svg-instrument">
        <rect x="15" y="10" width="30" height="2" fill="#c58ee0" />
        <rect x="15" y="80" width="30" height="2" fill="#c58ee0" />
        <line x1="20" y1="10" x2="20" y2="80" stroke="#c58ee0" stroke-width="1" />
        <line x1="40" y1="10" x2="40" y2="80" stroke="#c58ee0" stroke-width="1" />
        <rect x="22" y="15" width="4" height="60" rx="1" fill="#dceaf0" opacity="0.8" />
        <rect x="28" y="15" width="4" height="60" rx="1" fill="#dceaf0" opacity="0.8" />
        <rect x="34" y="15" width="4" height="60" rx="1" fill="#dceaf0" opacity="0.8" />
      </svg>`,
      bgc: `<svg viewBox="0 0 40 100" class="svg-instrument">
        <rect x="15" y="25" width="10" height="60" rx="5" fill="#8ee0a4" />
        <line x1="20" y1="25" x2="20" y2="5" stroke="#7c93a0" stroke-width="1.5" />
        <circle cx="25" cy="45" r="3" fill="#3fe0c5" opacity="0.6">
          <animate attributeName="r" values="3;5;3" dur="2s" repeatCount="indefinite" />
        </circle>
        <circle cx="15" cy="65" r="2" fill="#3fe0c5" opacity="0.4" />
      </svg>`
    };

    this.container.innerHTML = `
      <div class="intro-particles"></div>

      <!-- Section Titles (Global) -->
      <div class="intro-section-header">
        <h2 id="intro-section-title"></h2>
        <p id="intro-section-subtitle"></p>
      </div>

      <div class="intro-content">
        <!-- Stage 1: Identity -->
        <div class="intro-stage" id="intro-stage-1">
          <div class="intro-identity">
            <h1 class="intro-title">OCEAN 3D</h1>
            <div class="intro-subtitle">Ocean Data Visualization & Analysis</div>
          </div>
        </div>

        <!-- Stage 2: Observation Instruments -->
        <div class="intro-stage" id="intro-stage-2">
          <div class="intro-platforms">
            <div class="platform-box">
              <div class="platform-icon-anim argo-anim">${svgIcons.argo}</div>
              <div class="platform-name">ARGO FLOAT</div>
              <div class="platform-desc">Autonomous floats that profile the ocean vertically.<br>Measures temperature, salinity and pressure.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim buoy-anim">${svgIcons.buoy}</div>
              <div class="platform-name">MOORED BUOY</div>
              <div class="platform-desc">Fixed ocean stations for continuous monitoring.<br>Measures ocean conditions from a stable location.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim glider-anim">${svgIcons.glider}</div>
              <div class="platform-name">AUTONOMOUS GLIDER</div>
              <div class="platform-desc">Moves through the ocean while collecting observations.<br>Builds a spatial profile along its trajectory.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim ctd-anim">${svgIcons.ctd}</div>
              <div class="platform-name">SHIPBOARD CTD</div>
              <div class="platform-desc">Lowered from research vessels to sample the water column.<br>Measures conductivity, temperature and depth.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim bgc-anim">${svgIcons.bgc}</div>
              <div class="platform-name">BGC-ARGO</div>
              <div class="platform-desc">Argo floats focused on biogeochemical conditions.<br>Measures variables such as oxygen and chlorophyll.</div>
            </div>
          </div>
        </div>

        <!-- Stage 3: Ocean Observations -->
        <div class="intro-stage" id="intro-stage-3">
           <div class="obs-visual-wrap">
              <div class="scientific-data-map">
                <div class="map-grid"></div>
                <div class="data-stream-path argo-path"></div>
                <div class="data-stream-path glider-path"></div>
                <div class="data-point argo-pt"></div>
                <div class="data-point glider-pt"></div>
                <div class="data-point buoy-pt"></div>
              </div>
              <div class="obs-flow-text">
                <div class="flow-item">INSTRUMENTS</div>
                <div class="flow-arrow">→</div>
                <div class="flow-item highlight">OCEAN OBSERVATIONS</div>
              </div>
           </div>
        </div>

        <!-- Stage 4: Ocean Model + Observations -->
        <div class="intro-stage" id="intro-stage-4">
          <div class="merge-visual-wrap">
             <div class="merge-grid"></div>
             <div class="merge-content">
                <div class="merge-side model-side">
                  <div class="merge-label">OCEAN MODEL</div>
                  <div class="scientific-icon model-icon">
                    <div class="grid-3d"></div>
                  </div>
                </div>
                <div class="merge-plus">+</div>
                <div class="merge-side obs-side">
                  <div class="merge-label">OBSERVATIONS</div>
                  <div class="scientific-icon obs-icon">
                    <div class="points-3d"></div>
                  </div>
                </div>
                <div class="merge-equals">=</div>
                <div class="merge-result">
                  <div class="merge-label">OCEAN 3D</div>
                  <div class="scientific-icon result-icon">
                    <div class="globe-mini">
                      <div class="globe-ring"></div>
                      <div class="globe-ring" style="transform: rotateY(60deg)"></div>
                      <div class="globe-ring" style="transform: rotateY(120deg)"></div>
                    </div>
                  </div>
                </div>
             </div>
          </div>
        </div>

        <!-- Stage 5: Explore the Ocean -->
        <div class="intro-stage" id="intro-stage-5">
          <div class="intro-caps">
            <div class="cap-item">
              <div class="cap-icon">
                <svg viewBox="0 0 100 60" class="streamline-svg">
                  <path d="M10,30 Q30,10 50,30 T90,30" class="stream-path" />
                  <path d="M10,45 Q30,25 50,45 T90,45" class="stream-path" style="animation-delay: 0.5s" />
                  <circle r="2" fill="#3fe0c5" class="stream-particle" />
                </svg>
              </div>
              <div class="cap-label">OCEAN CURRENTS</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">
                <div class="variable-field">
                  <div class="field-band"></div>
                  <div class="field-band"></div>
                  <div class="field-band"></div>
                </div>
              </div>
              <div class="cap-label">OCEAN VARIABLES</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">
                <div class="depth-ruler">
                  <div class="ruler-line"></div>
                  <div class="ruler-mark"></div>
                </div>
              </div>
              <div class="cap-label">DEPTH ANALYSIS</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">
                <div class="analysis-3d">
                  <div class="box-3d"></div>
                  <div class="box-3d-line"></div>
                </div>
              </div>
              <div class="cap-label">3D VISUALIZATION</div>
            </div>
          </div>
          <div class="final-cta">LOCATION • DEPTH • TIME</div>
        </div>
      </div>

      <!-- Navigation Bar -->
      <div class="intro-nav-bar">
        <button id="btn-back" class="nav-btn secondary">← BACK</button>
        <div class="intro-progress" id="intro-progress-text">01 / 05</div>
        <button id="btn-next" class="nav-btn primary">NEXT →</button>
      </div>

      <button id="skip-intro">Skip Intro</button>
    `;

    document.body.appendChild(this.container);

    document.getElementById('btn-next').addEventListener('click', () => this.next());
    document.getElementById('btn-back').addEventListener('click', () => this.prev());
    document.getElementById('skip-intro').addEventListener('click', () => this.skip());
  }

  generateParticles() {
    const pContainer = this.container.querySelector('.intro-particles');
    for (let i = 0; i < 40; i++) {
      const p = document.createElement('div');
      p.className = 'particle';
      const size = Math.random() * 3 + 1;
      p.style.width = `${size}px`;
      p.style.height = `${size}px`;
      p.style.left = `${Math.random() * 100}%`;
      p.style.top = `${Math.random() * 100}%`;
      p.style.setProperty('--dx', `${(Math.random() - 0.5) * 200}px`);
      p.style.setProperty('--dy', `${(Math.random() - 0.5) * 200}px`);
      p.style.animationDuration = `${Math.random() * 10 + 10}s`;
      p.style.animationDelay = `${Math.random() * -20}s`;
      pContainer.appendChild(p);
    }
  }

  next() {
    if (this.currentStage < this.totalStages) {
      this.goToStage(this.currentStage + 1);
    } else {
      this.finish();
    }
  }

  prev() {
    if (this.currentStage > 1) {
      this.goToStage(this.currentStage - 1);
    }
  }

  goToStage(n) {
    this.currentStage = n;

    // Update Stage Visibility
    const stages = this.container.querySelectorAll('.intro-stage');
    stages.forEach((s, idx) => {
      s.classList.toggle('active', (idx + 1) === n);
    });

    this.updateUI();
  }

  updateUI() {
    const titleEl = document.getElementById('intro-section-title');
    const subtitleEl = document.getElementById('intro-section-subtitle');
    const nextBtn = document.getElementById('btn-next');
    const backBtn = document.getElementById('btn-back');
    const progressEl = document.getElementById('intro-progress-text');

    // Section Titles & Subtitles
    const headers = [
      { title: '', subtitle: '' },
      { title: 'OBSERVATION INSTRUMENTS', subtitle: 'Five ways we observe the ocean' },
      { title: 'OCEAN OBSERVATIONS', subtitle: 'Location • Depth • Time • Measurements' },
      { title: 'OCEAN MODEL + OBSERVATIONS', subtitle: 'Integrating theoretical models with real-world data' },
      { title: 'EXPLORE THE OCEAN', subtitle: 'Interactive discovery through the Ocean 3D platform' }
    ];

    const h = headers[this.currentStage - 1];
    titleEl.textContent = h.title;
    subtitleEl.textContent = h.subtitle;

    // Navigation Buttons
    backBtn.style.visibility = (this.currentStage === 1) ? 'hidden' : 'visible';
    nextBtn.textContent = (this.currentStage === this.totalStages) ? 'ENTER OCEAN 3D →' : 'NEXT →';

    // Progress Indicator
    progressEl.textContent = `0${this.currentStage} / 05`;
  }

  skip() {
    this.isSkipped = true;
    this.finish();
  }

  finish() {
    this.container.classList.add('hidden');
    sessionStorage.setItem('ocean3d_intro_shown', 'true');
    setTimeout(() => this.removeIntro(), 1000);
  }

  removeIntro() {
    if (this.container && this.container.parentNode) {
      this.container.parentNode.removeChild(this.container);
    }
    // Ensure app is visible and interactive
    const app = document.getElementById('app');
    if (app) {
      app.style.visibility = 'visible';
      app.style.opacity = '1';
    }
  }
}

// Initialize on load
window.addEventListener('DOMContentLoaded', () => {
  const intro = new Ocean3DIntro();
  intro.init();
});
