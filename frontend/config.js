// OCEAN 3D Frontend Configuration
window.CESIUM_ION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6Ijdtb25zbDBVQV9PSjVYVjYiLCJqdGkiOiI1YzlkMzc4Zi1lZWQ2LTRhMjktOTYyZi00MjlmNGNhOGYxMDUiLCJpZCI6NDgwODM2LCJpc3MiOiJodHRwczovL2FwaS5jZXNpdW0uY29tIiwiYXVkIjoidW5kZWZpbmVkX2RlZmF1bHQiLCJpYXQiOjE3ODg1NDEwNTl9.cxmIfvWN4Q0PBNwM4HjlRBvaBpNSnP9dZSa30-A4rT8";

// Expose the Cesium Viewer instance to optional feature modules loaded below.
// The main app still owns the viewer; feature modules only add/read entities.
if (window.Cesium && window.Cesium.Viewer) {
  const Ocean3DViewer = window.Cesium.Viewer;
  window.Cesium.Viewer = function (...args) {
    const instance = new Ocean3DViewer(...args);
    window.oceanViewer = instance;
    return instance;
  };
  window.Cesium.Viewer.prototype = Ocean3DViewer.prototype;
}

// Adaptive Observation feature is loaded as a standalone frontend module.
(function loadAdaptiveObservation() {
  const script = document.createElement('script');
  script.src = 'adaptive-observation.js';
  script.defer = true;
  document.head.appendChild(script);
})();
