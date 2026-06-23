const API_URL = "http://127.0.0.1:5000/api";

const usuarioActual = JSON.parse(localStorage.getItem("usuario"));
const selectTarea = document.getElementById("selectTarea");
const nombreCliente = document.getElementById("nombreCliente");
const temporizador = document.getElementById("temporizador");
const btnIniciar = document.getElementById("btnIniciar");
const btnDetener = document.getElementById("btnDetener");
const mensajeControl = document.getElementById("mensajeControl");
const tablaRegistros = document.getElementById("tablaRegistros");

let tareasDisponibles = [];
let temporizadorActivo = null;
let intervaloTemporizador = null;

document.addEventListener("DOMContentLoaded", async () => {
  if (!usuarioActual) return;

  await cargarContexto();
  await cargarRegistros();
});

selectTarea.addEventListener("change", () => {
  const tarea = obtenerTareaSeleccionada();
  nombreCliente.textContent = tarea ? tarea.cliente : "Seleccione una tarea";
});

btnIniciar.addEventListener("click", iniciarTemporizador);
btnDetener.addEventListener("click", detenerTemporizador);

async function cargarContexto() {
  try {
    const response = await fetch(
      `${API_URL}/control-horas/contexto?id_usuario=${usuarioActual.id_usuario}`
    );
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      manejarAccesoDenegado(response.status, data.error);
      return;
    }

    tareasDisponibles = data.tareas || [];
    renderizarTareas();

    if (data.temporizador_activo) {
      activarTemporizador(data.temporizador_activo);
    } else {
      desactivarTemporizador();
    }
  } catch (error) {
    console.error(error);
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  }
}

function renderizarTareas() {
  selectTarea.innerHTML = "";

  const opcionInicial = document.createElement("option");
  opcionInicial.value = "";
  opcionInicial.textContent = tareasDisponibles.length
    ? "Seleccione una tarea"
    : "No hay tareas disponibles";
  selectTarea.appendChild(opcionInicial);

  tareasDisponibles.forEach(tarea => {
    const opcion = document.createElement("option");
    opcion.value = tarea.id_tarea;
    opcion.textContent = `${tarea.titulo} - ${tarea.cliente}`;
    selectTarea.appendChild(opcion);
  });
}

function obtenerTareaSeleccionada() {
  return tareasDisponibles.find(
    tarea => Number(tarea.id_tarea) === Number(selectTarea.value)
  );
}

async function iniciarTemporizador() {
  const tarea = obtenerTareaSeleccionada();

  if (!tarea) {
    mostrarMensaje("Debe seleccionar una tarea.", "error");
    return;
  }

  btnIniciar.disabled = true;
  mostrarMensaje("");

  try {
    const response = await fetch(`${API_URL}/control-horas/iniciar`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        id_usuario: usuarioActual.id_usuario,
        id_tarea: tarea.id_tarea
      })
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo iniciar el temporizador.", "error");
      btnIniciar.disabled = false;

      if (response.status === 409) {
        await cargarContexto();
      }
      return;
    }

    activarTemporizador(data.temporizador_activo);
    mostrarMensaje(data.message, "success");
  } catch (error) {
    console.error(error);
    btnIniciar.disabled = false;
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  }
}

async function detenerTemporizador() {
  if (!temporizadorActivo) return;

  btnDetener.disabled = true;
  mostrarMensaje("");

  try {
    const response = await fetch(`${API_URL}/control-horas/detener`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        id_usuario: usuarioActual.id_usuario
      })
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo detener el temporizador.", "error");
      btnDetener.disabled = false;
      return;
    }

    desactivarTemporizador();
    mostrarMensaje(data.message, "success");
    await cargarRegistros();
  } catch (error) {
    console.error(error);
    btnDetener.disabled = false;
    mostrarMensaje("No se pudo conectar con el servidor.", "error");
  }
}

