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

document.addEventListener("DOMContentLoaded", () => {
  const selectArea = document.getElementById("selectArea");
  const inputBuscar = document.getElementById("inputBuscar");
  const tbodyClientes = document.getElementById("tablaClientesCuerpo");

  async function cargarClientesFiltrados() {
    const idArea = selectArea.value;
    const textoBusqueda = inputBuscar.value.trim();
    const parametros = [];

    if (idArea !== "TODOS") parametros.push(`id_area=${idArea}`);
    if (textoBusqueda) parametros.push(`buscar=${encodeURIComponent(textoBusqueda)}`);

    const queryString = parametros.length > 0 ? `?${parametros.join("&")}` : "";

    tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">Consultando registros...</td></tr>`;

    try {
      const response = await fetch(`${API_URL}/clientes/filtrar${queryString}`, {
        credentials: window.API_CONFIG.credentials
      });
      const clientes = await response.json();

      if (!response.ok) {
        tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">${escapeHtml(clientes.error || "No se pudo procesar el filtro.")}</td></tr>`;
        return;
      }

      renderizarResultados(clientes);
    } catch (error) {
      console.error(error);
      tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">Error al conectar con el servidor.</td></tr>`;
    }
  }

  function renderizarResultados(clientes) {
    tbodyClientes.innerHTML = "";

    if (clientes.length === 0) {
      tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">No se encontraron clientes con los criterios seleccionados.</td></tr>`;
      return;
    }

    clientes.forEach(cliente => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td><strong>${escapeHtml(cliente.rut)}</strong></td>
        <td>${escapeHtml(cliente.razon_social)}</td>
        <td>${escapeHtml(cliente.telefono || "Sin teléfono")}</td>
        <td>
          <span class="badge estado-${escapeHtml(cliente.estado.toLowerCase())}">
            ${escapeHtml(cliente.estado)}
          </span>
        </td>
        <td>
          <a href="ficha_cliente.html?id=${encodeURIComponent(cliente.id_cliente)}" class="btn btn-primary btn-small">Ver Ficha</a>
        </td>
      `;

      tbodyClientes.appendChild(fila);
    });
  }

  selectArea.addEventListener("change", cargarClientesFiltrados);
  inputBuscar.addEventListener("input", cargarClientesFiltrados);

  cargarClientesFiltrados();
});
