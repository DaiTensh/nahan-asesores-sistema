function obtenerUsuarioActual() {
  return JSON.parse(localStorage.getItem("usuario"));
}

function protegerPagina(rolesPermitidos) {
  const usuario = obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  if (!rolesPermitidos.includes(usuario.nombre_rol)) {
    alert("No tiene permisos para acceder a este módulo.");
    window.location.href = "../dashboard/dashboard.html";
  }
}