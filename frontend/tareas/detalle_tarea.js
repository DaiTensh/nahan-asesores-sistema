const API_URL = window.API_CONFIG.API_URL;

const ESTADOS_TEXTO = {
  PENDIENTE: "Pendiente",
  EN_PROCESO: "En proceso",
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
    fila.appendChild(crearCelda(evento.accion));
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
      alert(data.error || "No se pudo descargar el archivo");
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
    alert("Error al conectar con el servidor");
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

  return new Date(fecha).toLocaleString("es-CL", { timeZone: "UTC" });
}
