// OCEAN 3D Frontend Configuration
window.CESIUM_ION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6Ijdtb25zbDBVQV9PSjVYVjYiLCJqdGkiOiI1YzlkMzc4Zi1lZWQ2LTRhMjktOTYyZi00MjlmNGNhOGYxMDUiLCJpZCI6NDgwODM2LCJpc3MiOiJodHRwczovL2FwaS5jZXNpdW0uY29tIiwiYXVkIjoidW5kZWZpbmVkX2RlZmF1bHQiLCJpYXQiOjE3ODg1NDEwNTl9.cxmIfvWN4Q0PBNM4HjlRBvaBpNSnP9dZSa30-A4rT8";

// Adaptive observation decision layer is loaded separately so the existing
// Cesium/Three.js application remains untouched and independently replaceable.
(function loadAdaptiveObservationModule() {
  var css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = 'adaptive.css';
  document.head.appendChild(css);

  var script = document.createElement('script');
  script.src = 'adaptive.js';
  script.defer = true;
  document.head.appendChild(script);
})();
