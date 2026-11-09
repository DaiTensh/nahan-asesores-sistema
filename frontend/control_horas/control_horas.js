const API_URL = window.API_CONFIG.API_URL;

let usuarioActual = null;
let tareasDisponibles = [];
let clientesDisponibles = [];
let temporizadorActivo = null;
let intervaloTemporizador = null;

const clienteBusqueda = document.getElementById("clienteBusqueda");
const idClienteSeleccionado = document.getElementById("idClienteSeleccionado");
const clientesControlDatalist = document.getElementById("clientesControlDatalist");
const tareaBusqueda = document.getElementById("tareaBusqueda");
const idTareaSeleccionada = document.getElementById("idTareaSeleccionada");
const tareasControlDatalist = document.getElementById("tareasControlDatalist");
const ayudaTareas = document.getElementById("ayudaTareas");
const timerPanel = document.getElementById("timerPanel");
const estadoTemporizador = document.getElementById("estadoTemporizador");
const inicioTemporizador = document.getElementById("inicioTemporizador");
const clienteActivo = document.getElementById("clienteActivo");
const tareaActiva = document.getElementById("tareaActiva");
const descripcionActiva = document.getElementById("descripcionActiva");
const temporizador = document.getElementById("temporizador");
const btnIniciar = document.getElementById("btnIniciar");
const btnDetener = document.getElementById("btnDetener");
const mensajeControl = document.getElementById("mensajeControl");
const tablaRegistros = document.getElementById("tablaRegistros");
const horasHoy = document.getElementById("horasHoy");
const horasAcumuladas = document.getElementById("horasAcumuladas");
const montoAcumulado = document.getElementById("montoAcumulado");
const totalRegistros = document.getElementById("totalRegistros");
const formFiltrosHoras = document.getElementById("formFiltrosHoras");
const filtroPeriodoRapido = document.getElementById("filtroPeriodoRapido");
const filtroDesde = document.getElementById("filtroDesde");
const filtroHasta = document.getElementById("filtroHasta");
const filtroCliente = document.getElementById("filtroCliente");
const filtroTarea = document.getElementById("filtroTarea");
const grupoFiltroUsuario = document.getElementById("grupoFiltroUsuario");
const filtroUsuario = document.getElementById("filtroUsuario");
const estadoFiltrosHoras = document.getElementById("estadoFiltrosHoras");
const alcanceResumen = document.getElementById("alcanceResumen");
const thUsuarioRegistro = document.getElementById("thUsuarioRegistro");

let tareasFiltroHoras = [];
let falloCargaFiltrosHoras = false;

// Elementos que esta versión del script necesita. Si faltan, el navegador conserva el HTML de una versión
// anterior (los .js se revalidan en cada visita y los .html pueden quedar en caché): se avisa y se pide
// recargar en lugar de dejar la pantalla a medias, con el historial en «Cargando…» y sin filtros.
const ELEMENTOS_REQUERIDOS = [
  "accionesControlHoras", "formFiltrosHoras", "panelRegistroManual",
  "formRegistroManual", "tablaRegistros", "alcanceResumen"
];

function mostrarAvisoVersionAnterior() {
  const contenedor = document.createElement("div");
  contenedor.className = "mensaje error";
  contenedor.setAttribute("role", "alert");

  const texto = document.createElement("p");
  texto.textContent =
    "Su navegador conserva una versión anterior de esta pantalla y no puede mostrarla completa. " +
    "Recargue la página para obtener la versión actual.";
  contenedor.appendChild(texto);

  const boton = document.createElement("button");
  boton.type = "button";
  boton.className = "btn btn-primary";
  boton.textContent = "Recargar página";
  boton.addEventListener("click", () => window.location.reload());
  contenedor.appendChild(boton);

  const principal = document.querySelector("main") || document.body;
  principal.insertBefore(contenedor, principal.firstChild);
}

document.addEventListener("DOMContentLoaded", async () => {
  usuarioActual = await obtenerUsuarioActual();

  if (!usuarioActual) {
    window.location.href = "../auth/login.html";
    return;
  }

  if (ELEMENTOS_REQUERIDOS.some(id => !document.getElementById(id))) {
    mostrarAvisoVersionAnterior();
    return;
  }

  const accionesControlHoras = document.getElementById("accionesControlHoras");
  const botonRegistroManual = document.createElement("button");
  botonRegistroManual.type = "button";
  botonRegistroManual.id = "btnRegistroManual";
  botonRegistroManual.className = "btn btn-primary";
  botonRegistroManual.textContent = "Registrar horas manualmente";
  accionesControlHoras.appendChild(botonRegistroManual);

  if (usuarioActual.nombre_rol === "ADMINISTRADOR") {
    const enlaceInformesHoras = document.createElement("a");
    enlaceInformesHoras.className = "btn btn-secondary";
    enlaceInformesHoras.href = "../reportes/reportes.html?tipo=horas";
    enlaceInformesHoras.textContent = "Informes de horas";
    accionesControlHoras.appendChild(enlaceInformesHoras);

    const enlaceTarifas = document.createElement("a");
    enlaceTarifas.className = "btn btn-secondary";
    enlaceTarifas.href = "../tarifas/tarifas.html";
    enlaceTarifas.textContent = "Tarifas";
    accionesControlHoras.appendChild(enlaceTarifas);
  }
  accionesControlHoras.hidden = false;
  configurarRegistroManual();

  const esAdministrador = usuarioActual.nombre_rol === "ADMINISTRADOR";
  grupoFiltroUsuario.hidden = !esAdministrador;
  thUsuarioRegistro.hidden = !esAdministrador;
  document.querySelector("#tablaRegistros td").colSpan = esAdministrador ? 10 : 9;
  actualizarRotulosResumen();

  clienteBusqueda.addEventListener("input", manejarCambioCliente);
  tareaBusqueda.addEventListener("input", manejarCambioTarea);
  btnIniciar.addEventListener("click", iniciarTemporizador);
  btnDetener.addEventListener("click", detenerTemporizador);
  formFiltrosHoras.addEventListener("submit", async evento => {
    evento.preventDefault();
    await cargarRegistros();
  });
  filtroPeriodoRapido.addEventListener("change", actualizarFechasFiltro);
  [filtroDesde, filtroHasta].forEach(input => {
    ["input", "change"].forEach(evento => input.addEventListener(evento, () => {
      filtroPeriodoRapido.value = "";
    }));
  });
  filtroCliente.addEventListener("change", actualizarTareasFiltro);
  document.getElementById("btnLimpiarFiltrosHoras").addEventListener("click", async () => {
    formFiltrosHoras.reset();
    filtroPeriodoRapido.value = "";
    actualizarTareasFiltro();
    await cargarRegistros();
  });

  await cargarContexto();
  await cargarFiltrosRegistros();
  const solicitud = leerSolicitudDeTarea();
  if (solicitud) filtrarHistorialPorTarea(solicitud.idTarea);
  await cargarRegistros();
  if (solicitud) aplicarSolicitudDeTarea(solicitud);
});

