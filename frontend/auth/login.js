const API_URL = "http://127.0.0.1:5000/api";

const loginForm = document.getElementById("loginForm");
const mensaje = document.getElementById("mensaje");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  mensaje.textContent = "";
  mensaje.className = "mensaje";

  try {
    const response = await fetch(`${API_URL}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "Error al iniciar sesión";
      mensaje.className = "mensaje error";
      return;
    }

    localStorage.setItem("usuario", JSON.stringify(data.usuario));

    mensaje.textContent = "Inicio de sesión correcto";
    mensaje.className = "mensaje success";

    setTimeout(() => {
      window.location.href = "../dashboard/dashboard.html";
    }, 800);

  } catch (error) {
    console.error(error);
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
  }
});