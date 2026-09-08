const API_URL = window.API_CONFIG.API_URL;

const verificando = document.getElementById("verificando");
const restablecerForm = document.getElementById("restablecerForm");
const botonGuardar = document.getElementById("botonGuardar");
const mensaje = document.getElementById("mensaje");

const token = new URLSearchParams(window.location.search).get("token") || "";

function mostrarError(texto) {
  verificando.hidden = true;
  restablecerForm.hidden = true;
  mensaje.textContent = texto;
  mensaje.className = "mensaje error";
}

// Se comprueba el enlace antes de pedir la contraseña, para no hacer escribirla
// dos veces cuando ya caducó.
document.addEventListener("DOMContentLoaded", async () => {
  if (!token) {
    mostrarError("El enlace está incompleto. Solicita uno nuevo desde la pantalla de recuperación.");
    return;
  }

  try {
    const response = await fetch(`${API_URL}/auth/recuperar/verificar`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token })
    });

    const data = await response.json();

    if (!response.ok || !data.valido) {
      mostrarError("El enlace no es válido o ya caducó. Solicita uno nuevo.");
      return;
    }

    verificando.hidden = true;
    restablecerForm.hidden = false;

  } catch (error) {
    console.error(error);
    mostrarError("No se pudo conectar con el servidor");
  }
});

restablecerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const password = document.getElementById("password").value;
  const confirmacion = document.getElementById("confirmacion").value;

  mensaje.textContent = "";
  mensaje.className = "mensaje";

  if (password !== confirmacion) {
    mensaje.textContent = "Las dos contraseñas no coinciden";
    mensaje.className = "mensaje error";
    return;
  }

  botonGuardar.disabled = true;

  try {
    const response = await fetch(`${API_URL}/auth/restablecer`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token, password })
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "No se pudo actualizar la contraseña";
      mensaje.className = "mensaje error";
      botonGuardar.disabled = false;
      return;
    }

    restablecerForm.hidden = true;
    mensaje.textContent = data.message;
    mensaje.className = "mensaje success";

    setTimeout(() => {
      window.location.href = "./login.html";
    }, 1800);

  } catch (error) {
    console.error(error);
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
    botonGuardar.disabled = false;
  }
});
