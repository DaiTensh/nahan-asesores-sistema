const API_URL = "http://127.0.0.1:5000/api";

const formUsuario = document.getElementById("formUsuario");
const mensaje = document.getElementById("mensaje");

formUsuario.addEventListener("submit", async (event) => {
  event.preventDefault();

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
    const response = await fetch(`${API_URL}/usuarios`, {
      method: "POST",
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

  } catch (error) {
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
  }
});