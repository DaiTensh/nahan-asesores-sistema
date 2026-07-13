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

document.addEventListener("DOMContentLoaded", async () => {
  usuarioActual = await obtenerUsuarioActual();

  if (!usuarioActual) {
    window.location.href = "../auth/login.html";
    return;
  }

  clienteBusqueda.addEventListener("input", manejarCambioCliente);
  tareaBusqueda.addEventListener("input", manejarCambioTarea);
  btnIniciar.addEventListener("click", iniciarTemporizador);
  btnDetener.addEventListener("click", detenerTemporizador);

  await cargarContexto();
  await cargarRegistros();
});

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
    const response = await fetch(`${API_URL}/control-horas/detener`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      }
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo detener el temporizador.", "error");
      return;
    }

    desactivarTemporizador({ limpiarMensaje: false });
    mostrarMensaje(data.message || "Horas registradas correctamente.", "success");

    if (data.resumen) {
      renderizarResumen(data.resumen);
    }

    await cargarRegistros();
    await cargarContexto();
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
  try {
    mostrarFilaTabla("Cargando registros...");

    const response = await fetch(`${API_URL}/control-horas/registros`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      manejarAccesoDenegado(response.status, data.error);
      return;
    }

    renderizarRegistros(data.registros || []);
    renderizarResumen(data.resumen || {});
  } catch (error) {
    console.error(error);
    mostrarFilaTabla("Error al conectar con el servidor.");
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
    agregarCelda(fila, registro.cliente);
    agregarCelda(fila, registro.tarea);
    agregarCelda(fila, registro.inicio_hora || registro.inicio);
    agregarCelda(fila, registro.fin);
    agregarCelda(fila, formatearMinutos(registro.duracion_minutos));
    agregarCelda(fila, formatearMoneda(registro.tarifa_hora));
    agregarCelda(fila, formatearMoneda(registro.monto));

    tablaRegistros.appendChild(fila);
  });
}

function mostrarFilaTabla(mensaje) {
  tablaRegistros.textContent = "";
  const fila = document.createElement("tr");
  const celda = document.createElement("td");
  celda.colSpan = 8;
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

function renderizarResumen(resumen) {
  horasHoy.textContent = formatearMinutos(resumen.minutos_hoy || 0);
  horasAcumuladas.textContent = formatearMinutos(resumen.minutos_acumulados || 0);
  montoAcumulado.textContent = formatearMoneda(resumen.monto_acumulado || 0);
  totalRegistros.textContent = String(resumen.total_registros || 0);

  renderizarTotales("totalesCliente", resumen.totales_cliente || []);
  renderizarTotales("totalesTarea", resumen.totales_tarea || []);
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

  const fecha = new Date(valor);

  if (Number.isNaN(fecha.getTime())) {
    return valor;
  }

  return fecha.toLocaleString("es-CL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
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

function manejarAccesoDenegado(estado, mensaje) {
  if (estado === 401 || estado === 403) {
    alert(mensaje || "La sesión ya no está activa.");
    window.location.href = "../auth/login.html";
    return;
  }

  mostrarMensaje(mensaje || "No se pudieron cargar los datos.", "error");
}
