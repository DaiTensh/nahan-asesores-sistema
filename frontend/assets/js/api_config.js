(function () {
  const liveServerOrigins = new Set([
    "http://127.0.0.1:5500",
    "http://localhost:5500"
  ]);

  const API_URL = liveServerOrigins.has(window.location.origin)
    ? "http://127.0.0.1:5000/api"
    : "/api";

  window.API_CONFIG = {
    API_URL,
    credentials: "include"
  };
})();
