let usuarioActualPromesa = null;

// Sin respuesta del servidor (red caída o error 5xx) no se sabe si la sesión sigue vigente. Cada pantalla
// manda al login cuando no hay usuario; esta nota le permite explicar la causa en vez de aparentar que
// la sesión se cerró (el login la lee y la borra).
function anotarFalloDeServidor() {
  try {
    sessionStorage.setItem("nahan_sesion_motivo", "servidor");
  } catch (error) {
    // Sin almacenamiento de sesión el login simplemente no muestra la causa.
  }
}

async function obtenerUsuarioActual() {
  if (!usuarioActualPromesa) {
    usuarioActualPromesa = fetch(`${window.API_CONFIG.API_URL}/auth/me`, {
      credentials: window.API_CONFIG.credentials
    })
      .then(async response => {
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
          if (response.status >= 500) anotarFalloDeServidor();
          return null;
        }

        // El estado del cambio obligatorio lo decide el servidor. Mientras esté pendiente, ninguna pantalla
        // (salvo la propia de cambio) sirve: se redirige aquí, en un único lugar y sin bucles.
        const pendiente = Boolean(data.debe_cambiar_password);
        if (pendiente && !window.location.pathname.endsWith("/auth/cambiar_password.html")) {
          // Se devuelve el usuario (no null) para que la pantalla no mande además al login y las dos
          // redirecciones compitan.
          window.location.href = "../auth/cambiar_password.html";
        }
        return data.usuario ? { ...data.usuario, debe_cambiar_password: pendiente } : data.usuario;
      })
      .catch(error => {
        console.error(error);
        anotarFalloDeServidor();
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
    const aviso = "No tiene permisos para acceder a este módulo.";
    if (window.avisarAccion) {
      await avisarAccion(aviso, "advertencia");
    } else {
      alert(aviso);
    }
    window.location.href = "../dashboard/dashboard.html";
  }
}
