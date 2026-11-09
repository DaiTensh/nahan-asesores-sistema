const API_URL = window.API_CONFIG.API_URL;

const ESTADOS_TEXTO = {
  PENDIENTE: "Pendiente",
  EN_PROCESO: "En proceso",
  PAUSADA: "Pausada",
  EN_REVISION: "En revisión",
  COMPLETADA: "Completada",
  CANCELADA: "Cancelada"
};

const PRIORIDADES_TEXTO = {
  BAJA: "Baja",
  MEDIA: "Media",
  ALTA: "Alta",
  URGENTE: "Urgente"
};

const ESTADOS_FINALES = ["COMPLETADA", "CANCELADA"];

document.addEventListener("DOMContentLoaded", () => {
  const idTarea = new URLSearchParams(window.location.search).get("id");

  if (!idTarea) {
    mostrarMensaje("No se recibió una tarea válida desde el listado.", "error");
    return;
  }

  cargarDetalle(idTarea);
});

async function cargarDetalle(idTarea) {
  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}`, {
      credentials: window.API_CONFIG.credentials
    });
    const tarea = await response.json();

    if (response.status === 401) {
      window.location.href = "../auth/login.html";
      return;
    }

    if (!response.ok) {
      mostrarMensaje(tarea.error || "No fue posible cargar la tarea.", "error");
      return;
    }

    document.getElementById("detalleTitulo").textContent = tarea.titulo;

    document.getElementById("detalleCliente").textContent = tarea.cliente;
    document.getElementById("detalleArea").textContent = tarea.area;
    document.getElementById("detalleResponsable").textContent = tarea.responsable;
    document.getElementById("detalleCreador").textContent = tarea.creador;
    document.getElementById("detalleEstado").textContent = ESTADOS_TEXTO[tarea.estado] || tarea.estado;
    document.getElementById("detallePrioridad").textContent = PRIORIDADES_TEXTO[tarea.prioridad] || tarea.prioridad;
    document.getElementById("detalleFechaCreacion").textContent = formatearFechaHora(tarea.fecha_creacion);
    document.getElementById("detalleFechaInicio").textContent = formatearFecha(tarea.fecha_inicio);
    document.getElementById("detalleFechaVencimiento").textContent = formatearFecha(tarea.fecha_vencimiento);
    document.getElementById("detalleFechaFinalizacion").textContent = formatearFechaHora(tarea.fecha_finalizacion);
    document.getElementById("detalleDescripcion").textContent = tarea.descripcion || "Sin descripción";

    document.getElementById("detalleContenido").hidden = false;

    if (!ESTADOS_FINALES.includes(tarea.estado)) {
      const enlaceEditar = document.getElementById("enlaceEditar");
      enlaceEditar.href = `editar_tarea.html?id=${idTarea}`;
      enlaceEditar.hidden = false;
    }

    await configurarAccionesRevision(tarea);
    renderizarHistorial(tarea.historial || []);
    await cargarAdjuntos(idTarea);
    await cargarHoras(tarea);

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor.", "error");
  }
}

async function configurarAccionesRevision(tarea) {
  const seccion = document.getElementById("seccionAccionesRevision");
  const btnEnviar = document.getElementById("btnEnviarRevision");
  const btnAprobar = document.getElementById("btnAprobarRevision");
  const btnRechazar = document.getElementById("btnRechazarRevision");
  const contenedorRechazo = document.getElementById("contenedorObservacionRechazo");
  const observacion = document.getElementById("observacionRechazo");
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    seccion.hidden = true;
    return;
  }

  const esResponsable = Number(usuario.id_usuario) === Number(tarea.id_responsable);
  const esAdmin = usuario.nombre_rol === "ADMINISTRADOR";
  const puedeEnviar = !ESTADOS_FINALES.includes(tarea.estado) && tarea.estado !== "EN_REVISION" && (esResponsable || esAdmin);
  const puedeAprobar = esAdmin && tarea.estado === "EN_REVISION";
  const puedeRechazar = esAdmin && tarea.estado === "EN_REVISION";

  btnEnviar.hidden = !puedeEnviar;
  btnAprobar.hidden = !puedeAprobar;
  btnRechazar.hidden = !puedeRechazar;
  contenedorRechazo.hidden = true;
  observacion.value = "";

  seccion.hidden = !(puedeEnviar || puedeAprobar || puedeRechazar);

  if (puedeEnviar) {
    btnEnviar.onclick = async () => {
      const respuesta = await fetch(`${API_URL}/tareas/${tarea.id_tarea}/estado`, {
        method: "PUT",
        credentials: window.API_CONFIG.credentials,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ estado: "EN_REVISION" })
      });
      const data = await respuesta.json().catch(() => ({}));

      if (!respuesta.ok) {
        mostrarMensaje(data.error || "No se pudo enviar la tarea a revisión.", "error");
        return;
      }

      mostrarMensaje(data.message || "Tarea enviada a revisión.", "success");
      window.location.reload();
    };
  }

  if (puedeAprobar) {
    btnAprobar.onclick = async () => {
      const respuesta = await fetch(`${API_URL}/tareas/${tarea.id_tarea}/revision`, {
        method: "PUT",
        credentials: window.API_CONFIG.credentials,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accion: "aprobar" })
      });
      const data = await respuesta.json().catch(() => ({}));

      if (!respuesta.ok) {
        mostrarMensaje(data.error || "No se pudo aprobar la tarea.", "error");
        return;
      }

      mostrarMensaje(data.message || "Tarea aprobada.", "success");
      window.location.reload();
    };
  }

  if (puedeRechazar) {
    btnRechazar.onclick = () => {
      contenedorRechazo.hidden = false;
      observacion.focus();
    };

    document.getElementById("btnConfirmarRechazo").onclick = async () => {
      const descripcion = observacion.value.trim();
      if (!descripcion) {
        mostrarMensaje("Debe indicar las observaciones del rechazo.", "error");
        return;
      }

      const respuesta = await fetch(`${API_URL}/tareas/${tarea.id_tarea}/revision`, {
        method: "PUT",
        credentials: window.API_CONFIG.credentials,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accion: "rechazar", observaciones: descripcion })
      });
      const data = await respuesta.json().catch(() => ({}));

      if (!respuesta.ok) {
        mostrarMensaje(data.error || "No se pudo rechazar la tarea.", "error");
        return;
      }

      mostrarMensaje(data.message || "La tarea fue rechazada.", "success");
      window.location.reload();
    };
  }
}

function renderizarHistorial(historial) {
  const seccion = document.getElementById("seccionHistorial");
  const tabla = document.getElementById("tablaHistorial");
  tabla.textContent = "";

  seccion.hidden = false;

  if (historial.length === 0) {
    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 5;
    celda.textContent = "Esta tarea todavía no registra cambios.";
    fila.appendChild(celda);
    tabla.appendChild(fila);
    return;
  }

  historial.forEach(evento => {
    const fila = document.createElement("tr");

    fila.appendChild(crearCelda(formatearFechaHora(evento.fecha)));
    fila.appendChild(crearCelda(evento.usuario));
    fila.appendChild(crearCelda(window.etiquetaAccionAuditoria(evento.accion)));
    fila.appendChild(crearCelda(evento.datos_anteriores));
    fila.appendChild(crearCelda(evento.datos_nuevos));

    tabla.appendChild(fila);
  });
}

function crearCelda(valor) {
  const celda = document.createElement("td");
  celda.textContent = valor ?? "";
  return celda;
}

async function cargarAdjuntos(idTarea) {
  const seccion = document.getElementById("seccionAdjuntos");
  const lista = document.getElementById("detalleAdjuntos");
  lista.textContent = "";
  seccion.hidden = false;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/documentos`, {
      credentials: window.API_CONFIG.credentials
    });
    const documentos = await response.json();

    if (!response.ok) {
      const item = document.createElement("li");
      item.textContent = documentos.error || "No se pudieron cargar los adjuntos.";
      lista.appendChild(item);
      return;
    }

    if (documentos.length === 0) {
      const item = document.createElement("li");
      item.textContent = "Esta tarea todavía no tiene archivos adjuntos.";
      lista.appendChild(item);
      return;
    }

    documentos.forEach(documento => {
      lista.appendChild(crearItemAdjunto(documento));
    });

  } catch (error) {
    console.error(error);
    const item = document.createElement("li");
    item.textContent = "Error al conectar con el servidor.";
    lista.appendChild(item);
  }
}

