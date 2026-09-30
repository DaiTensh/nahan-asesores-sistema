// RF51, RF52, RF53 — Bandeja de notificaciones internas. RF46 agrega la
// importancia: las críticas se destacan con una etiqueta de texto y un borde.
//
// Se monta desde topbar.js en todas las pantallas autenticadas. Muestra en la
// barra superior el número de notificaciones no leídas y, al abrirla, las más
// recientes del usuario en sesión con su enlace a la tarea; permite marcarlas
// como leídas una a una o todas juntas. La consulta periódica del contador
// usa la cabecera `X-Actividad: pasiva` (RF59): no renueva la sesión.
(function () {
  if (window.__notificacionesMontadas) return;
  window.__notificacionesMontadas = true;

  const API_URL = window.API_CONFIG.API_URL;
  const CREDENCIALES = window.API_CONFIG.credentials;
  const INTERVALO_CONTADOR_MS = 60000;
  const LIMITE_LISTADO = 15;

  const ETIQUETAS_TIPO = {
    ASIGNACION_TAREA: "Nueva asignación",
    REASIGNACION_TAREA: "Tarea asignada",
    CAMBIO_ESTADO_TAREA: "Cambio de estado",
    REVISION_TAREA: "Revisión de tarea",
    VENCIMIENTO_PROXIMO: "Vencimiento próximo",
    SEGURIDAD: "Seguridad"
  };

  // RF46 — solo estos valores se convierten en clase CSS; cualquier otro se
  // trata como normal. La importancia nunca se inserta como HTML.
  const ETIQUETAS_IMPORTANCIA = {
    CRITICA: "⚠ Crítica",
    ALTA: "Alta"
  };

  let contenedor = null;
  let boton = null;
  let insignia = null;
  let panel = null;
  let lista = null;

  function cargarEstilos() {
    if (document.querySelector('link[data-modulo="notificaciones"]')) return;
    const enlace = document.createElement("link");
    enlace.rel = "stylesheet";
    enlace.href = "../assets/css/notificaciones.css";
    enlace.dataset.modulo = "notificaciones";
    document.head.appendChild(enlace);
  }

  // Los enlaces los genera el backend como "/frontend/<módulo>/<página>".
  // Solo se aceptan rutas internas con esa forma; cualquier otra cosa se
  // muestra sin enlace.
  function enlaceInterno(url) {
    if (typeof url !== "string") return null;
    const coincidencia = url.match(/^\/frontend\/([a-z_]+\/[a-z_]+\.html(?:\?[A-Za-z0-9_=&]*)?)$/);
    return coincidencia ? `../${coincidencia[1]}` : null;
  }

  // La fecha llega como hora local del servidor rotulada "GMT": se muestra
  // en UTC para no desplazarla (mismo criterio que detalle_tarea.js).
  function formatearFecha(valor) {
    const fecha = new Date(valor);
    return Number.isNaN(fecha.getTime()) ? String(valor ?? "") : fecha.toLocaleString("es-CL", { timeZone: "UTC" });
  }

  function actualizarInsignia(noLeidas) {
    const total = Number(noLeidas) || 0;
    insignia.textContent = total > 99 ? "99+" : String(total);
    insignia.hidden = total === 0;
    const descripcion = total === 0
      ? "Notificaciones: sin avisos pendientes"
      : `Notificaciones: ${total} sin leer`;
    boton.title = descripcion;
    boton.setAttribute("aria-label", descripcion);
  }

  async function solicitar(ruta, opciones = {}) {
    const response = await fetch(`${API_URL}${ruta}`, {
      credentials: CREDENCIALES,
      ...opciones,
      headers: { ...(opciones.headers || {}) }
    });
    const datos = await response.json().catch(() => ({}));
    return { response, datos };
  }

  async function consultarContador() {
    try {
      const { response, datos } = await solicitar("/notificaciones/contador", {
        headers: { "X-Actividad": "pasiva" }
      });
      if (response.ok) actualizarInsignia(datos.no_leidas);
    } catch (error) {
      console.error(error);
    }
  }

  function mensajeEnLista(texto) {
    lista.textContent = "";
    const item = document.createElement("li");
    item.className = "notificaciones-vacio";
    item.textContent = texto;
    lista.appendChild(item);
  }

  function crearItem(notificacion) {
    const item = document.createElement("li");
    item.className = notificacion.leida ? "notificacion-item" : "notificacion-item no-leida";

    const importancia = Object.prototype.hasOwnProperty.call(ETIQUETAS_IMPORTANCIA, notificacion.importancia)
      ? notificacion.importancia
      : "NORMAL";
    if (importancia === "CRITICA") item.classList.add("critica");

    const tipo = document.createElement("span");
    tipo.className = "notificacion-tipo";
    tipo.textContent = ETIQUETAS_TIPO[notificacion.tipo] || notificacion.tipo;

    if (importancia !== "NORMAL") {
      const etiqueta = document.createElement("span");
      etiqueta.className = `notificacion-importancia importancia-${importancia.toLowerCase()}`;
      etiqueta.textContent = ETIQUETAS_IMPORTANCIA[importancia];
      tipo.appendChild(etiqueta);
    }

    const destino = enlaceInterno(notificacion.url_destino);
    const mensaje = document.createElement(destino ? "a" : "p");
    mensaje.className = "notificacion-mensaje";
    mensaje.textContent = notificacion.mensaje;
    if (destino) {
      mensaje.href = destino;
      mensaje.addEventListener("click", async event => {
        if (notificacion.leida) return;
        event.preventDefault();
        await marcarLeida(notificacion.id_notificacion);
        window.location.href = destino;
      });
    }

    const pie = document.createElement("div");
    pie.className = "notificacion-pie";

    const fecha = document.createElement("span");
    fecha.textContent = formatearFecha(notificacion.fecha);
    pie.appendChild(fecha);

    if (!notificacion.leida) {
      const marcar = document.createElement("button");
      marcar.type = "button";
      marcar.className = "notificacion-marcar";
      marcar.textContent = "Marcar como leída";
      marcar.addEventListener("click", async () => {
        await marcarLeida(notificacion.id_notificacion);
        await cargarListado();
      });
      pie.appendChild(marcar);
    }

    item.append(tipo, mensaje, pie);
    return item;
  }

  async function cargarListado() {
    mensajeEnLista("Cargando notificaciones...");
    try {
      const { response, datos } = await solicitar(`/notificaciones?limite=${LIMITE_LISTADO}`);

      if (response.status === 401) {
        window.location.href = "../auth/login.html";
        return;
      }
      if (!response.ok) {
        mensajeEnLista(datos.error || "No se pudieron cargar las notificaciones.");
        return;
      }

      actualizarInsignia(datos.no_leidas);

      if (!datos.notificaciones.length) {
        mensajeEnLista("No tienes notificaciones.");
        return;
      }

      lista.textContent = "";
      datos.notificaciones.forEach(notificacion => lista.appendChild(crearItem(notificacion)));
    } catch (error) {
      console.error(error);
      mensajeEnLista("Error al conectar con el servidor.");
    }
  }

  async function marcarLeida(idNotificacion) {
    try {
      const { response, datos } = await solicitar(`/notificaciones/${idNotificacion}/leida`, { method: "PUT" });
      if (response.ok) actualizarInsignia(datos.no_leidas);
    } catch (error) {
      console.error(error);
    }
  }

  async function marcarTodas() {
    try {
      const { response } = await solicitar("/notificaciones/leer-todas", { method: "PUT" });
      if (response.ok) await cargarListado();
    } catch (error) {
      console.error(error);
    }
  }

  function alternarPanel() {
    const abrir = panel.hidden;
    panel.hidden = !abrir;
    boton.setAttribute("aria-expanded", String(abrir));
    if (abrir) cargarListado();
  }

  function montar() {
    const acciones = document.querySelector(".topbar-actions");
    if (!acciones) return false;

    contenedor = document.createElement("div");
    contenedor.className = "topbar-notificaciones";

    boton = document.createElement("button");
    boton.type = "button";
    boton.id = "topbarNotificaciones";
    boton.className = "topbar-icon-button notificaciones-boton";
    boton.setAttribute("aria-haspopup", "true");
    boton.setAttribute("aria-expanded", "false");
    boton.textContent = "\u{1F514}";
    boton.addEventListener("click", alternarPanel);

    insignia = document.createElement("span");
    insignia.className = "notificaciones-insignia";
    insignia.hidden = true;
    boton.appendChild(insignia);

    panel = document.createElement("div");
    panel.className = "notificaciones-panel";
    panel.hidden = true;
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-label", "Notificaciones");

    const encabezado = document.createElement("div");
    encabezado.className = "notificaciones-encabezado";
    const titulo = document.createElement("strong");
    titulo.textContent = "Notificaciones";
    const todas = document.createElement("button");
    todas.type = "button";
    todas.className = "notificacion-marcar";
    todas.textContent = "Marcar todas como leídas";
    todas.addEventListener("click", marcarTodas);
    encabezado.append(titulo, todas);

    lista = document.createElement("ul");
    lista.className = "notificaciones-lista";

    panel.append(encabezado, lista);
    contenedor.append(boton, panel);

    const menuUsuario = acciones.querySelector(".topbar-user");
    acciones.insertBefore(contenedor, menuUsuario || null);

    document.addEventListener("click", event => {
      if (!panel.hidden && !contenedor.contains(event.target)) {
        panel.hidden = true;
        boton.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !panel.hidden) {
        panel.hidden = true;
        boton.setAttribute("aria-expanded", "false");
        boton.focus();
      }
    });

    actualizarInsignia(0);
    return true;
  }

  cargarEstilos();
  if (montar()) {
    consultarContador();
    setInterval(consultarContador, INTERVALO_CONTADOR_MS);
  }
})();
