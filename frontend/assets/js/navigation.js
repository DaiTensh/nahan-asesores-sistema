const SIDEBAR_STORAGE_KEY = "nahan_sidebar_collapsed";

const NAV_ITEMS = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: "DA",
    href: "../dashboard/dashboard.html"
  },
  {
    id: "clientes",
    label: "Clientes",
    icon: "CL",
    href: "../clientes/listar_clientes.html"
  },
  {
    id: "tareas",
    label: "Tareas",
    icon: "TA",
    href: "../tareas/tareas.html"
  },
  {
    id: "control-horas",
    label: "Control de Horas",
    icon: "CH",
    href: "../control_horas/control_horas.html"
  }
];

const ADMIN_ITEMS = [
  {
    id: "reportes",
    label: "Reportes",
    icon: "RE",
    href: "../reportes/reportes.html"
  },
  {
    id: "registrar",
    label: "Registrar usuario",
    icon: "RU",
    href: "../usuarios/usuarios.html"
  },
  {
    id: "modificar",
    label: "Modificar usuario",
    icon: "MU",
    href: "../usuarios/modificar_usuario.html"
  },
  {
    id: "desactivar",
    label: "Deshabilitar usuario",
    icon: "DU",
    href: "../usuarios/desactivar_usuario.html"
  },
  {
    id: "rol",
    label: "Asignar rol",
    icon: "AR",
    href: "../usuarios/asignar_rol.html"
  }
];

function nombreRolNatural(nombreRol) {
  const roles = {
    ADMINISTRADOR: "Administrador",
    USUARIO_AREA_JURIDICA: "Área jurídica",
    USUARIO_AREA_CONTABLE: "Área contable"
  };

  return roles[nombreRol] || nombreRol;
}

function obtenerIniciales(nombre = "") {
  return nombre
    .trim()
    .split(/\s+/)
    .map(parte => parte[0])
    .join("")
    .substring(0, 2)
    .toUpperCase() || "NA";
}

function crearLinkNavegacion(item, rutaActiva, extraClass = "") {
  const link = document.createElement("a");
  link.href = item.href;
  link.className = `sidebar-link ${extraClass} ${rutaActiva === item.id ? "active" : ""}`.trim();
  link.title = item.label;
  link.setAttribute("aria-label", item.label);

  const icono = document.createElement("span");
  icono.className = "sidebar-icon";
  icono.setAttribute("aria-hidden", "true");
  icono.textContent = item.icon;

  const texto = document.createElement("span");
  texto.className = "sidebar-text";
  texto.textContent = item.label;

  link.appendChild(icono);
  link.appendChild(texto);

  return link;
}

function aplicarEstadoSidebar(colapsada) {
  document.body.classList.toggle("sidebar-collapsed", colapsada);
}