function crearItemAdjunto(documento) {
  const item = document.createElement("li");
  item.className = "adjuntos-item";

  const nombre = document.createElement("span");
  nombre.className = "nombre";
  nombre.textContent = documento.nombre_documento;
  item.appendChild(nombre);

  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = `subido por ${documento.subido_por} — ${formatearFechaHora(documento.fecha_subida)}`;
  item.appendChild(meta);

  const botonDescargar = document.createElement("button");
  botonDescargar.type = "button";
  botonDescargar.className = "btn btn-secondary btn-small";
  botonDescargar.textContent = "Descargar";
  botonDescargar.addEventListener("click", () => descargarAdjunto(documento.id_documento, documento.nombre_documento));
  item.appendChild(botonDescargar);

  return item;
}

async function descargarAdjunto(idDocumento, nombreDocumento) {
  try {
    const response = await fetch(`${API_URL}/documentos/${idDocumento}/descargar`, {
      credentials: window.API_CONFIG.credentials
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      avisarAccion(data.error || "No se pudo descargar el archivo", "error");
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombreDocumento;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    window.URL.revokeObjectURL(url);

  } catch (error) {
    console.error(error);
    avisarAccion("Error al conectar con el servidor", "error");
  }
}

function mostrarMensaje(texto, tipo) {
  const mensaje = document.getElementById("detalleMensaje");
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

// La API entrega DATE y DATETIME de MySQL (hora local del servidor, sin
// zona) serializados como "... GMT". Se muestran en UTC para conservar el
// valor guardado: convertirlos a la zona del navegador restaba un día a los
// vencimientos y 3 horas a las fechas con hora.
function formatearFecha(fecha) {
  if (!fecha) {
    return "Sin fecha";
  }

  return new Date(fecha).toLocaleDateString("es-CL", { timeZone: "UTC" });
}

function formatearFechaHora(fecha) {
  if (!fecha) {
    return "Sin registrar";
  }

  return formatearFechaHora24(fecha, { utc: true });
}

// ---------------------------------------------------------------------------
// Horas trabajadas en la tarea (RF71 «iniciar el temporizador desde la vista detalle de la tarea»,
// RF72/RF73 historial y total por tarea, CU-14 y CU-29 «registrar tiempo desde el detalle»).
// Solo reutiliza los endpoints de Control de horas: el servidor decide quién puede registrar y
// qué horas ve cada rol (un usuario de área ve solo las suyas; el administrador, las de todos).
// ---------------------------------------------------------------------------
const HORAS_FILAS_MAXIMAS = 10;
const URL_CONTROL_HORAS = "../control_horas/control_horas.html";

function formatearMinutosTarea(totalMinutos) {
  const minutos = Math.round(Number(totalMinutos) || 0);
  const relleno = numero => String(numero).padStart(2, "0");
  return `${relleno(Math.floor(minutos / 60))}h ${relleno(minutos % 60)}m`;
}

function formatearMontoTarea(valor) {
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0
  }).format(Number(valor) || 0);
}

function mostrarMensajeHoras(texto, tipo = "") {
  const mensaje = document.getElementById("horasMensaje");
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

async function cargarHoras(tarea) {
  const seccion = document.getElementById("seccionHoras");
  // La sección es opcional: con un HTML anterior en caché no existe y el resto del detalle sigue igual.
  if (!seccion) return;

  try {
    const usuario = await obtenerUsuarioActual();
    if (!usuario) return;

    const idTarea = Number(tarea.id_tarea);
    const esAdministrador = usuario.nombre_rol === "ADMINISTRADOR";
    const opciones = { credentials: window.API_CONFIG.credentials };
    const [respuestaRegistros, respuestaContexto] = await Promise.all([
      fetch(`${API_URL}/control-horas/registros?id_tarea=${idTarea}`, opciones),
      fetch(`${API_URL}/control-horas/contexto`, opciones)
    ]);

    seccion.hidden = false;
    document.getElementById("horasAlcance").textContent = esAdministrador
      ? "Horas registradas por todos los usuarios en esta tarea."
      : "Sus horas registradas en esta tarea.";
    document.getElementById("thUsuarioHoras").hidden = !esAdministrador;
    document.getElementById("enlaceControlHorasTarea").href = `${URL_CONTROL_HORAS}?id_tarea=${idTarea}`;

    if (respuestaRegistros.ok) {
      const datos = await respuestaRegistros.json();
      renderizarHoras(datos.registros || [], datos.resumen || {}, esAdministrador);
    } else {
      const datos = await respuestaRegistros.json().catch(() => ({}));
      mostrarMensajeHoras(datos.error || "No se pudieron cargar las horas de la tarea.", "error");
    }

    const contexto = respuestaContexto.ok ? await respuestaContexto.json().catch(() => null) : null;
    configurarAccionesHoras(idTarea, contexto);
  } catch (error) {
    console.error(error);
    seccion.hidden = false;
    mostrarMensajeHoras("No se pudieron cargar las horas de la tarea.", "error");
  }
}

function renderizarHoras(registros, resumen, esAdministrador) {
  document.getElementById("horasTotalTarea").textContent = formatearMinutosTarea(resumen.minutos_acumulados);
  document.getElementById("horasMontoTarea").textContent = formatearMontoTarea(resumen.monto_acumulado);
  document.getElementById("horasRegistrosTarea").textContent = String(resumen.total_registros || 0);

  const cuerpo = document.getElementById("tablaHorasTarea");
  cuerpo.textContent = "";

  if (registros.length === 0) {
    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = esAdministrador ? 7 : 6;
    celda.className = "text-loading";
    celda.textContent = "Todavía no hay horas registradas en esta tarea.";
    fila.appendChild(celda);
    cuerpo.appendChild(fila);
  }

  registros.slice(0, HORAS_FILAS_MAXIMAS).forEach(registro => {
    const fila = document.createElement("tr");
    fila.appendChild(crearCelda(registro.fecha));
    if (esAdministrador) fila.appendChild(crearCelda(registro.usuario_responsable));
    fila.appendChild(crearCelda(registro.inicio_hora));
    fila.appendChild(crearCelda(registro.fin));
    fila.appendChild(crearCelda(formatearMinutosTarea(registro.duracion_minutos)));
    fila.appendChild(crearCelda(formatearMontoTarea(registro.monto)));

    const celdaOrigen = document.createElement("td");
    const manual = registro.origen === "MANUAL";
    const insignia = document.createElement("span");
    insignia.className = manual ? "badge badge-info" : "badge badge-pending";
    insignia.textContent = manual ? "Manual" : "Temporizador";
    celdaOrigen.appendChild(insignia);
    if (manual && registro.observacion) {
      const observacion = document.createElement("small");
      observacion.className = "horas-origen-observacion";
      observacion.textContent = registro.observacion;
      celdaOrigen.appendChild(observacion);
    }
    fila.appendChild(celdaOrigen);
    cuerpo.appendChild(fila);
  });

  document.getElementById("horasNota").textContent = registros.length > HORAS_FILAS_MAXIMAS
    ? `Se muestran los ${HORAS_FILAS_MAXIMAS} registros más recientes de ${registros.length}. ` +
      "El total incluye todos; el historial completo está en Control de horas."
    : "";
}

function configurarAccionesHoras(idTarea, contexto) {
  const botonIniciar = document.getElementById("btnIniciarTemporizadorTarea");
  const enlaceManual = document.getElementById("enlaceRegistroManualTarea");
  const estado = document.getElementById("horasEstadoTemporizador");
  const activo = contexto ? contexto.temporizador_activo : null;
  const habilitada = Boolean(contexto) &&
    (contexto.tareas || []).some(t => Number(t.id_tarea) === idTarea);

  botonIniciar.hidden = true;
  botonIniciar.disabled = false;
  enlaceManual.hidden = !habilitada;
  enlaceManual.href = `${URL_CONTROL_HORAS}?id_tarea=${idTarea}&registrar=manual`;
  estado.textContent = "";

  if (!contexto) {
    estado.textContent = "No se pudo comprobar si puede registrar horas en esta tarea.";
    return;
  }

  if (activo && Number(activo.id_tarea) === idTarea) {
    estado.textContent =
      // El inicio llega como hora local sin zona («2026-11-05T13:01:05»): se muestra sin convertir a UTC.
      `Tiene un temporizador en curso en esta tarea desde ${formatearFechaHora24(activo.inicio)}. ` +
      "Deténgalo desde Control de horas.";
    return;
  }

  if (!habilitada) {
    estado.textContent =
      "No se pueden registrar horas en esta tarea: está finalizada, su cliente está inactivo o no está asignada a usted.";
    return;
  }

  botonIniciar.hidden = false;

  if (activo) {
    botonIniciar.disabled = true;
    estado.textContent =
      `Ya tiene un temporizador en curso en «${activo.tarea}». Deténgalo en Control de horas para iniciar otro.`;
    return;
  }

  botonIniciar.onclick = () => iniciarTemporizadorDesdeDetalle(idTarea, botonIniciar);
}

async function iniciarTemporizadorDesdeDetalle(idTarea, boton) {
  boton.disabled = true;
  boton.textContent = "Iniciando...";
  mostrarMensajeHoras("");

  try {
    const response = await fetch(`${API_URL}/control-horas/iniciar`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_tarea: idTarea })
    });
    const datos = await response.json().catch(() => ({}));

    if (!response.ok) {
      mostrarMensajeHoras(datos.error || "No se pudo iniciar el temporizador.", "error");
      boton.disabled = false;
      boton.textContent = "Iniciar temporizador";
      return;
    }

    // El temporizador queda corriendo en Control de horas, donde también se detiene.
    window.location.href = URL_CONTROL_HORAS;
  } catch (error) {
    console.error(error);
    mostrarMensajeHoras("No se pudo conectar con el servidor.", "error");
    boton.disabled = false;
    boton.textContent = "Iniciar temporizador";
  }
}
