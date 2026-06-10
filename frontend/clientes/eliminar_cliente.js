const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  const btnConfirmarAccion = document.getElementById("btnConfirmarAccion");
  const txtRut = document.getElementById("resumenRut");
  const txtNombre = document.getElementById("resumenNombre");
  const textoVerificacion = document.getElementById("textoVerificacion");
  const mensaje = document.getElementById("mensajeFeedback");
  const parametrosUrl = new URLSearchParams(window.location.search);
  const idCliente = parametrosUrl.get("id");
  const usuario = JSON.parse(localStorage.getItem("usuario")) || {};

  let puedeEliminarDefinitivo = false;

  cargarVerificacion();

  btnConfirmarAccion.addEventListener("click", procesarCliente);

  async function cargarVerificacion() {
    if (!idCliente) {
      bloquearAccion("Sin cliente");
      mostrarMensaje("No se recibió un cliente válido desde el listado.", "error");
      return;
    }

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/verificar-vinculos`);
      const data = await response.json();

      if (!response.ok) {
        bloquearAccion("No disponible");
        mostrarMensaje(data.error || "No se pudo verificar el cliente.", "error");
        return;
      }

      txtRut.textContent = data.rut;
      txtNombre.textContent = data.razon_social;

      if (data.tiene_vinculos) {
        puedeEliminarDefinitivo = false;
        textoVerificacion.textContent = `Este cliente posee ${data.tareas_activas} tareas activas o documentos vigentes. Se aplicará deshabilitación lógica para conservar el historial.`;
        btnConfirmarAccion.textContent = "Deshabilitar cliente";
      } else {
        puedeEliminarDefinitivo = true;
        textoVerificacion.textContent = "Este cliente no posee vínculos activos. Puede eliminarse definitivamente del registro.";
        btnConfirmarAccion.textContent = "Eliminar definitivamente";
      }
    } catch (error) {
      console.error(error);
      bloquearAccion("No disponible");
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  async function procesarCliente() {
    const accion = puedeEliminarDefinitivo ? "eliminar definitivamente" : "deshabilitar";
    const confirmar = confirm(`Desea ${accion} este cliente?`);

    if (!confirmar) return;

    const endpoint = puedeEliminarDefinitivo
      ? `${API_URL}/clientes/${idCliente}/eliminar-definitivo`
      : `${API_URL}/clientes/${idCliente}/deshabilitar`;

    const method = puedeEliminarDefinitivo ? "DELETE" : "PATCH";

    try {
      const response = await fetch(endpoint, {
        method,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          id_usuario_auditoria: usuario.id_usuario || 1
        })
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "No se pudo procesar la acción.", "error");
        return;
      }

      mostrarMensaje(data.message || "Acción completada correctamente.", "success");
      bloquearAccion("Acción completada");

      setTimeout(() => {
        window.location.href = "listar_clientes.html";
      }, 1200);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  function bloquearAccion(texto) {
    btnConfirmarAccion.disabled = true;
    btnConfirmarAccion.textContent = texto;
  }

  function mostrarMensaje(texto, tipo) {
    mensaje.textContent = texto;
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }
});