// El detalle de la tarea enlaza aquí con ?id_tarea=<id> (y &registrar=manual para abrir el registro
// manual). Solo se aceptan identificadores numéricos: cualquier otra cosa se ignora.
function leerSolicitudDeTarea() {
  const parametros = new URLSearchParams(window.location.search);
  const id = parametros.get("id_tarea");
  if (!id || !/^[1-9][0-9]{0,9}$/.test(id)) return null;
  return { idTarea: Number(id), registrarManual: parametros.get("registrar") === "manual" };
}

function filtrarHistorialPorTarea(idTarea) {
  const tarea = tareasFiltroHoras.find(t => Number(t.id_tarea) === idTarea);
  if (!tarea) return;
  filtroCliente.value = String(tarea.id_cliente);
  actualizarTareasFiltro();
  filtroTarea.value = String(tarea.id_tarea);
}

function aplicarSolicitudDeTarea({ idTarea, registrarManual }) {
  const tarea = tareasDisponibles.find(t => Number(t.id_tarea) === idTarea);

  if (!tarea) {
    if (!temporizadorActivo || Number(temporizadorActivo.id_tarea) !== idTarea) {
      mostrarMensaje(
        "La tarea indicada no está disponible para registrar horas: está finalizada, su cliente " +
          "está inactivo o no está asignada a usted.",
        "info"
      );
    }
    return;
  }

  if (!temporizadorActivo) {
    seleccionarClienteDesdeTarea(tarea);
    tareaBusqueda.value = obtenerTextoTarea(tarea);
    idTareaSeleccionada.value = tarea.id_tarea;
    actualizarVistaSeleccion();
  }

  if (registrarManual && panelRegistroManual) {
    panelRegistroManual.abrir();
    document.getElementById("rmCliente").value = String(tarea.id_cliente);
    poblarTareasRegistroManual();
    document.getElementById("rmTarea").value = String(tarea.id_tarea);
    document.getElementById("rmHoraInicio").focus({ preventScroll: true });
  }
}

async function cargarFiltrosRegistros() {
  try {
    const response = await fetch(`${API_URL}/control-horas/filtros`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      falloCargaFiltrosHoras = true;
      manejarAccesoDenegado(response.status, data.error);
      estadoFiltrosHoras.textContent = data.error || "No se pudieron cargar los filtros.";
      return;
    }

    falloCargaFiltrosHoras = false;
    tareasFiltroHoras = data.tareas || [];
    poblarFiltro(
      filtroCliente,
      data.clientes || [],
      "Todos los clientes",
      cliente => [cliente.id_cliente, obtenerTextoCliente(cliente)]
    );
    poblarFiltro(
      filtroUsuario,
      data.usuarios || [],
      "Todos los usuarios",
      usuario => [usuario.id_usuario, usuario.nombres]
    );
    actualizarTareasFiltro();
  } catch (error) {
    console.error(error);
    falloCargaFiltrosHoras = true;
    estadoFiltrosHoras.textContent = "No se pudieron cargar los filtros.";
    mostrarMensaje("No se pudieron cargar los filtros.", "error");
  }
}

function poblarFiltro(select, opciones, textoInicial, obtenerOpcion) {
  select.textContent = "";
  const opcionInicial = document.createElement("option");
  opcionInicial.value = "";
  opcionInicial.textContent = textoInicial;
  select.appendChild(opcionInicial);

  opciones.forEach(opcion => {
    const [valor, texto] = obtenerOpcion(opcion);
    const elemento = document.createElement("option");
    elemento.value = valor;
    elemento.textContent = texto || "";
    select.appendChild(elemento);
  });
}

function actualizarTareasFiltro() {
  const idCliente = filtroCliente.value;
  const tareas = idCliente
    ? tareasFiltroHoras.filter(tarea => Number(tarea.id_cliente) === Number(idCliente))
    : tareasFiltroHoras;

  poblarFiltro(
    filtroTarea,
    tareas,
    "Todas las tareas",
    tarea => [
      tarea.id_tarea,
      `${tarea.titulo}${tarea.cliente ? ` — ${tarea.cliente}` : ""}`
    ]
  );
}

