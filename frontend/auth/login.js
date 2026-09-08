const API_URL = window.API_CONFIG.API_URL;

const loginForm = document.getElementById("loginForm");
const mensaje = document.getElementById("mensaje");
const botonLogin = loginForm.querySelector('button[type="submit"]');

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (botonLogin.disabled) {
    return;
  }

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  mensaje.textContent = "";
  mensaje.className = "mensaje";
  botonLogin.disabled = true;
  const textoOriginal = botonLogin.textContent;
  botonLogin.textContent = "Iniciando sesión...";

  try {
    const response = await fetch(`${API_URL}/login`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "Error al iniciar sesión";
      mensaje.className = "mensaje error";
      botonLogin.disabled = false;
      botonLogin.textContent = textoOriginal;
      return;
    }

    mensaje.textContent = "Inicio de sesión correcto";
    mensaje.className = "mensaje success";

    setTimeout(() => {
      window.location.href = "../dashboard/dashboard.html";
    }, 800);

  } catch (error) {
    console.error(error);
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
    botonLogin.disabled = false;
    botonLogin.textContent = textoOriginal;
  }
});
