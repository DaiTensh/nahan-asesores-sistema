// Cambio de contraseña personal. Es obligatorio cuando la cuenta tiene una contraseña temporal (lo decide el
// SERVIDOR: /auth/me devuelve `debe_cambiar_password` y el resto de la API responde 403 mientras esté
// pendiente); también puede usarse de forma voluntaria. No usa almacenamiento del navegador.
const API_URL = window.API_CONFIG.API_URL;

const cambiarForm = document.getElementById("cambiarForm");
const botonGuardar = document.getElementById("botonGuardar");
const mensaje = document.getElementById("mensaje");
const avisoObligatorio = document.getElementById("avisoObligatorio");
const etiquetaActual = document.getElementById("etiquetaActual");
const enlaceSalir = document.getElementById("enlaceSalir");
const enlaceVolver = document.getElementById("enlaceVolver");
const separadorVolver = document.getElementById("separadorVolver");

function mostrar(texto, tipo) {
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const response = await fetch(`${API_URL}/auth/me`, { credentials: window.API_CONFIG.credentials });
    if (response.status === 401) {
      window.location.href = "./login.html";
      return;
    }
    const data = await response.json();
    if (data.debe_cambiar_password) {
      avisoObligatorio.hidden = false;
      etiquetaActual.textContent = "Contraseña temporal";
      document.getElementById("subtitulo").textContent = "Establecer su contraseña personal";
    } else {
      // Cambio voluntario: se puede volver al sistema.
      enlaceVolver.hidden = false;
      separadorVolver.hidden = false;
    }
  } catch (error) {
    console.error(error);
    mostrar("No se pudo comprobar la sesión con el servidor.", "error");
  }
});

cambiarForm.addEventListener("submit", async evento => {
  evento.preventDefault();
  if (botonGuardar.disabled) return;

  const password_actual = document.getElementById("passwordActual").value;
  const password_nueva = document.getElementById("passwordNueva").value;
  const confirmacion = document.getElementById("confirmacion").value;

  if (!password_actual || !password_nueva || !confirmacion) {
    mostrar("Complete los tres campos.", "error");
    return;
  }
  if (password_nueva.length < 8) {
    mostrar("La contraseña nueva debe tener al menos 8 caracteres.", "error");
    return;
  }
  if (password_nueva !== confirmacion) {
    mostrar("La confirmación no coincide con la contraseña nueva.", "error");
    return;
  }
  if (password_nueva === password_actual) {
    mostrar("La contraseña nueva no puede ser igual a la actual.", "error");
    return;
  }

  botonGuardar.disabled = true;
  mostrar("");
  try {
    const response = await fetch(`${API_URL}/auth/cambiar-password`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password_actual, password_nueva, confirmacion })
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 401) {
        window.location.href = "./login.html";
        return;
      }
      mostrar(data.error || "No se pudo cambiar la contraseña.", "error");
      botonGuardar.disabled = false;
      return;
    }

    cambiarForm.reset();
    mostrar("Contraseña actualizada. Entrando al sistema...", "success");
    setTimeout(() => { window.location.href = "../dashboard/dashboard.html"; }, 900);
  } catch (error) {
    console.error(error);
    mostrar("No se pudo conectar con el servidor.", "error");
    botonGuardar.disabled = false;
  }
});

enlaceSalir.addEventListener("click", async evento => {
  evento.preventDefault();
  try {
    await fetch(`${API_URL}/logout`, { method: "POST", credentials: window.API_CONFIG.credentials });
  } catch (error) {
    console.error(error);
  }
  window.location.href = "./login.html";
});
