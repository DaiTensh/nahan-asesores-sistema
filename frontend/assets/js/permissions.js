let usuarioActualPromesa = null;

async function obtenerUsuarioActual() {
  if (!usuarioActualPromesa) {
    usuarioActualPromesa = fetch(`${window.API_CONFIG.API_URL}/auth/me`, {
      credentials: window.API_CONFIG.credentials
    })
      .then(async response => {
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          return null;
        }

        return data.usuario;
      })
      .catch(error => {
        console.error(error);
        return null;
      });
  }

  return usuarioActualPromesa;
}

async function protegerPagina(rolesPermitidos) {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  if (!rolesPermitidos.includes(usuario.nombre_rol)) {
    alert("No tiene permisos para acceder a este módulo.");
    window.location.href = "../dashboard/dashboard.html";
  }
}