function actualizarFechasFiltro() {
  const valor = filtroPeriodoRapido.value;
  if (!valor) return;

  const fin = new Date();
  const inicio = new Date(fin);
  if (valor === "anio") inicio.setMonth(0, 1);
  else if (valor === "mes") inicio.setMonth(inicio.getMonth() - 1);
  else inicio.setDate(inicio.getDate() - 6);

  filtroDesde.value = fechaLocal(inicio);
  filtroHasta.value = fechaLocal(fin);
}

function fechaLocal(fecha) {
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;
}

function crearParametrosFiltrosHoras() {
  const desde = filtroDesde.value;
  const hasta = filtroHasta.value;

  if (Boolean(desde) !== Boolean(hasta)) {
    const error = "Debe indicar ambas fechas o dejar las dos vacías.";
    estadoFiltrosHoras.textContent = error;
    mostrarMensaje(error, "error");
    return null;
  }

  if (desde && desde > hasta) {
    const error = "La fecha desde no puede ser posterior a la fecha hasta.";
    estadoFiltrosHoras.textContent = error;
    mostrarMensaje(error, "error");
    return null;
  }

  const parametros = new URLSearchParams();
  if (desde) {
    parametros.set("fecha_inicio", desde);
    parametros.set("fecha_fin", hasta);
  }
  if (filtroCliente.value) parametros.set("id_cliente", filtroCliente.value);
  if (filtroTarea.value) parametros.set("id_tarea", filtroTarea.value);
  if (usuarioActual.nombre_rol === "ADMINISTRADOR" && filtroUsuario.value) {
    parametros.set("id_usuario", filtroUsuario.value);
  }
  return parametros;
}

async function cargarContexto() {
  try {
    mostrarMensaje("Cargando control de horas...", "info");

    const response = await fetch(`${API_URL}/control-horas/contexto`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      manejarAccesoDenegado(response.status, data.error);
      return;
    }

    tareasDisponibles = data.tareas || [];

    if (data.temporizador_activo) {
      tareasDisponibles = asegurarTareaTemporizador(
        tareasDisponibles,
        data.temporizador_activo
      );
    }

    clientesDisponibles = obtenerClientesDesdeTareas(tareasDisponibles);
    renderizarClientes();
    renderizarTareas("");

    if (data.temporizador_activo) {
      activarTemporizador(data.temporizador_activo);
      mostrarMensaje("Temporizador activo recuperado.", "info");
    } else {
      desactivarTemporizador({ limpiarMensaje: false });
      mostrarMensaje("");
    }
  } catch (error) {
    console.error(error);
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  }
}

function asegurarTareaTemporizador(tareas, datosTemporizador) {
  const existe = tareas.some(
    tarea => Number(tarea.id_tarea) === Number(datosTemporizador.id_tarea)
  );

  if (existe) return tareas;

  return [
    ...tareas,
    {
      id_tarea: datosTemporizador.id_tarea,
      id_cliente: datosTemporizador.id_cliente,
      titulo: datosTemporizador.tarea,
      descripcion: datosTemporizador.descripcion,
      cliente: datosTemporizador.cliente,
      cliente_rut: datosTemporizador.cliente_rut
    }
  ];
}

function obtenerClientesDesdeTareas(tareas) {
  const clientesPorId = new Map();

  tareas.forEach(tarea => {
    if (!clientesPorId.has(Number(tarea.id_cliente))) {
      clientesPorId.set(Number(tarea.id_cliente), {
        id_cliente: Number(tarea.id_cliente),
        razon_social: tarea.cliente,
        rut: tarea.cliente_rut
      });
    }
  });

  return Array.from(clientesPorId.values())
    .sort((clienteA, clienteB) =>
      clienteA.razon_social.localeCompare(clienteB.razon_social, "es")
    );
}

function renderizarClientes() {
  clientesControlDatalist.textContent = "";

  clientesDisponibles.forEach(cliente => {
    const opcion = document.createElement("option");
    opcion.value = obtenerTextoCliente(cliente);
    clientesControlDatalist.appendChild(opcion);
  });
}

function renderizarTareas(clienteId) {
  tareasControlDatalist.textContent = "";

  const tareas = obtenerTareasParaBusqueda(clienteId);

  tareas.forEach(tarea => {
    const opcion = document.createElement("option");
    opcion.value = obtenerTextoTarea(tarea, !clienteId);
    tareasControlDatalist.appendChild(opcion);
  });

  actualizarAyudaTareas(clienteId, tareas.length);
}

function obtenerTareasParaBusqueda(clienteId) {
  if (!clienteId) {
    return [...tareasDisponibles].sort(ordenarTareasPorCliente);
  }

  return tareasDisponibles
    .filter(tarea => Number(tarea.id_cliente) === Number(clienteId))
    .sort(ordenarTareasPorTitulo);
}

function ordenarTareasPorCliente(tareaA, tareaB) {
  return (
    tareaA.cliente.localeCompare(tareaB.cliente, "es") ||
    tareaA.titulo.localeCompare(tareaB.titulo, "es")
  );
}

function ordenarTareasPorTitulo(tareaA, tareaB) {
  return tareaA.titulo.localeCompare(tareaB.titulo, "es");
}

function obtenerTareaSeleccionada() {
  return tareasDisponibles.find(
    tarea => Number(tarea.id_tarea) === Number(idTareaSeleccionada.value)
  );
}

