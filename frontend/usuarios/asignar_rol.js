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

  mostrarMensaje("", "");

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
    document.getElementById("rol_actual").textContent = data.nombre_rol;
    document.getElementById("area").textContent = data.nombre_area;
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
    const response = await fetch(
      `${API_URL}/usuarios/${usuarioActual.id_usuario}/rol`,
      {
        method: "PUT",
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

    mostrarMensaje(data.message, "success");

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor", "error");
  }
}