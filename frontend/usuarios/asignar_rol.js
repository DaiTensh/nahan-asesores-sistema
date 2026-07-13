const API_URL = window.API_CONFIG.API_URL;

const datosUsuario = document.getElementById("datosUsuario");
const mensaje = document.getElementById("mensaje");

let usuarioActual = null;

const AREA_LABEL_POR_ROL = {
  1: "Ambas áreas",
  2: "Área jurídica",
  3: "Área contable"
};

const AREA_LABEL_POR_NOMBRE = {
  ADMINISTRACION: "Ambas áreas",
  JURIDICA: "Área jurídica",
  CONTABLE: "Área contable"
};

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

  mostrarMensaje("", "");

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
    document.getElementById("rol_actual").textContent = data.nombre_rol;
    document.getElementById("area").textContent = AREA_LABEL_POR_NOMBRE[data.nombre_area] || data.nombre_area;
    document.getElementById("id_rol").value = data.id_rol;

    datosUsuario.classList.remove("hidden");
    mostrarMensaje("", "");

  } catch (error) {
    console.error(error);
    usuarioActual = null;
    datosUsuario.classList.add("hidden");
    mostrarMensaje("Error al conectar con el servidor", "error");
  }
}

async function asignarRol() {
  const botonAsignar = document.getElementById("btnAsignarRol");

  if (!usuarioActual) {
    mostrarMensaje("Debe buscar un usuario primero", "error");
    return;
  }

  const nuevoRol = document.getElementById("id_rol").value;

  if (!nuevoRol) {
    mostrarMensaje("Debe seleccionar un rol", "error");
    return;
  }

  const confirmar = confirm("¿Está seguro de asignar este rol al usuario?");

  if (!confirmar) return;

  try {
    botonAsignar.disabled = true;
    botonAsignar.textContent = "Asignando...";

    const response = await fetch(
      `${API_URL}/usuarios/${usuarioActual.id_usuario}/rol`,
      {
        method: "PUT",
        credentials: window.API_CONFIG.credentials,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          id_rol: Number(nuevoRol)
        })
      }
    );

    const data = await response.json();

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo asignar el rol", "error");
      return;
    }

    const textoRol = document.getElementById("id_rol")
      .options[document.getElementById("id_rol").selectedIndex]
      .text;

    document.getElementById("rol_actual").textContent = textoRol;
    document.getElementById("area").textContent = AREA_LABEL_POR_ROL[Number(nuevoRol)];

    mostrarMensaje(data.message, "success");

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor", "error");
  } finally {
    botonAsignar.disabled = false;
    botonAsignar.textContent = "Asignar Rol";
  }
}
