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
              <div class="platform-icon-anim"><div class="argo-trace"></div><div class="argo-dot"></div></div>
              <div class="platform-name">ARGO FLOAT</div>
              <div class="platform-desc">Autonomous floats that profile the ocean vertically.<br>Measures temperature, salinity and pressure.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim"><div class="mooring-line"></div><div class="buoy-base"></div><div class="pulse"></div></div>
              <div class="platform-name">MOORED BUOY</div>
              <div class="platform-desc">Fixed ocean stations for continuous monitoring.<br>Measures ocean conditions from a stable location.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim"><div class="glider-dot"></div></div>
              <div class="platform-name">AUTONOMOUS GLIDER</div>
              <div class="platform-desc">Moves through the ocean while collecting observations.<br>Builds a spatial profile along its trajectory.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim"><div class="ship-icon"></div><div class="ctd-probe"></div></div>
              <div class="platform-name">SHIPBOARD CTD</div>
              <div class="platform-desc">Lowered from research vessels to sample the water column.<br>Measures conductivity, temperature and depth.</div>
            </div>
            <div class="platform-box">
              <div class="platform-icon-anim"><div class="bgc-dot"></div><div class="bgc-bubble" style="left:20px;bottom:20px;"></div><div class="bgc-bubble" style="left:40px;bottom:40px;animation-delay:1s;"></div></div>
              <div class="platform-name">BGC-ARGO</div>
              <div class="platform-desc">Argo floats focused on biogeochemical conditions.<br>Measures variables such as oxygen and chlorophyll.</div>
            </div>
          </div>
        </div>

        <!-- Stage 3: Ocean Observations -->
        <div class="intro-stage" id="intro-stage-3">
           <div class="obs-visual-wrap">
             <div class="arch-visual">
                <div class="data-particle" style="top:20%; left:10%; animation-delay:0s;"></div>
                <div class="data-particle" style="top:50%; left:20%; animation-delay:0.5s;"></div>
                <div class="data-particle" style="top:80%; left:15%; animation-delay:1s;"></div>
                <div class="data-particle" style="top:30%; left:80%; animation-delay:0.2s;"></div>
                <div class="data-particle" style="top:60%; left:70%; animation-delay:0.7s;"></div>
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
                <div class="merge-side">
                  <div class="merge-label">OCEAN MODEL</div>
                  <div class="merge-icon">🧊</div>
                </div>
                <div class="merge-plus">+</div>
                <div class="merge-side">
                  <div class="merge-label">OBSERVATIONS</div>
                  <div class="merge-icon">📡</div>
                </div>
                <div class="merge-equals">=</div>
                <div class="merge-result">
                  <div class="merge-label">OCEAN 3D</div>
                  <div class="merge-icon large">🌍</div>
                </div>
             </div>
          </div>
        </div>

        <!-- Stage 5: Explore the Ocean -->
        <div class="intro-stage" id="intro-stage-5">
          <div class="intro-caps">
            <div class="cap-item">
              <div class="cap-icon"><div class="flow-lines"><div class="flow-line" style="top:5px;"></div><div class="flow-line" style="top:15px;animation-delay:0.5s;"></div></div></div>
              <div class="cap-label">OCEAN CURRENTS</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">🌡️</div>
              <div class="cap-label">OCEAN VARIABLES</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon"><div class="depth-gauge"><div class="depth-marker"></div></div></div>
              <div class="cap-label">DEPTH ANALYSIS</div>
            </div>
            <div class="cap-item">
              <div class="cap-icon">🌍</div>
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
