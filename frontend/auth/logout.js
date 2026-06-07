function cerrarSesion() {
  const confirmar = confirm("¿Desea cerrar sesión?");

  if (!confirmar) {
    return;
  }

  localStorage.removeItem("usuario");
  window.location.href = "../auth/login.html";
}