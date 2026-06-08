function cargarNavegacion(rutaActiva = "") {
  const usuario = JSON.parse(localStorage.getItem("usuario"));

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const nav = document.getElementById("sidebar");

  if (!nav) return;
  const esAdmin = usuario.nombre_rol === "ADMINISTRADOR";

nav.innerHTML = `
    <div class="sidebar-title">Nahan Asesores</div>

    <a class="sidebar-link ${rutaActiva === "dashboard" ? "active" : ""}"
       href="../dashboard/dashboard.html">
       Dashboard
    </a>

    ${
      esAdmin
        ? `
        <a class="sidebar-link ${rutaActiva === "registrar" ? "active" : ""}"
           href="../usuarios/usuarios.html">
           Registrar Usuario
        </a>

        <a class="sidebar-link ${rutaActiva === "modificar" ? "active" : ""}"
           href="../usuarios/modificar_usuario.html">
           Modificar Usuario
        </a>

        <a class="sidebar-link ${rutaActiva === "desactivar" ? "active" : ""}"
           href="../usuarios/desactivar_usuario.html">
           Deshabilitar Usuario
        </a>

        <a class="sidebar-link ${rutaActiva === "rol" ? "active" : ""}"
           href="../usuarios/asignar_rol.html">
           Asignar Rol
        </a>
        `
        : ""
    }

    <button class="sidebar-button" onclick="cerrarSesion()">
      Cerrar Sesión
    </button>

    <div class="sidebar-footer">
      © 2026 Nahan Asesores
    </div>
`;
}