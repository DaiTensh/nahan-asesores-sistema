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
});