async function cargarNavegacion(rutaActiva = "") {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const nav = document.getElementById("sidebar");

  if (!nav) return;

  const esAdmin = usuario.nombre_rol === "ADMINISTRADOR";
  const sidebarColapsada = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  aplicarEstadoSidebar(sidebarColapsada);

  nav.textContent = "";
  nav.setAttribute("aria-label", "Navegación principal");

  const header = document.createElement("div");
  header.className = "sidebar-header";

  const marca = document.createElement("a");
  marca.href = "../dashboard/dashboard.html";
  marca.className = "sidebar-brand";
  marca.title = "Nahan Asesores";
  marca.setAttribute("aria-label", "Ir al dashboard");

  const marcaLogo = document.createElement("span");
  marcaLogo.className = "sidebar-brand-mark";
  marcaLogo.setAttribute("aria-hidden", "true");
  marcaLogo.textContent = "NA";

  const marcaTexto = document.createElement("span");
  marcaTexto.className = "sidebar-brand-text";
  marcaTexto.textContent = "Nahan Asesores";

  marca.appendChild(marcaLogo);
  marca.appendChild(marcaTexto);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "sidebar-toggle btn-icon";
  toggle.title = sidebarColapsada ? "Expandir menú" : "Contraer menú";
  toggle.setAttribute("aria-label", sidebarColapsada ? "Expandir menú" : "Contraer menú");
  toggle.setAttribute("aria-expanded", String(!sidebarColapsada));
  toggle.textContent = sidebarColapsada ? ">" : "<";
  toggle.addEventListener("click", () => {
    const nuevoEstado = !document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(nuevoEstado));
    aplicarEstadoSidebar(nuevoEstado);
    toggle.textContent = nuevoEstado ? ">" : "<";
    toggle.title = nuevoEstado ? "Expandir menú" : "Contraer menú";
    toggle.setAttribute("aria-label", toggle.title);
    toggle.setAttribute("aria-expanded", String(!nuevoEstado));
  });

  header.appendChild(marca);
  header.appendChild(toggle);
  nav.appendChild(header);

  const lista = document.createElement("div");
  lista.className = "sidebar-nav";
  NAV_ITEMS.forEach(item => lista.appendChild(crearLinkNavegacion(item, rutaActiva)));
  nav.appendChild(lista);

  if (esAdmin) {
    const detalles = document.createElement("details");
    detalles.className = "sidebar-admin-group";

    if (ADMIN_ITEMS.some(item => item.id === rutaActiva)) {
      detalles.open = true;
    }

    const resumen = document.createElement("summary");
    resumen.className = `sidebar-link sidebar-admin-summary ${
      ADMIN_ITEMS.some(item => item.id === rutaActiva) ? "active" : ""
    }`;
    resumen.title = "Administración";
    resumen.setAttribute("aria-label", "Administración");

    const icono = document.createElement("span");
    icono.className = "sidebar-icon";
    icono.setAttribute("aria-hidden", "true");
    icono.textContent = "AD";

    const texto = document.createElement("span");
    texto.className = "sidebar-text";
    texto.textContent = "Administración";

    resumen.appendChild(icono);
    resumen.appendChild(texto);
    detalles.appendChild(resumen);

    const submenu = document.createElement("div");
    submenu.className = "sidebar-submenu";
    ADMIN_ITEMS.forEach(item => submenu.appendChild(
      crearLinkNavegacion(item, rutaActiva, "sidebar-sublink")
    ));
    detalles.appendChild(submenu);
    nav.appendChild(detalles);
  }

  const footer = document.createElement("div");
  footer.className = "sidebar-user";

  const menuSesion = document.createElement("details");
  menuSesion.className = "sidebar-user-menu";

  const resumenSesion = document.createElement("summary");
  resumenSesion.className = "sidebar-user-summary";
  resumenSesion.title = `${usuario.nombres} - ${nombreRolNatural(usuario.nombre_rol)}`;

  const avatar = document.createElement("span");
  avatar.className = "sidebar-user-avatar";
  avatar.textContent = obtenerIniciales(usuario.nombres);

  const info = document.createElement("span");
  info.className = "sidebar-user-info";

  const nombre = document.createElement("span");
  nombre.className = "sidebar-user-name";
  nombre.textContent = usuario.nombres;

  const rol = document.createElement("span");
  rol.className = "sidebar-user-role";
  rol.textContent = nombreRolNatural(usuario.nombre_rol);

  info.appendChild(nombre);
  info.appendChild(rol);
  resumenSesion.appendChild(avatar);
  resumenSesion.appendChild(info);
  menuSesion.appendChild(resumenSesion);

  const panel = document.createElement("div");
  panel.className = "sidebar-session-panel";

  const estado = document.createElement("p");
  estado.textContent = "Sesión activa";

  const cerrar = document.createElement("button");
  cerrar.type = "button";
  cerrar.className = "btn btn-danger btn-sm";
  cerrar.textContent = "Cerrar sesión";
  cerrar.addEventListener("click", cerrarSesion);

  panel.appendChild(estado);
  panel.appendChild(cerrar);
  menuSesion.appendChild(panel);
  footer.appendChild(menuSesion);
  nav.appendChild(footer);
}