function manejarCambioCliente() {
  if (temporizadorActivo) return;

  const cliente = resolverClienteDesdeTexto(clienteBusqueda.value);
  const clienteAnterior = idClienteSeleccionado.value;

  idClienteSeleccionado.value = cliente ? cliente.id_cliente : "";

  if (String(clienteAnterior) !== String(idClienteSeleccionado.value)) {
    tareaBusqueda.value = "";
    idTareaSeleccionada.value = "";
  }

  renderizarTareas(idClienteSeleccionado.value);
  actualizarVistaSeleccion();
}

function manejarCambioTarea() {
  if (temporizadorActivo) return;

  const tarea = resolverTareaDesdeTexto(tareaBusqueda.value);
  idTareaSeleccionada.value = tarea ? tarea.id_tarea : "";

  if (tarea) {
    seleccionarClienteDesdeTarea(tarea);
  }

  actualizarVistaSeleccion();
}

function resolverClienteDesdeTexto(texto) {
  const valor = normalizarTexto(texto);

  if (!valor) return null;

  const exacto = clientesDisponibles.find(
    cliente =>
      normalizarTexto(obtenerTextoCliente(cliente)) === valor ||
      normalizarTexto(cliente.razon_social) === valor ||
      normalizarTexto(cliente.rut) === valor
  );

  if (exacto) return exacto;

  const coincidencias = clientesDisponibles.filter(cliente =>
    normalizarTexto(obtenerTextoCliente(cliente)).includes(valor) ||
    normalizarTexto(cliente.razon_social).includes(valor) ||
    normalizarTexto(cliente.rut).includes(valor)
  );

  return coincidencias.length === 1 ? coincidencias[0] : null;
}

function resolverTareaDesdeTexto(texto) {
  const clienteId = idClienteSeleccionado.value;
  const valor = normalizarTexto(texto);

  if (!valor) return null;

  const tareas = obtenerTareasParaBusqueda(clienteId);
  const exactas = tareas.filter(
    tarea =>
      normalizarTexto(obtenerTextoTarea(tarea, !clienteId)) === valor ||
      normalizarTexto(obtenerTextoTarea(tarea, true)) === valor ||
      normalizarTexto(tarea.titulo) === valor
  );

  if (exactas.length === 1) return exactas[0];

  const coincidencias = tareas.filter(tarea =>
    normalizarTexto(obtenerTextoTarea(tarea, !clienteId)).includes(valor) ||
    normalizarTexto(obtenerTextoTarea(tarea, true)).includes(valor) ||
    normalizarTexto(tarea.titulo).includes(valor) ||
    normalizarTexto(tarea.cliente).includes(valor) ||
    normalizarTexto(tarea.cliente_rut).includes(valor)
  );

  return coincidencias.length === 1 ? coincidencias[0] : null;
}

function seleccionarClienteDesdeTarea(tarea) {
  const cliente = clientesDisponibles.find(
    clienteDisponible => Number(clienteDisponible.id_cliente) === Number(tarea.id_cliente)
  );

  if (!cliente) return;

  idClienteSeleccionado.value = cliente.id_cliente;
  clienteBusqueda.value = obtenerTextoCliente(cliente);
  renderizarTareas(cliente.id_cliente);
}

function actualizarVistaSeleccion() {
  const tarea = obtenerTareaSeleccionada();

  if (tarea) {
    clienteActivo.textContent = tarea.cliente || "Cliente no disponible";
    tareaActiva.textContent = tarea.titulo || "Tarea sin título";
    descripcionActiva.textContent = tarea.descripcion || "Sin descripción disponible.";
    inicioTemporizador.textContent = "Listo para iniciar.";
  } else {
    clienteActivo.textContent = "Sin cliente seleccionado";
    tareaActiva.textContent = "Sin tarea seleccionada";
    descripcionActiva.textContent = "Sin descripción disponible.";
    inicioTemporizador.textContent = "Seleccione una tarea para comenzar.";
  }

  actualizarEstadoBotones();
}

function actualizarAyudaTareas(clienteId, totalTareas) {
  if (!clienteId) {
    ayudaTareas.textContent = totalTareas
      ? `${totalTareas} tareas disponibles. Puede buscar por tarea o cliente.`
      : "No hay tareas disponibles.";
    return;
  }

  ayudaTareas.textContent = totalTareas
    ? `${totalTareas} tarea${totalTareas === 1 ? "" : "s"} disponible${totalTareas === 1 ? "" : "s"} para este cliente.`
    : "Este cliente no tiene tareas disponibles.";
}

function actualizarEstadoBotones() {
  btnIniciar.disabled = Boolean(temporizadorActivo) || !idTareaSeleccionada.value;
  btnDetener.disabled = !temporizadorActivo;
}

async function iniciarTemporizador() {
  const tarea = obtenerTareaSeleccionada();

  if (!tarea) {
    mostrarMensaje("Debe seleccionar una tarea válida.", "error");
    actualizarEstadoBotones();
    return;
  }

  setBotonCargando(btnIniciar, true, "Iniciando...");
  mostrarMensaje("");

  try {
    const response = await fetch(`${API_URL}/control-horas/iniciar`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        id_tarea: tarea.id_tarea
      })
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo iniciar el temporizador.", "error");

      if (response.status === 409) {
        await cargarContexto();
      }
      return;
    }

    activarTemporizador(data.temporizador_activo);
    mostrarMensaje(data.message || "Temporizador iniciado.", "success");
  } catch (error) {
    console.error(error);
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  } finally {
    setBotonCargando(btnIniciar, false, "Iniciar");
    actualizarEstadoBotones();
  }
}

