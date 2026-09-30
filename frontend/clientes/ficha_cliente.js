const API_URL = window.API_CONFIG.API_URL;

function escapeHtml(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (caracter) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  }[caracter]));
}

function sanitizarUrl(url) {
  const valor = String(url || "").trim();
  if (/^https?:\/\//i.test(valor) || valor.startsWith("/")) {
    return escapeHtml(valor);
  }
  return "#";
}

document.addEventListener("DOMContentLoaded", () => {
  const tbodyTareas = document.getElementById("tablaTareasCuerpo");
  const tbodyDocs = document.getElementById("tablaDocumentoCuerpo");
  const parametrosUrl = new URLSearchParams(window.location.search);
  const idCliente = parametrosUrl.get("id");

  cargarFichaCliente();

  async function cargarFichaCliente() {
    if (!idCliente) {
      mostrarError("No se recibió un cliente válido desde el listado.");
      return;
    }

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/ficha`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();

      if (!response.ok) {
        mostrarError(data.error || "No fue posible cargar la ficha del cliente.");
        return;
      }

      document.getElementById("resumenEstado").textContent = escapeHtml(data.estado);
      document.getElementById("resumenArea").textContent = escapeHtml(data.areas_nombres || "Sin área asignada");
      document.getElementById("resumenTareasActivas").textContent = escapeHtml(data.tareas_activas ?? 0);

      document.getElementById("fichaRut").textContent = data.rut;
      document.getElementById("fichaRazonSocial").textContent = data.razon_social;
      document.getElementById("fichaDireccion").textContent = data.direccion || "No registrada";
      document.getElementById("fichaTelefono").textContent = data.telefono || "No registrado";
      document.getElementById("fichaEmail").textContent = data.email || "No registrado";
      document.getElementById("fichaAreas").textContent = data.areas_nombres || "Sin área asignada";

      renderizarTareas(data.tareas || []);
      renderizarDocumentos(data.documentos || []);
      cargarObservaciones();
      cargarHistorial();
    } catch (error) {
      console.error(error);
      mostrarError("Error al conectar con el servidor.");
    }
  }

  const seccionObservaciones = document.getElementById("seccionObservaciones");
  const tbodyObs = document.getElementById("tablaObservacionesCuerpo");
  const formObservacion = document.getElementById("formObservacionCliente");
  const mensajeObs = document.getElementById("mensajeObsFeedback");

  async function cargarObservaciones() {
    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/observaciones`, {
        credentials: window.API_CONFIG.credentials
      });

      // La sección solo se despliega si el backend confirma el acceso: un
      // usuario sin permiso (401/403) nunca ve ni el formulario ni la tabla.
      if (!response.ok) {
        seccionObservaciones.hidden = true;
        return;
      }

      const data = await response.json();
      seccionObservaciones.hidden = false;
      renderizarObservaciones(data.observaciones || []);
    } catch (error) {
      console.error(error);
      seccionObservaciones.hidden = true;
    }
  }

  function renderizarObservaciones(observaciones) {
    tbodyObs.innerHTML = "";

    if (observaciones.length === 0) {
      tbodyObs.innerHTML = `<tr><td colspan="3" class="text-loading">No se registran observaciones para este cliente.</td></tr>`;
      return;
    }

    observaciones.forEach(observacion => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td>${escapeHtml(observacion.fecha)}</td>
        <td>${escapeHtml(observacion.registrado_por)}</td>
        <td>${escapeHtml(observacion.texto)}</td>
      `;

      tbodyObs.appendChild(fila);
    });
  }

  formObservacion.addEventListener("submit", async (event) => {
    event.preventDefault();

    const boton = formObservacion.querySelector('button[type="submit"]');

    if (boton.disabled) {
      return;
    }

    const texto = document.getElementById("obsTexto").value.trim();

    if (!texto) {
      mostrarMensajeObs("El texto de la observación es obligatorio.", "error");
      return;
    }

    boton.disabled = true;
    const textoOriginal = boton.textContent;
    boton.textContent = "Registrando...";

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/observaciones`, {
        method: "POST",
        credentials: window.API_CONFIG.credentials,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ texto })
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensajeObs(data.error || "No se pudo registrar la observación.", "error");
        return;
      }

      mostrarMensajeObs(data.message || "Observación registrada correctamente.", "success");
      formObservacion.reset();
      cargarObservaciones();
      cargarHistorial();
    } catch (error) {
      console.error(error);
      mostrarMensajeObs("No se pudo contactar la API. Verifique que el servidor esté disponible.", "error");
    } finally {
      boton.disabled = false;
      boton.textContent = textoOriginal;
    }
  });

  function mostrarMensajeObs(texto, tipo) {
    mensajeObs.textContent = texto;
    mensajeObs.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }

  function renderizarTareas(tareas) {
    tbodyTareas.innerHTML = "";

    if (tareas.length === 0) {
      tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">No existen gestiones registradas para este cliente.</td></tr>`;
      return;
    }

    tareas.forEach(tarea => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td><strong>${escapeHtml(tarea.titulo)}</strong></td>
        <td>${escapeHtml(tarea.nombre_area)}</td>
        <td>${escapeHtml(tarea.fecha_vencimiento || "Sin fecha")}</td>
        <td>${escapeHtml(tarea.estado)}</td>
      `;

      tbodyTareas.appendChild(fila);
    });
  }

  function renderizarDocumentos(documentos) {
    tbodyDocs.innerHTML = "";

    if (documentos.length === 0) {
      tbodyDocs.innerHTML = `<tr><td colspan="4" class="text-loading">No se registran documentos asociados.</td></tr>`;
      return;
    }

    documentos.forEach(documento => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td>${escapeHtml(documento.nombre_documento)}</td>
        <td>${escapeHtml(documento.tipo_documento)}</td>
        <td>${escapeHtml(documento.fecha_subida)}</td>
        <td>${escapeHtml(documento.descripcion || "-")}</td>
      `;

      tbodyDocs.appendChild(fila);
    });
  }

  function mostrarError(texto) {
    tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">${escapeHtml(texto)}</td></tr>`;
    tbodyDocs.innerHTML = `<tr><td colspan="4" class="text-loading">${escapeHtml(texto)}</td></tr>`;
  }

  const formDocumento = document.getElementById("formReferenciaDocumento");
  const mensajeDoc = document.getElementById("mensajeDocFeedback");

  formDocumento.addEventListener("submit", async (event) => {
    event.preventDefault();

    const boton = formDocumento.querySelector('button[type="submit"]');

    if (boton.disabled) {
      return;
    }

    const payload = {
      nombre_documento: document.getElementById("docNombre").value.trim(),
      tipo_documento: document.getElementById("docTipo").value.trim(),
      ubicacion_referencia: document.getElementById("docUbicacion").value.trim(),
      observaciones: document.getElementById("docObservaciones").value.trim()
    };

    boton.disabled = true;
    const textoOriginal = boton.textContent;
    boton.textContent = "Registrando...";

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/documentos`, {
        method: "POST",
        credentials: window.API_CONFIG.credentials,
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensajeDoc(data.error || "No se pudo registrar la referencia.", "error");
        return;
      }

      mostrarMensajeDoc(data.message || "Referencia registrada correctamente.", "success");
      formDocumento.reset();
      cargarFichaCliente();
    } catch (error) {
      console.error(error);
      mostrarMensajeDoc("No se pudo contactar la API. Verifique que el servidor esté disponible.", "error");
    } finally {
      boton.disabled = false;
      boton.textContent = textoOriginal;
    }
  });

  function mostrarMensajeDoc(texto, tipo) {
    mensajeDoc.textContent = texto;
    mensajeDoc.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }

  // RF13 — Historial completo del cliente. Solo lectura: la sección consulta
  // GET /clientes/<id>/historial-completo y no ofrece edición ni borrado.
  const HISTORIAL_POR_PAGINA = 20;
  const ETIQUETAS_ACCION_HISTORIAL = {
    CLIENTE_CREADO: "Cliente creado",
    CLIENTE_MODIFICADO: "Datos del cliente modificados",
    CAMBIO_ESTADO: "Cambio de estado del cliente",
    DESHABILITAR: "Cliente deshabilitado",
    OBSERVACION_CREADA: "Observación registrada",
    TAREA_CREADA: "Tarea creada",
    EDICION: "Tarea editada",
    CAMBIO_ESTADO_TAREA: "Cambio de estado de la tarea",
    REASIGNACION: "Tarea reasignada",
    REASIGNACION_MASIVA: "Tarea reasignada (masivo)",
    ENVIO_REVISION: "Tarea enviada a revisión",
    APROBAR_REVISION: "Revisión aprobada",
    RECHAZAR_REVISION: "Revisión rechazada",
    COMPLETAR_TAREA: "Tarea completada",
    CANCELAR_TAREA: "Tarea cancelada",
    DOCUMENTO_REFERENCIADO: "Documento referenciado",
    DOCUMENTO_ADJUNTADO: "Documento adjuntado",
    DESCARGA: "Documento descargado"
  };

  const seccionHistorial = document.getElementById("seccionHistorial");
  const tbodyHistorial = document.getElementById("tablaHistorialCuerpo");
  const formHistorial = document.getElementById("formHistorialCliente");
  const selectAccionHistorial = document.getElementById("historialAccion");
  const mensajeHistorial = document.getElementById("mensajeHistorialFeedback");
  const btnHistorialAnterior = document.getElementById("btnHistorialAnterior");
  const btnHistorialSiguiente = document.getElementById("btnHistorialSiguiente");
  let paginaHistorial = 1;
  let totalPaginasHistorial = 1;

  function etiquetaAccionHistorial(accion) {
    if (ETIQUETAS_ACCION_HISTORIAL[accion]) return ETIQUETAS_ACCION_HISTORIAL[accion];
    const texto = String(accion || "").replace(/_/g, " ").toLowerCase();
    return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "-";
  }

  function formatearFechaHistorial(fecha) {
    const partes = String(fecha || "").split("-");
    return partes.length === 3 ? `${partes[2]}-${partes[1]}-${partes[0]}` : (fecha || "-");
  }

  function mostrarMensajeHistorial(texto) {
    mensajeHistorial.textContent = texto || "";
    mensajeHistorial.className = texto ? "mensaje error" : "mensaje";
  }

  function filaMensajeHistorial(texto) {
    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 5;
    celda.className = "text-loading";
    celda.textContent = texto;
    fila.appendChild(celda);
    tbodyHistorial.replaceChildren(fila);
  }

  function celdaHistorial(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto || "-";
    return celda;
  }

  function celdaDetalleHistorial(evento) {
    const celda = document.createElement("td");
    const partes = [];
    if (evento.datos_anteriores) partes.push(["Antes", evento.datos_anteriores]);
    if (evento.datos_nuevos) partes.push(["Después", evento.datos_nuevos]);

    partes.forEach(([etiqueta, valor], indice) => {
      if (indice) celda.appendChild(document.createElement("br"));
      const titulo = document.createElement("strong");
      titulo.textContent = `${etiqueta}: `;
      celda.appendChild(titulo);
      celda.appendChild(document.createTextNode(valor));
    });

    if (evento.tabla_afectada === "tarea" && /^\d+$/.test(String(evento.id_registro ?? ""))) {
      if (partes.length) celda.appendChild(document.createElement("br"));
      const enlace = document.createElement("a");
      enlace.href = `../tareas/detalle_tarea.html?id=${encodeURIComponent(evento.id_registro)}`;
      enlace.textContent = "Ver tarea";
      celda.appendChild(enlace);
    } else if (!partes.length) {
      celda.textContent = "-";
    }

    return celda;
  }

  function actualizarAccionesHistorial(acciones) {
    const seleccion = selectAccionHistorial.value;
    const opciones = [new Option("Todas las acciones", "")];
    acciones.forEach(accion => opciones.push(new Option(etiquetaAccionHistorial(accion), accion)));
    selectAccionHistorial.replaceChildren(...opciones);
    selectAccionHistorial.value = acciones.includes(seleccion) ? seleccion : "";
  }

  function actualizarPaginacionHistorial(total) {
    totalPaginasHistorial = Math.max(1, Math.ceil(total / HISTORIAL_POR_PAGINA));
    document.getElementById("txtHistorialPagina").textContent =
      `Página ${paginaHistorial} de ${totalPaginasHistorial} · ${total} evento(s)`;
    btnHistorialAnterior.disabled = paginaHistorial <= 1;
    btnHistorialSiguiente.disabled = paginaHistorial >= totalPaginasHistorial;
  }

  async function cargarHistorial() {
    const inicio = document.getElementById("historialFechaInicio").value;
    const fin = document.getElementById("historialFechaFin").value;

    if (inicio && fin && inicio > fin) {
      mostrarMensajeHistorial("La fecha de inicio no puede ser posterior a la fecha de término.");
      return;
    }

    const parametros = new URLSearchParams({
      limite: HISTORIAL_POR_PAGINA,
      offset: (paginaHistorial - 1) * HISTORIAL_POR_PAGINA
    });
    if (selectAccionHistorial.value) parametros.set("accion", selectAccionHistorial.value);
    if (inicio) parametros.set("fecha_inicio", inicio);
    if (fin) parametros.set("fecha_fin", fin);

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}/historial-completo?${parametros}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json().catch(() => ({}));

      // Igual que en observaciones: sin acceso (401/403) la sección no se muestra.
      if (response.status === 401 || response.status === 403) {
        seccionHistorial.hidden = true;
        return;
      }

      seccionHistorial.hidden = false;

      if (!response.ok) {
        mostrarMensajeHistorial(data.error || "No fue posible cargar el historial.");
        return;
      }

      mostrarMensajeHistorial("");
      actualizarAccionesHistorial(data.acciones_disponibles || []);
      actualizarPaginacionHistorial(data.total || 0);

      const eventos = data.historial || [];
      if (!eventos.length) {
        filaMensajeHistorial("No se registran eventos para los filtros seleccionados.");
        return;
      }

      tbodyHistorial.replaceChildren(...eventos.map(evento => {
        const fila = document.createElement("tr");
        fila.appendChild(celdaHistorial(formatearFechaHistorial(evento.fecha)));
        fila.appendChild(celdaHistorial(String(evento.hora || "").substring(0, 5)));
        fila.appendChild(celdaHistorial(evento.usuario));
        fila.appendChild(celdaHistorial(etiquetaAccionHistorial(evento.accion)));
        fila.appendChild(celdaDetalleHistorial(evento));
        return fila;
      }));
    } catch (error) {
      console.error(error);
      seccionHistorial.hidden = false;
      mostrarMensajeHistorial("No fue posible conectar con el servidor.");
    }
  }

  formHistorial.addEventListener("submit", event => {
    event.preventDefault();
    paginaHistorial = 1;
    cargarHistorial();
  });

  document.getElementById("btnLimpiarHistorial").addEventListener("click", () => {
    formHistorial.reset();
    paginaHistorial = 1;
    cargarHistorial();
  });

  btnHistorialAnterior.addEventListener("click", () => {
    if (paginaHistorial > 1) {
      paginaHistorial -= 1;
      cargarHistorial();
    }
  });

  btnHistorialSiguiente.addEventListener("click", () => {
    if (paginaHistorial < totalPaginasHistorial) {
      paginaHistorial += 1;
      cargarHistorial();
    }
  });
});