function activarTemporizador(datosTemporizador) {
  temporizadorActivo = datosTemporizador;

  const opcionActivaExiste = Array.from(selectTarea.options).some(
    opcion => Number(opcion.value) === Number(datosTemporizador.id_tarea)
  );

  if (!opcionActivaExiste) {
    const opcionActiva = document.createElement("option");
    opcionActiva.value = datosTemporizador.id_tarea;
    opcionActiva.textContent =
      `${datosTemporizador.tarea} - ${datosTemporizador.cliente}`;
    selectTarea.appendChild(opcionActiva);
  }

  selectTarea.value = String(datosTemporizador.id_tarea);
  nombreCliente.textContent = datosTemporizador.cliente;
  selectTarea.disabled = true;
  btnIniciar.disabled = true;
  btnDetener.disabled = false;

  actualizarTemporizador();
  clearInterval(intervaloTemporizador);
  intervaloTemporizador = setInterval(actualizarTemporizador, 1000);
}

function desactivarTemporizador() {
  temporizadorActivo = null;
  clearInterval(intervaloTemporizador);
  intervaloTemporizador = null;
  temporizador.textContent = "00h 00m 00s";
  selectTarea.disabled = false;
  selectTarea.value = "";
  nombreCliente.textContent = "Seleccione una tarea";
  btnIniciar.disabled = tareasDisponibles.length === 0;
  btnDetener.disabled = true;
}

function actualizarTemporizador() {
  if (!temporizadorActivo) return;

  const inicio = new Date(temporizadorActivo.inicio);
  const segundos = Math.max(0, Math.floor((Date.now() - inicio.getTime()) / 1000));
  temporizador.textContent = formatearDuracionSegundos(segundos);
}

async function cargarRegistros() {
  try {
    const response = await fetch(
      `${API_URL}/control-horas/registros?id_usuario=${usuarioActual.id_usuario}`
    );
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      manejarAccesoDenegado(response.status, data.error);
      return;
    }

    renderizarRegistros(data.registros || []);
    renderizarResumen(data.resumen || {});
  } catch (error) {
    console.error(error);
    tablaRegistros.innerHTML = "";
    const fila = tablaRegistros.insertRow();
    const celda = fila.insertCell();
    celda.colSpan = 8;
    celda.className = "text-loading";
    celda.textContent = "Error al conectar con el servidor.";
  }
}

function renderizarRegistros(registros) {
  tablaRegistros.innerHTML = "";

  if (registros.length === 0) {
    const fila = tablaRegistros.insertRow();
    const celda = fila.insertCell();
    celda.colSpan = 8;
    celda.className = "text-loading";
    celda.textContent = "No hay horas registradas.";
    return;
  }

  registros.forEach(registro => {
    const fila = tablaRegistros.insertRow();
    agregarCelda(fila, registro.tarea);
    agregarCelda(fila, registro.cliente);
    agregarCelda(fila, registro.inicio);
    agregarCelda(fila, registro.fin);
    agregarCelda(fila, formatearMinutos(registro.duracion_minutos));
    agregarCelda(fila, formatearMoneda(registro.tarifa_hora));
    agregarCelda(fila, formatearMoneda(registro.monto));
    agregarCelda(fila, registro.usuario_responsable);
  });
}

function agregarCelda(fila, valor) {
  const celda = fila.insertCell();
  celda.textContent = valor;
}

function renderizarResumen(resumen) {
  document.getElementById("horasAcumuladas").textContent =
    formatearMinutos(resumen.minutos_acumulados || 0);
  document.getElementById("montoAcumulado").textContent =
    formatearMoneda(resumen.monto_acumulado || 0);

  renderizarTotales("totalesCliente", resumen.totales_cliente || []);
  renderizarTotales("totalesTarea", resumen.totales_tarea || []);
}

function renderizarTotales(idContenedor, totales) {
  const contenedor = document.getElementById(idContenedor);
  contenedor.innerHTML = "";

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

function formatearDuracionSegundos(totalSegundos) {
  const horas = Math.floor(totalSegundos / 3600);
  const minutos = Math.floor((totalSegundos % 3600) / 60);
  const segundos = totalSegundos % 60;

  return `${rellenar(horas)}h ${rellenar(minutos)}m ${rellenar(segundos)}s`;
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
  if (estado === 403) {
    localStorage.removeItem("usuario");
    alert(mensaje || "La sesión ya no está activa.");
    window.location.href = "../auth/login.html";
    return;
  }

  mostrarMensaje(mensaje || "No se pudieron cargar los datos.", "error");
}
