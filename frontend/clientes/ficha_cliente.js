const API_URL = "http://127.0.0.1:5000/api";

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
      const response = await fetch(`${API_URL}/clientes/${idCliente}/ficha`);
      const data = await response.json();

      if (!response.ok) {
        mostrarError(data.error || "No fue posible cargar la ficha del cliente.");
        return;
      }

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
        <td><strong>${tarea.titulo}</strong></td>
        <td>${tarea.nombre_area}</td>
        <td>${tarea.fecha_vencimiento || "Sin fecha"}</td>
        <td>${tarea.estado}</td>
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
        <td>${documento.nombre_documento}</td>
        <td>${documento.fecha_subida}</td>
        <td>
          <a href="${documento.url_archivo}" target="_blank" class="btn btn-secondary btn-small">Ver Archivo</a>
        </td>
      `;

      tbodyDocs.appendChild(fila);
    });
  }

  function mostrarError(texto) {
    tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">${texto}</td></tr>`;
    tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">${texto}</td></tr>`;
  }
});
