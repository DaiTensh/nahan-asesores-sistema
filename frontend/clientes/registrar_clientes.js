const API_URL = window.API_CONFIG.API_URL;

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("formRegistroCliente");
  const mensaje = document.getElementById("mensajeFeedback");
  const botonCrear = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (botonCrear.disabled) {
      return;
    }

    const areasSeleccionadas = obtenerAreasSeleccionadas();

    if (areasSeleccionadas.length === 0) {
      mostrarMensaje("Debe asignar el cliente a al menos un área.", "error");
      return;
    }

    const confirmar = confirm("Desea crear este cliente?");

    if (!confirmar) return;

    const payload = {
      rut: document.getElementById("rut").value.trim(),
      razon_social: document.getElementById("razon_social").value.trim(),
      direccion: document.getElementById("direccion").value.trim(),
      telefono: document.getElementById("telefono").value.trim(),
      email: document.getElementById("email").value.trim(),
      areas: areasSeleccionadas
    };

    botonCrear.disabled = true;
    const textoOriginal = botonCrear.textContent;
    botonCrear.textContent = "Creando...";

    try {
      const response = await fetch(`${API_URL}/clientes`, {
        method: "POST",
        credentials: window.API_CONFIG.credentials,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "No se pudo completar el registro.", "error");
        return;
      }

      mostrarMensaje(data.message || "Cliente registrado correctamente.", "success");
      form.reset();
    } catch (error) {
      console.error(error);
      mostrarMensaje("No se pudo contactar la API. Verifique que el servidor esté disponible.", "error");
    } finally {
      botonCrear.disabled = false;
      botonCrear.textContent = textoOriginal;
    }
  });

  function obtenerAreasSeleccionadas() {
    const areas = [];

    if (document.getElementById("checkLegal").checked) areas.push(1);
    if (document.getElementById("checkContable").checked) areas.push(2);

    return areas;
  }

  function mostrarMensaje(texto, tipo) {
    mensaje.textContent = texto;
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }
});