async function detenerTemporizador() {
  if (!temporizadorActivo) {
    mostrarMensaje("No existe un temporizador activo.", "error");
    return;
  }

  setBotonCargando(btnDetener, true, "Deteniendo...");
  mostrarMensaje("");

  try {
    // Sin cuerpo no se declara Content-Type: el backend valida todo cuerpo JSON.
    const response = await fetch(`${API_URL}/control-horas/detener`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo detener el temporizador.", "error");
      return;
    }

    const textoExito = data.message || "Horas registradas correctamente.";
    desactivarTemporizador({ limpiarMensaje: false });
    mostrarMensaje(textoExito, "success");

    await cargarRegistros();
    await cargarContexto();
    // H-18 — cargarContexto reescribe el aviso («Cargando…» y luego nada): se repone el de éxito
    // salvo que la recarga haya fallado y dejado un error.
    if (!mensajeControl.classList.contains("error")) {
      mostrarMensaje(textoExito, "success");
    }
  } catch (error) {
    console.error(error);
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  } finally {
    setBotonCargando(btnDetener, false, "Detener y registrar");
    actualizarEstadoBotones();
  }
}

function activarTemporizador(datosTemporizador) {
  temporizadorActivo = datosTemporizador;
  timerPanel.classList.add("is-active");
  estadoTemporizador.textContent = "En curso";
  estadoTemporizador.className = "badge timer-status is-running";

  clienteActivo.textContent = datosTemporizador.cliente || "Cliente no disponible";
  tareaActiva.textContent = datosTemporizador.tarea || "Tarea no disponible";
  descripcionActiva.textContent = datosTemporizador.descripcion || "Sin descripción disponible.";
  inicioTemporizador.textContent = `Inicio registrado por servidor: ${formatearFechaHora(datosTemporizador.inicio)}`;

  clienteBusqueda.value = obtenerTextoCliente({
    razon_social: datosTemporizador.cliente,
    rut: datosTemporizador.cliente_rut
  });
  idClienteSeleccionado.value = datosTemporizador.id_cliente;
  renderizarTareas(datosTemporizador.id_cliente);

  tareaBusqueda.value = obtenerTextoTarea({
    titulo: datosTemporizador.tarea,
    id_tarea: datosTemporizador.id_tarea,
    cliente: datosTemporizador.cliente
  });
  idTareaSeleccionada.value = datosTemporizador.id_tarea;

  clienteBusqueda.disabled = true;
  tareaBusqueda.disabled = true;
  ayudaTareas.textContent = "Hay un temporizador activo. Deténgalo antes de iniciar otro.";

  actualizarTemporizador();
  clearInterval(intervaloTemporizador);
  intervaloTemporizador = setInterval(actualizarTemporizador, 1000);
  actualizarEstadoBotones();
}

function desactivarTemporizador({ limpiarMensaje = true } = {}) {
  temporizadorActivo = null;
  clearInterval(intervaloTemporizador);
  intervaloTemporizador = null;

  timerPanel.classList.remove("is-active");
  estadoTemporizador.textContent = "Sin temporizador activo";
  estadoTemporizador.className = "badge timer-status";
  temporizador.textContent = "00:00:00";
  inicioTemporizador.textContent = "Seleccione una tarea para comenzar.";

  clienteBusqueda.disabled = false;
  clienteBusqueda.value = "";
  idClienteSeleccionado.value = "";
  tareaBusqueda.disabled = false;
  tareaBusqueda.value = "";
  idTareaSeleccionada.value = "";
  renderizarTareas("");
  actualizarVistaSeleccion();

  if (limpiarMensaje) {
    mostrarMensaje("");
  }
}

function actualizarTemporizador() {
  if (!temporizadorActivo) return;

  const inicio = new Date(temporizadorActivo.inicio);
  const segundos = Math.max(0, Math.floor((Date.now() - inicio.getTime()) / 1000));
  temporizador.textContent = formatearDuracionSegundos(segundos);
}

async function cargarRegistros() {
  const parametros = crearParametrosFiltrosHoras();
  if (!parametros) return;

  try {
    mostrarFilaTabla("Cargando registros...");

    const query = parametros.toString();
    const url = `${API_URL}/control-horas/registros${query ? `?${query}` : ""}`;
    const response = await fetch(url, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      manejarAccesoDenegado(response.status, data.error);
      estadoFiltrosHoras.textContent = data.error || "No se pudieron cargar los registros.";
      return;
    }

    const registros = data.registros || [];
    renderizarRegistros(registros);
    renderizarResumen(data.resumen || {});
    estadoFiltrosHoras.textContent = registros.length
      ? `Mostrando ${registros.length} ${registros.length === 1 ? "registro" : "registros"}.`
      : "No hay registros para los filtros elegidos.";
    if (falloCargaFiltrosHoras) {
      estadoFiltrosHoras.textContent += " No se pudieron cargar los filtros.";
    }
  } catch (error) {
    console.error(error);
    mostrarFilaTabla("Error al conectar con el servidor.");
    estadoFiltrosHoras.textContent = "Error al conectar con el servidor.";
  }
}

function renderizarRegistros(registros) {
  tablaRegistros.textContent = "";

  if (registros.length === 0) {
    mostrarFilaTabla("No hay horas registradas.");
    return;
  }

  registros.forEach(registro => {
    const fila = document.createElement("tr");
    agregarCelda(fila, registro.fecha || extraerFecha(registro.inicio));
    if (usuarioActual.nombre_rol === "ADMINISTRADOR") {
      agregarCelda(fila, registro.usuario_responsable);
    }
    agregarCelda(fila, registro.cliente);
    agregarCelda(fila, registro.tarea);
    agregarCelda(fila, registro.inicio_hora || registro.inicio);
    agregarCelda(fila, registro.fin);
    agregarCelda(fila, formatearMinutos(registro.duracion_minutos));
    agregarCelda(fila, formatearMoneda(registro.tarifa_hora));
    agregarCelda(fila, formatearMoneda(registro.monto));
    agregarCeldaOrigen(fila, registro);

    tablaRegistros.appendChild(fila);
  });
}

