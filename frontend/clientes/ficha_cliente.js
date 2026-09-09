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
    } catch (error) {
      console.error(error);
      mostrarError("Error al conectar con el servidor.");
    }
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
      tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">No se registran documentos asociados.</td></tr>`;
      return;
    }

    documentos.forEach(documento => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td>${escapeHtml(documento.nombre_documento)}</td>
        <td>${escapeHtml(documento.fecha_subida)}</td>
        <td>
          <a href="${sanitizarUrl(documento.url_archivo)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-small">Ver Archivo</a>
        </td>
      `;

      tbodyDocs.appendChild(fila);
    });
  }

  function mostrarError(texto) {
    tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">${escapeHtml(texto)}</td></tr>`;
    tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">${escapeHtml(texto)}</td></tr>`;
  }
});
