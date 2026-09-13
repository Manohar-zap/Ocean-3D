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

    // Initialize authoritative state at Stage 1
    this.goToStage(1);

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
           <div class="stage-3-content">
              <h2 class="stage-title">OCEAN OBSERVATIONS</h2>
              <p class="stage-subtitle">LOCATION • DEPTH • TIME • MEASUREMENTS</p>
           </div>
        </div>

        <!-- Stage 4: Ocean Model + Observations -->
        <div class="intro-stage" id="intro-stage-4">
          <div class="synthesis-wrap">
             <div class="synthesis-item">
                <div class="synthesis-icon">🌊</div>
                <div class="synthesis-label">OCEAN MODEL</div>
                <div class="synthesis-sub">Numerical Simulations</div>
             </div>
             <div class="synthesis-operator">+</div>
             <div class="synthesis-item">
                <div class="synthesis-icon">🛰️</div>
                <div class="synthesis-label">OBSERVATIONS</div>
                <div class="synthesis-sub">Real-World Data</div>
             </div>
             <div class="synthesis-operator">→</div>
             <div class="synthesis-item">
                <div class="synthesis-icon">🌍</div>
                <div class="synthesis-label">OCEAN 3D</div>
                <div class="synthesis-sub">Integrated View</div>
             </div>
          </div>
        </div>

        <!-- Stage 5: Explore the Ocean -->
        <div class="intro-stage" id="intro-stage-5">
          <div class="capabilities-grid">
            <div class="cap-item">
              <div class="cap-icon">🌊</div>
              <div class="cap-name">OCEAN CURRENTS</div>
              <div class="cap-desc">3D Streamlines • Particles</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">🌡️</div>
              <div class="cap-name">OCEAN VARIABLES</div>
              <div class="cap-desc">Temperature • Salinity</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">⬇️</div>
              <div class="cap-name">DEPTH ANALYSIS</div>
              <div class="cap-desc">Surface to Deep Ocean</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">🌍</div>
              <div class="cap-name">3D VISUALIZATION</div>
              <div class="cap-desc">Analysis Environment</div>
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
    const headerEl = this.container.querySelector('.intro-section-header');

    // Section Titles & Subtitles
    const headers = [
      { title: '', subtitle: '' },
      { title: 'OBSERVATION INSTRUMENTS', subtitle: 'Five ways we observe the ocean' },
      { title: 'OCEAN OBSERVATIONS', subtitle: 'Location • Depth • Time • Measurements' },
      { title: 'OCEAN MODEL + OBSERVATIONS', subtitle: 'Integrating theoretical models with real-world data' },
      { title: 'EXPLORE THE OCEAN', subtitle: 'Interactive discovery through the Ocean 3D platform' }
    ];

    if (titleEl && subtitleEl && headerEl) {
      const h = headers[this.currentStage - 1];
      titleEl.textContent = h.title;
      subtitleEl.textContent = h.subtitle;

      // Only Stage 2 uses the global fixed header in this simplified design
      headerEl.classList.toggle('active', this.currentStage === 2);
    }

    // Navigation Buttons
    if (backBtn) {
      backBtn.style.visibility = (this.currentStage === 1) ? 'hidden' : 'visible';
    }
    if (nextBtn) {
      nextBtn.textContent = (this.currentStage === this.totalStages) ? 'ENTER OCEAN 3D →' : 'NEXT →';
    }

    // Progress Indicator
    if (progressEl) {
      progressEl.textContent = `0${this.currentStage} / 05`;
    }
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