function mostrarFilaTabla(mensaje) {
  tablaRegistros.textContent = "";
  const fila = document.createElement("tr");
  const celda = document.createElement("td");
  celda.colSpan = usuarioActual.nombre_rol === "ADMINISTRADOR" ? 10 : 9;
  celda.className = "text-loading";
  celda.textContent = mensaje;
  fila.appendChild(celda);
  tablaRegistros.appendChild(fila);
}

function agregarCelda(fila, valor) {
  const celda = document.createElement("td");
  celda.textContent = valor || "-";
  fila.appendChild(celda);
}

function agregarCeldaOrigen(fila, registro) {
  const celda = document.createElement("td");
  const manual = registro.origen === "MANUAL";

  const insignia = document.createElement("span");
  insignia.className = manual ? "badge badge-info" : "badge badge-pending";
  insignia.textContent = manual ? "Manual" : "Temporizador";
  celda.appendChild(insignia);

  if (manual && registro.observacion) {
    const observacion = document.createElement("small");
    observacion.className = "origen-observacion";
    observacion.textContent = registro.observacion;
    celda.appendChild(observacion);
  }
  fila.appendChild(celda);
}

function renderizarResumen(resumen) {
  actualizarRotulosResumen();
  horasHoy.textContent = formatearMinutos(resumen.minutos_hoy || 0);
  horasAcumuladas.textContent = formatearMinutos(resumen.minutos_acumulados || 0);
  montoAcumulado.textContent = formatearMoneda(resumen.monto_acumulado || 0);
  totalRegistros.textContent = String(resumen.total_registros || 0);

  renderizarTotales("totalesCliente", resumen.totales_cliente || []);
  renderizarTotales("totalesTarea", resumen.totales_tarea || []);
}

function actualizarRotulosResumen() {
  const esAdministrador = usuarioActual?.nombre_rol === "ADMINISTRADOR";
  const idUsuario = esAdministrador ? filtroUsuario.value : "";
  const nombreUsuario = idUsuario
    ? filtroUsuario.selectedOptions[0]?.textContent
    : "";
  const sufijo = esAdministrador
    ? ` · ${nombreUsuario || "todos los usuarios"}`
    : "";

  document.getElementById("rotuloHorasHoy").textContent =
    `${esAdministrador ? "Horas de hoy" : "Mis horas hoy"}${sufijo}`;
  document.getElementById("rotuloHorasTotal").textContent =
    `${esAdministrador ? "Horas en total" : "Mis horas en total"}${sufijo}`;
  document.getElementById("rotuloMontoTotal").textContent =
    `${esAdministrador ? "Monto acumulado" : "Mi monto acumulado"}${sufijo}`;
  document.getElementById("rotuloRegistros").textContent =
    `${esAdministrador ? "Registros cerrados" : "Mis registros cerrados"}${sufijo}`;

  const alcance = esAdministrador
    ? `Mostrando: registros de ${nombreUsuario || "todos los usuarios"}`
    : "Mostrando: mis registros";
  const filtros = [];
  if (filtroDesde.value && filtroHasta.value) {
    filtros.push(`período ${formatearFechaFiltro(filtroDesde.value)} a ${formatearFechaFiltro(filtroHasta.value)}`);
  }
  if (filtroCliente.value) {
    filtros.push(`cliente ${filtroCliente.selectedOptions[0]?.textContent || ""}`);
  }
  if (filtroTarea.value) {
    filtros.push(`tarea ${filtroTarea.selectedOptions[0]?.textContent || ""}`);
  }
  if (idUsuario) filtros.push(`usuario ${nombreUsuario}`);

  alcanceResumen.textContent = `${alcance} · Filtros: ${filtros.length ? `${filtros.join(" · ")}.` : "ninguno."}`;
}

function formatearFechaFiltro(fecha) {
  const [anio, mes, dia] = fecha.split("-");
  return `${dia}-${mes}-${anio}`;
}

function renderizarTotales(idContenedor, totales) {
  const contenedor = document.getElementById(idContenedor);
  contenedor.textContent = "";

  if (totales.length === 0) {
    const vacio = document.createElement("p");
    vacio.className = "total-vacio";
    vacio.textContent = "Sin registros.";
    contenedor.appendChild(vacio);
    return;
  }

  totales.forEach(total => {
    const fila = document.createElement("div");
    fila.className = "total-fila";

    [total.nombre, formatearMinutos(total.minutos), formatearMoneda(total.monto)]
      .forEach(valor => {
        const texto = document.createElement("span");
        texto.textContent = valor;
        fila.appendChild(texto);
      });

    contenedor.appendChild(fila);
  });
}

function obtenerTextoCliente(cliente) {
  if (!cliente) return "";

  return cliente.rut
    ? `${cliente.razon_social} - ${cliente.rut}`
    : cliente.razon_social;
}

function obtenerTextoTarea(tarea, incluirCliente = false) {
  if (!tarea) return "";

  const partes = [tarea.titulo];

  if (incluirCliente) {
    partes.push(tarea.cliente);
  }

  partes.push(`ID ${tarea.id_tarea}`);

  return partes.join(" - ");
}

