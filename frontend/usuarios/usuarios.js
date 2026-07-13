const API_URL = window.API_CONFIG.API_URL;

const formUsuario = document.getElementById("formUsuario");
const mensaje = document.getElementById("mensaje");
const selectorRol = document.getElementById("id_rol");
const selectorArea = document.getElementById("id_area");
const botonRegistrar = formUsuario.querySelector("button[type='submit']");

const AREA_POR_ROL = {
  1: 3,
  2: 1,
  3: 2
};

function sincronizarAreaConRol() {
  const idRol = Number(selectorRol.value);
  const idArea = AREA_POR_ROL[idRol];

  if (!idArea) {
    selectorArea.value = "";
    selectorArea.disabled = false;
    return;
  }

  selectorArea.value = String(idArea);
  selectorArea.disabled = true;
}

selectorRol.addEventListener("change", sincronizarAreaConRol);

formUsuario.addEventListener("submit", async (event) => {
  event.preventDefault();
  sincronizarAreaConRol();

  const usuario = {
    id_rol: Number(document.getElementById("id_rol").value),
    id_area: Number(document.getElementById("id_area").value),
    nombres: document.getElementById("nombres").value.trim(),
    email: document.getElementById("email").value.trim(),
    password: document.getElementById("password").value
  };

  const confirmar = confirm("¿Desea registrar este nuevo usuario?");

  if (!confirmar) {
    return;
  }

  try {
    botonRegistrar.disabled = true;
    botonRegistrar.textContent = "Registrando...";

    const response = await fetch(`${API_URL}/usuarios`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(usuario)
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "Error al registrar usuario";
      mensaje.className = "mensaje error";
      return;
    }

    mensaje.textContent = data.message;
    mensaje.className = "mensaje success";
    formUsuario.reset();
    sincronizarAreaConRol();

  } catch (error) {
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
  } finally {
    botonRegistrar.disabled = false;
    botonRegistrar.textContent = "Registrar Usuario";
  }
});
