const API_URL = window.API_CONFIG.API_URL;

const loginForm = document.getElementById("loginForm");
const mensaje = document.getElementById("mensaje");
const botonLogin = loginForm.querySelector('button[type="submit"]');

// RF59: aviso cuando se llega aquí por cierre automático de sesión. Si la sesión terminó por otra causa
// (H-16), el aviso no atribuye el cierre a la inactividad.
const MOTIVOS_DE_CIERRE = {
  inactividad: "Tu sesión se cerró por inactividad. Vuelve a iniciar sesión.",
  sesion: "Tu sesión ya no está activa. Vuelve a iniciar sesión.",
  servidor: "No se pudo comprobar tu sesión porque el servidor no responde. Inténtalo de nuevo en unos minutos."
};
let motivoDeCierre = new URLSearchParams(window.location.search).get("motivo");
// permissions.js anota «servidor» cuando /auth/me no respondió; se lee una sola vez.
try {
  if (!motivoDeCierre && sessionStorage.getItem("nahan_sesion_motivo") === "servidor") motivoDeCierre = "servidor";
  sessionStorage.removeItem("nahan_sesion_motivo");
} catch (error) {
  // Sin almacenamiento de sesión no hay causa que mostrar.
}
if (Object.prototype.hasOwnProperty.call(MOTIVOS_DE_CIERRE, motivoDeCierre)) {
  mensaje.textContent = MOTIVOS_DE_CIERRE[motivoDeCierre];
  mensaje.className = "mensaje error";
}

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

    // Contraseña temporal: el servidor exige establecer una personal antes de cualquier otra operación.
    const destino = data.usuario && data.usuario.debe_cambiar_password
      ? "./cambiar_password.html"
      : "../dashboard/dashboard.html";

    setTimeout(() => {
      window.location.href = destino;
    }, 800);

  } catch (error) {
    console.error(error);
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
    botonLogin.disabled = false;
    botonLogin.textContent = textoOriginal;
  }
});