function normalizarTexto(texto) {
  return String(texto || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function formatearDuracionSegundos(totalSegundos) {
  const horas = Math.floor(totalSegundos / 3600);
  const minutos = Math.floor((totalSegundos % 3600) / 60);
  const segundos = totalSegundos % 60;

  return `${rellenar(horas)}:${rellenar(minutos)}:${rellenar(segundos)}`;
}

function formatearMinutos(totalMinutos) {
  const minutosRedondeados = Math.round(Number(totalMinutos) || 0);
  const horas = Math.floor(minutosRedondeados / 60);
  const minutos = minutosRedondeados % 60;
  return `${rellenar(horas)}h ${rellenar(minutos)}m`;
}

function rellenar(numero) {
  return String(numero).padStart(2, "0");
}

function formatearMoneda(valor) {
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0
  }).format(Number(valor) || 0);
}

function formatearFechaHora(valor) {
  if (!valor) return "No disponible";

  return formatearFechaHora24(valor);
}

function extraerFecha(valor) {
  if (!valor) return "-";
  return String(valor).split(" ")[0] || valor;
}

function setBotonCargando(boton, cargando, texto) {
  boton.disabled = cargando;
  boton.classList.toggle("is-loading", cargando);
  boton.textContent = texto;
}

function mostrarMensaje(texto, tipo = "") {
  mensajeControl.textContent = texto;
  mensajeControl.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

async function leerRespuestaJson(response) {
  const texto = await response.text();

  if (!texto) return {};

  try {
    return JSON.parse(texto);
  } catch (error) {
    console.error("Respuesta no válida del servidor:", texto);
    return { error: "Respuesta no válida del servidor." };
  }
}

async function manejarAccesoDenegado(estado, mensaje) {
  if (estado === 401 || estado === 403) {
    await avisarAccion(mensaje || "La sesión ya no está activa.", "advertencia");
    window.location.href = "../auth/login.html";
    return;
  }

  mostrarMensaje(mensaje || "No se pudieron cargar los datos.", "error");
}

// ---------------------------------------------------------------------------
// Registro manual de horas (CU-14 y CU-29): para cuando no se pudo usar el temporizador.
// El navegador solo revisa lo evidente para avisar rápido; el servidor vuelve a validar
// todo y es quien calcula la duración, la tarifa y el monto.
// ---------------------------------------------------------------------------
const DIAS_MAXIMOS_RETROACTIVO = 30;
let panelRegistroManual = null;

function configurarRegistroManual() {
  const formulario = document.getElementById("formRegistroManual");
  if (!formulario) return;

  panelRegistroManual = configurarPanelAlta({
    botonId: "btnRegistroManual",
    panelId: "panelRegistroManual",
    primerCampoId: "rmCliente",
    botonCerrarId: "btnCancelarRegistroManual",
    alAbrir: prepararRegistroManual
  });

  document.getElementById("rmCliente").addEventListener("change", poblarTareasRegistroManual);
  ["rmHoraInicio", "rmHoraFin"].forEach(id => {
    document.getElementById(id).addEventListener("input", actualizarDuracionRegistroManual);
  });
  formulario.addEventListener("submit", enviarRegistroManual);
}

function mostrarMensajeRegistroManual(texto, tipo = "") {
  const mensaje = document.getElementById("mensajeRegistroManual");
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

function prepararRegistroManual() {
  document.getElementById("formRegistroManual").reset();
  mostrarMensajeRegistroManual("");

  const selectCliente = document.getElementById("rmCliente");
  selectCliente.textContent = "";
  const opcionInicial = document.createElement("option");
  opcionInicial.value = "";
  opcionInicial.textContent = "Seleccione un cliente";
  selectCliente.appendChild(opcionInicial);
  clientesDisponibles.forEach(cliente => {
    const opcion = document.createElement("option");
    opcion.value = cliente.id_cliente;
    opcion.textContent = obtenerTextoCliente(cliente);
    selectCliente.appendChild(opcion);
  });
  poblarTareasRegistroManual();

  const hoy = new Date();
  const limite = new Date(hoy);
  limite.setDate(limite.getDate() - DIAS_MAXIMOS_RETROACTIVO);
  const fecha = document.getElementById("rmFecha");
  fecha.max = fechaLocal(hoy);
  fecha.min = fechaLocal(limite);
  fecha.value = fechaLocal(hoy);
  actualizarDuracionRegistroManual();

  const sinTareas = tareasDisponibles.length === 0;
  document.getElementById("btnGuardarRegistroManual").disabled = sinTareas;
  if (sinTareas) {
    mostrarMensajeRegistroManual("No tiene tareas habilitadas para registrar horas.", "info");
  }
}

function poblarTareasRegistroManual() {
  const selectTarea = document.getElementById("rmTarea");
  const idCliente = document.getElementById("rmCliente").value;
  selectTarea.textContent = "";

  const opcionInicial = document.createElement("option");
  opcionInicial.value = "";
  selectTarea.appendChild(opcionInicial);

  if (!idCliente) {
    opcionInicial.textContent = "Seleccione primero un cliente";
    selectTarea.disabled = true;
    return;
  }

  const tareas = obtenerTareasParaBusqueda(idCliente);
  opcionInicial.textContent = tareas.length ? "Seleccione una tarea" : "Este cliente no tiene tareas disponibles";
  tareas.forEach(tarea => {
    const opcion = document.createElement("option");
    opcion.value = tarea.id_tarea;
    opcion.textContent = obtenerTextoTarea(tarea);
    selectTarea.appendChild(opcion);
  });
  selectTarea.disabled = tareas.length === 0;
}

function minutosDeHora(texto) {
  const [horas, minutos] = String(texto || "").split(":").map(Number);
  return Number.isInteger(horas) && Number.isInteger(minutos) ? horas * 60 + minutos : null;
}

function actualizarDuracionRegistroManual() {
  const duracion = document.getElementById("rmDuracion");
  const inicio = minutosDeHora(document.getElementById("rmHoraInicio").value);
  const fin = minutosDeHora(document.getElementById("rmHoraFin").value);

  if (inicio === null || fin === null) {
    duracion.textContent = "Indique la hora de inicio y la de término.";
  } else if (fin <= inicio) {
    duracion.textContent = "La hora de término debe ser posterior a la de inicio.";
  } else {
    const total = fin - inicio;
    duracion.textContent = `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")} min`;
  }
}

function leerRegistroManual() {
  const cliente = document.getElementById("rmCliente");
  const tarea = document.getElementById("rmTarea");
  const fecha = document.getElementById("rmFecha");
  const horaInicio = document.getElementById("rmHoraInicio");
  const horaFin = document.getElementById("rmHoraFin");
  const observacion = document.getElementById("rmObservacion");

  const falla = (campo, error) => ({ campo, error });

  if (!cliente.value) return falla(cliente, "Seleccione un cliente.");
  if (!tarea.value) return falla(tarea, "Seleccione una tarea.");
  if (!fecha.value) return falla(fecha, "Indique la fecha del trabajo.");

  const ahora = new Date();
  const hoy = fechaLocal(ahora);
  const limite = new Date(ahora);
  limite.setDate(limite.getDate() - DIAS_MAXIMOS_RETROACTIVO);
  if (fecha.value > hoy) return falla(fecha, "No se pueden registrar horas que todavía no ocurrieron.");
  if (fecha.value < fechaLocal(limite)) {
    return falla(fecha, `Solo se pueden registrar horas de los últimos ${DIAS_MAXIMOS_RETROACTIVO} días.`);
  }

  const inicio = minutosDeHora(horaInicio.value);
  const fin = minutosDeHora(horaFin.value);
  if (inicio === null) return falla(horaInicio, "Indique la hora de inicio.");
  if (fin === null) return falla(horaFin, "Indique la hora de término.");
  if (fin <= inicio) return falla(horaFin, "La hora de término debe ser posterior a la hora de inicio.");
  if (fecha.value === hoy && fin > ahora.getHours() * 60 + ahora.getMinutes()) {
    return falla(horaFin, "No se pueden registrar horas que todavía no ocurrieron.");
  }

  const texto = observacion.value.trim();
  if (!texto) return falla(observacion, "Escriba una observación con el trabajo realizado.");

  return {
    datos: {
      id_tarea: Number(tarea.value),
      fecha: fecha.value,
      hora_inicio: horaInicio.value,
      hora_fin: horaFin.value,
      observacion: texto
    },
    minutos: fin - inicio
  };
}

async function enviarRegistroManual(evento) {
  evento.preventDefault();
  mostrarMensajeRegistroManual("");

  const lectura = leerRegistroManual();
  if (lectura.error) {
    mostrarMensajeRegistroManual(lectura.error, "error");
    lectura.campo.focus();
    return;
  }

  const tarea = tareasDisponibles.find(
    t => Number(t.id_tarea) === lectura.datos.id_tarea
  );
  const acepta = await confirmarAccion(
    `Se registrarán ${formatearMinutos(lectura.minutos)} en «${tarea ? tarea.titulo : "la tarea"}»` +
      `${tarea ? ` de ${tarea.cliente}` : ""} el ${formatearFechaFiltro(lectura.datos.fecha)}, ` +
      `de ${lectura.datos.hora_inicio} a ${lectura.datos.hora_fin}. ` +
      "Una vez registradas no se pueden editar ni anular. ¿Desea continuar?",
    "advertencia"
  );
  if (!acepta) return;

  const boton = document.getElementById("btnGuardarRegistroManual");
  setBotonCargando(boton, true, "Registrando...");

  try {
    const response = await fetch(`${API_URL}/control-horas/registros-manuales`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lectura.datos)
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      if (response.status === 401) {
        manejarAccesoDenegado(response.status, data.error);
        return;
      }
      mostrarMensajeRegistroManual(data.error || "No se pudieron registrar las horas.", "error");
      return;
    }

    if (panelRegistroManual) panelRegistroManual.cerrar();
    document.getElementById("formRegistroManual").reset();
    refrescarHistorialTrasRegistro();

    const registro = data.registro || {};
    await avisarAccion(
      `${data.message || "Horas registradas manualmente."} ` +
        `Duración: ${formatearMinutos(registro.duracion_minutos)}. ` +
        `Monto: ${formatearMoneda(registro.monto)}.`,
      "exito"
    );
  } catch (error) {
    console.error(error);
    mostrarMensajeRegistroManual("No se pudo conectar con el servidor.", "error");
  } finally {
    setBotonCargando(boton, false, "Registrar horas");
    boton.disabled = tareasDisponibles.length === 0;
  }
}

// Los filtros del historial se vuelven a pedir porque el cliente o la tarea pueden no haber
// tenido registros antes; se conserva lo que la persona tenía elegido.
async function refrescarHistorialTrasRegistro() {
  const [cliente, tarea, usuario] = [filtroCliente.value, filtroTarea.value, filtroUsuario.value];
  await cargarFiltrosRegistros();
  filtroCliente.value = cliente;
  actualizarTareasFiltro();
  filtroTarea.value = tarea;
  filtroUsuario.value = usuario;
  await cargarRegistros();
}
