const API_URL = window.API_CONFIG.API_URL;

const datosUsuario = document.getElementById("datosUsuario");
const mensaje = document.getElementById("mensaje");

let usuarioActual = null;

document.addEventListener("DOMContentLoaded", () => {
  UsuariosAutocomplete.configurarSelectorUsuario({
    inputId: "usuario_busqueda",
    hiddenId: "id_usuario",
    datalistId: "usuarios_datalist",
    onSelect: (usuario) => cargarUsuarioPorId(usuario.id_usuario)
  });
});

function mostrarMensaje(texto, tipo) {
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

async function buscarUsuario() {
  const usuario = await UsuariosAutocomplete.obtenerUsuarioSeleccionado("usuario_busqueda");

  mensaje.textContent = "";
  mensaje.className = "mensaje";

  if (!usuario) {
    datosUsuario.classList.add("hidden");
    mostrarMensaje("Seleccione un usuario de la lista", "error");
    return;
  }

  await cargarUsuarioPorId(usuario.id_usuario);
}

async function cargarUsuarioPorId(idUsuario) {
  try {
    const response = await fetch(`${API_URL}/usuarios/${idUsuario}`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await response.json();

    if (!response.ok) {
      usuarioActual = null;
      datosUsuario.classList.add("hidden");
      mostrarMensaje(data.error || "Usuario no encontrado", "error");
      return;
    }

    usuarioActual = data;
    UsuariosAutocomplete.mostrarUsuarioEnInput("usuario_busqueda", "id_usuario", data);

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
      {
        method: "PUT",
        credentials: window.API_CONFIG.credentials
      }
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
  const confirmar = confirm("¿Está seguro de intentar eliminar este usuario?");

  if (!confirmar) {
    return;
  }

  alert("Por trazabilidad, el sistema no elimina usuarios físicamente. Se recomienda deshabilitarlos.");
}
