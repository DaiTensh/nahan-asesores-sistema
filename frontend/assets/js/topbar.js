function formatearRolTopbar(nombreRol) {
  const roles = {
    ADMINISTRADOR: "Administrador",
    USUARIO_AREA_JURIDICA: "Área jurídica",
    USUARIO_AREA_CONTABLE: "Área contable"
  };

  return roles[nombreRol] || nombreRol;
}

function obtenerInicialesTopbar(nombre = "") {
  return nombre
    .trim()
    .split(/\s+/)
    .map(parte => parte[0])
    .join("")
    .substring(0, 2)
    .toUpperCase() || "NA";
}

function obtenerTituloPagina() {
  const titulo = document.querySelector("main h1");
  return titulo ? titulo.textContent.trim() : document.title;
}

function obtenerSubtituloPagina() {
  const encabezados = [
    ".dashboard-header p",
    ".clientes-header p",
    ".tareas-header p",
    ".control-header p",
    ".usuarios-card .subtitle",
    ".modificar-card .subtitle"
  ];

  for (const selector of encabezados) {
    const subtitulo = document.querySelector(selector);

    if (subtitulo && subtitulo.textContent.trim()) {
      return subtitulo.textContent.trim();
    }
  }

  return "";
}

function fechaActualEnEspanol() {
  return new Date().toLocaleDateString("es-CL", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric"
  });
}

// Carga un módulo complementario de la barra superior (assets/js/<nombre>.js)
// una sola vez. Cada funcionalidad que se monta en la barra vive en su propio
// archivo y aquí solo se agrega la línea que la carga.
function montarModuloTopbar(nombre) {
  if (document.querySelector(`script[data-modulo-topbar="${nombre}"]`)) return;
  const script = document.createElement("script");
  script.src = `../assets/js/${nombre}.js`;
  script.dataset.moduloTopbar = nombre;
  document.body.appendChild(script);
}

async function cargarTopbar() {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const topbar = document.getElementById("topbar");

  if (!topbar) return;

  topbar.textContent = "";

  const contexto = document.createElement("div");
  contexto.className = "topbar-context";

  const titulo = document.createElement("h1");
  titulo.textContent = obtenerTituloPagina();

  const subtituloTexto = obtenerSubtituloPagina();
  const subtitulo = document.createElement("p");
  subtitulo.textContent = subtituloTexto || "Sistema de gestión interna";

  contexto.appendChild(titulo);
  contexto.appendChild(subtitulo);

  const acciones = document.createElement("div");
  acciones.className = "topbar-actions";

  const fecha = document.createElement("span");
  fecha.className = "topbar-date";
  fecha.textContent = fechaActualEnEspanol();

  const menuSesion = document.createElement("details");
  menuSesion.className = "topbar-user";

  const resumen = document.createElement("summary");
  resumen.className = "topbar-user-summary";
  resumen.title = "Información de sesión";

  const avatar = document.createElement("span");
  avatar.className = "user-avatar";
  avatar.textContent = obtenerInicialesTopbar(usuario.nombres);

  const info = document.createElement("span");
  info.className = "user-info";

  const nombre = document.createElement("span");
  nombre.className = "user-name";
  nombre.textContent = usuario.nombres;

  const rol = document.createElement("span");
  rol.className = "user-role";
  rol.textContent = formatearRolTopbar(usuario.nombre_rol);

  info.appendChild(nombre);
  info.appendChild(rol);
  resumen.appendChild(avatar);
  resumen.appendChild(info);
  menuSesion.appendChild(resumen);

  const panel = document.createElement("div");
  panel.className = "topbar-user-panel";

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

  acciones.appendChild(fecha);
  acciones.appendChild(menuSesion);

  topbar.appendChild(contexto);
  topbar.appendChild(acciones);

  montarModuloTopbar("inactividad"); // RF59
  montarModuloTopbar("notificaciones"); // RF51, RF52, RF53
}
