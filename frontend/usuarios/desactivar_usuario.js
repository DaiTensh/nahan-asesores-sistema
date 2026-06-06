const API_URL = "http://127.0.0.1:5000/api";

const datosUsuario = document.getElementById("datosUsuario");
const mensaje = document.getElementById("mensaje");

let usuarioActual = null;

function mostrarMensaje(texto, tipo) {
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

async function buscarUsuario() {
  const idUsuario = document.getElementById("id_usuario").value;

  mensaje.textContent = "";
  mensaje.className = "mensaje";

  if (!idUsuario) {
    datosUsuario.classList.add("hidden");
    mostrarMensaje("Debe ingresar un ID de usuario", "error");
    return;
  }

  try {
    const response = await fetch(`${API_URL}/usuarios/${idUsuario}`);
    const data = await response.json();

    if (!response.ok) {
      usuarioActual = null;
      datosUsuario.classList.add("hidden");
      mostrarMensaje(data.error || "Usuario no encontrado", "error");
      return;
    }

    usuarioActual = data;

    document.getElementById("nombres").textContent = data.nombres;
    document.getElementById("email").textContent = data.email;
    document.getElementById("rol").textContent = data.nombre_rol;
    document.getElementById("area").textContent = data.nombre_area;
    document.getElementById("estado").textContent = data.estado;

    datosUsuario.classList.remove("hidden");
    mostrarMensaje("", "");

  } catch (error) {
    console.error(error);
    usuarioActual = null;
    datosUsuario.classList.add("hidden");
    mostrarMensaje("Error al conectar con el servidor", "error");
  }
}

async function desactivarUsuario() {
  if (!usuarioActual) {
    mostrarMensaje("Debe buscar un usuario primero", "error");
    return;
  }

  const confirmar = confirm("¿Está seguro de deshabilitar este usuario?");

  if (!confirmar) return;

  try {
    const response = await fetch(
      `${API_URL}/usuarios/${usuarioActual.id_usuario}/desactivar`,
      { method: "PUT" }
    );

    const data = await response.json();

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo deshabilitar el usuario", "error");
      return;
    }

    usuarioActual.estado = "INACTIVO";
    document.getElementById("estado").textContent = "INACTIVO";
    mostrarMensaje(data.message, "success");

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor", "error");
  }
}

function eliminarUsuario() {
  alert("Por trazabilidad, el sistema no elimina usuarios físicamente. Se recomienda deshabilitarlos.");
}