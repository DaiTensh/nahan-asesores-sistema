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

// RF57 — la API agrupa los resultados en plural (clientes, tareas, usuarios)
// y cada resultado trae su tipo en singular. La URL se arma con el tipo del
// resultado; el nombre del grupo solo sirve de respaldo.
const GRUPOS_BUSQUEDA_GLOBAL = {
  clientes: { tipo: "cliente", etiqueta: "Clientes" },
  tareas: { tipo: "tarea", etiqueta: "Tareas" },
  usuarios: { tipo: "usuario", etiqueta: "Usuarios" }
};

const PAGINA_POR_TIPO_BUSQUEDA = {
  cliente: "../clientes/ficha_cliente.html",
  tarea: "../tareas/detalle_tarea.html",
  usuario: "../usuarios/modificar_usuario.html"
};

// Devuelve la URL del registro, o null si no hay una página a la que ir.
// El perfil de usuario es una pantalla de administrador: a los demás roles
// no se les ofrece un enlace que terminaría en «sin permisos».
function generarUrlResultado(resultado, esAdministrador = false) {
  if (!resultado) return null;

  const pagina = PAGINA_POR_TIPO_BUSQUEDA[resultado.tipo];
  const id = String(resultado.id ?? "");
  if (!pagina || !/^\d+$/.test(id)) return null;
  if (resultado.tipo === "usuario" && !esAdministrador) return null;

  return `${pagina}?id=${encodeURIComponent(id)}`;
}

function renderizarBuscadorGlobal(usuario) {
  const esAdministrador = Boolean(usuario) && usuario.nombre_rol === "ADMINISTRADOR";
  const busqueda = document.getElementById("globalSearchInput");
  const resultados = document.getElementById("globalSearchResults");
  if (!busqueda || !resultados) return;

  let temporizador = null;

  const mostrarMensaje = (mensaje) => {
    const elemento = document.createElement("div");
    elemento.className = "topbar-search-empty";
    elemento.textContent = mensaje;
    resultados.replaceChildren(elemento);
    resultados.hidden = false;
  };

  const ejecutarBusqueda = async (valor) => {
    const texto = valor.trim();
    if (!texto || texto.length < 2) {
      resultados.hidden = true;
      return;
    }

    try {
      const response = await fetch(`${window.API_CONFIG.API_URL}/busqueda-global?q=${encodeURIComponent(texto)}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "Sin resultados");
        return;
      }

      const grupos = data.resultados || {};
      const bloques = [];

      Object.entries(GRUPOS_BUSQUEDA_GLOBAL).forEach(([nombreGrupo, definicion]) => {
        const items = grupos[nombreGrupo] || [];
        if (!items.length) return;

        const grupo = document.createElement("div");
        grupo.className = "topbar-search-group";

        const etiqueta = document.createElement("div");
        etiqueta.className = "topbar-search-label";
        etiqueta.textContent = definicion.etiqueta;
        grupo.appendChild(etiqueta);

        items.forEach(item => {
          const url = generarUrlResultado(
            { tipo: item.tipo || definicion.tipo, id: item.id },
            esAdministrador
          );
          const enlace = document.createElement(url ? "a" : "div");
          enlace.className = "topbar-search-item";
          if (url) enlace.href = url;

          const nombre = document.createElement("span");
          nombre.className = "topbar-search-title";
          nombre.textContent = item.nombre || "Sin nombre";

          const detalle = document.createElement("span");
          detalle.className = "topbar-search-meta";
          detalle.textContent = item.detalle || definicion.etiqueta;

          enlace.append(nombre, detalle);
          grupo.appendChild(enlace);
        });

        bloques.push(grupo);
      });

      if (!bloques.length) {
        mostrarMensaje("Sin resultados para la búsqueda.");
      } else {
        resultados.replaceChildren(...bloques);
        resultados.hidden = false;
      }
    } catch {
      mostrarMensaje("No fue posible ejecutar la búsqueda.");
    }
  };

  busqueda.addEventListener("input", event => {
    const valor = event.target.value;
    clearTimeout(temporizador);
    temporizador = setTimeout(() => ejecutarBusqueda(valor), 250);
  });

  busqueda.addEventListener("focus", () => {
    if (busqueda.value.trim().length >= 2) {
      ejecutarBusqueda(busqueda.value);
    }
  });

  document.addEventListener("click", event => {
    if (!event.target.closest("#globalSearchInput") && !event.target.closest("#globalSearchResults")) {
      resultados.hidden = true;
    }
  });
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

  const buscador = document.createElement("div");
  buscador.className = "topbar-search";

  const inputBusqueda = document.createElement("input");
  inputBusqueda.id = "globalSearchInput";
  inputBusqueda.type = "search";
  inputBusqueda.placeholder = "Buscar clientes, tareas, usuarios";
  inputBusqueda.setAttribute("aria-label", "Buscar globalmente");

  const resultadosBusqueda = document.createElement("div");
  resultadosBusqueda.id = "globalSearchResults";
  resultadosBusqueda.className = "topbar-search-panel";
  resultadosBusqueda.hidden = true;

  buscador.appendChild(inputBusqueda);
  buscador.appendChild(resultadosBusqueda);

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
  acciones.appendChild(buscador);
  acciones.appendChild(menuSesion);

  topbar.appendChild(contexto);
  topbar.appendChild(acciones);

  renderizarBuscadorGlobal(usuario);
  montarModuloTopbar("inactividad"); // RF59
  montarModuloTopbar("notificaciones"); // RF51, RF52, RF53
}
