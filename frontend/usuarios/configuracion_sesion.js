// RF59 — Configuración del tiempo de inactividad (solo administradores).
(function () {
  const API_URL = window.API_CONFIG.API_URL;

  function mostrarMensaje(texto, tipo) {
    const mensaje = document.getElementById("mensajeSesion");
    mensaje.textContent = texto || "";
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }

  async function cargar() {
    try {
      const response = await fetch(`${API_URL}/parametros/sesion`, {
        credentials: window.API_CONFIG.credentials
      });
      if (!response.ok) return;
      const data = await response.json();
      document.getElementById("inputMinutos").value = data.limite_minutos;
      document.getElementById("inputAviso").value = data.aviso_segundos;
    } catch (error) {
      console.error(error);
    }
  }

  async function guardar(event) {
    event.preventDefault();
    const minutos = Number(document.getElementById("inputMinutos").value);
    const aviso = Number(document.getElementById("inputAviso").value);

    if (aviso >= minutos * 60) {
      mostrarMensaje("El aviso debe mostrarse antes de que termine el tiempo de inactividad.", "error");
      return;
    }
    if (!confirm(`¿Guardar el cierre automático a los ${minutos} minutos de inactividad?`)) return;

    try {
      const response = await fetch(`${API_URL}/parametros/sesion`, {
        method: "PUT",
        credentials: window.API_CONFIG.credentials,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limite_minutos: minutos, aviso_segundos: aviso })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        mostrarMensaje(data.error || "No fue posible guardar la configuración.", "error");
        return;
      }
      mostrarMensaje("Configuración guardada. Se aplica desde la próxima solicitud de cada usuario.", "success");
    } catch (error) {
      console.error(error);
      mostrarMensaje("No fue posible conectar con el servidor.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("formSesion").addEventListener("submit", guardar);
    cargar();
  });
})();
