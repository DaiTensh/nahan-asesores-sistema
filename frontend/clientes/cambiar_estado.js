const API_URL = window.API_CONFIG.API_URL;

document.addEventListener("DOMContentLoaded", () => {
  const txtRazonSocial = document.getElementById("txtRazonSocial");
  const txtRut = document.getElementById("txtRut");
  const badgeEstado = document.getElementById("badgeEstado");
  const btnCambiarEstado = document.getElementById("btnCambiarEstado");
  const mensaje = document.getElementById("mensajeFeedback");
  const parametrosUrl = new URLSearchParams(window.location.search);
  const idCliente = parametrosUrl.get("id");
  let estadoActual = "";

  cargarEstadoCliente();

  btnCambiarEstado.addEventListener("click", cambiarEstado);

  async function cargarEstadoCliente() {
    if (!idCliente) {
      bloquearAccion("Sin cliente");
      mostrarMensaje("No se recibió un cliente válido desde el listado.", "error");
      return;
    }

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}`, {
        credentials: window.API_CONFIG.credentials
      });
      const cliente = await response.json();

      if (!response.ok) {
        bloquearAccion("No disponible");
        mostrarMensaje(cliente.error || "No se pudo cargar el cliente.", "error");
        return;
      }

      txtRazonSocial.textContent = cliente.razon_social;
      txtRut.textContent = cliente.rut;
      estadoActual = cliente.estado || "ACTIVO";

      badgeEstado.textContent = estadoActual;
      badgeEstado.className = `badge estado-${estadoActual.toLowerCase()}`;
      btnCambiarEstado.textContent = estadoActual === "ACTIVO" ? "Desactivar cliente" : "Reactivar cliente";
      btnCambiarEstado.disabled = false;
    } catch (error) {
      console.error(error);
      bloquearAccion("No disponible");
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  async function cambiarEstado() {
    const nuevoEstado = estadoActual === "ACTIVO" ? "INACTIVO" : "ACTIVO";
    const confirmar = confirm(`Desea cambiar el estado del cliente a ${nuevoEstado}?`);

    if (!confirmar) return;

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/cambiar-estado`, {
        method: "POST",
        credentials: window.API_CONFIG.credentials,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          nuevo_estado: nuevoEstado
        })
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "No se pudo actualizar el estado.", "error");
        return;
      }

      mostrarMensaje(data.message || "Estado actualizado correctamente.", "success");
      cargarEstadoCliente();
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  function bloquearAccion(texto) {
    btnCambiarEstado.disabled = true;
    btnCambiarEstado.textContent = texto;
  }

  function mostrarMensaje(texto, tipo) {
    mensaje.textContent = texto;
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }
});
