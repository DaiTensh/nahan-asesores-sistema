const API_URL = window.API_CONFIG.API_URL;

const recuperarForm = document.getElementById("recuperarForm");
const botonEnviar = document.getElementById("botonEnviar");
const mensaje = document.getElementById("mensaje");

recuperarForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const email = document.getElementById("email").value.trim();

  mensaje.textContent = "";
  mensaje.className = "mensaje";
  botonEnviar.disabled = true;

  try {
    const response = await fetch(`${API_URL}/auth/recuperar`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email })
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "No se pudo procesar la solicitud";
      mensaje.className = "mensaje error";
      botonEnviar.disabled = false;
      return;
    }

    // El mensaje es el mismo exista o no la cuenta: no revelamos si el correo
    // está registrado.
    mensaje.textContent = data.message;
    mensaje.className = "mensaje success";
    recuperarForm.reset();

  } catch (error) {
    console.error(error);
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
    botonEnviar.disabled = false;
  }
});
