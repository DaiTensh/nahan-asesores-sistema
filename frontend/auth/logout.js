async function cerrarSesion() {
  const confirmar = confirm("¿Desea cerrar sesión?");

  if (!confirmar) {
    return;
  }

  try {
    await fetch(`${window.API_CONFIG.API_URL}/logout`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials
    });
  } catch (error) {
    console.error(error);
  } finally {
    window.location.href = "../auth/login.html";
  }
}
