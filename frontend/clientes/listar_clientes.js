const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  const selectAreaFiltro = document.getElementById("selectAreaFiltro");
  const inputBuscarTexto = document.getElementById("inputBuscarTexto");
  const tbody = document.getElementById("tablaClientesGeneralCuerpo");
  const btnAnterior = document.getElementById("btnPaginaAnterior");
  const btnSiguiente = document.getElementById("btnPaginaSiguiente");
  const txtIndicador = document.getElementById("txtIndicadorPagina");

  let paginaActual = 1;
  const limiteRegistros = 7;

  async function cargarListadoGeneral() {
    tbody.innerHTML = `<tr><td colspan="5" class="text-loading">Cargando clientes...</td></tr>`;

    const idArea = selectAreaFiltro.value;
    const textoBuscar = inputBuscarTexto.value.trim();
    const queryParams = [`pagina=${paginaActual}`, `limite=${limiteRegistros}`];

    if (idArea !== "TODOS") queryParams.push(`id_area=${idArea}`);
    if (textoBuscar) queryParams.push(`buscar=${encodeURIComponent(textoBuscar)}`);

    try {
      const response = await fetch(`${API_URL}/clientes/listado?${queryParams.join("&")}`);
      const data = await leerRespuestaJson(response);

      if (!response.ok) {
        await cargarListadoSimple(idArea, textoBuscar, data.error);
        return;
      }

      const clientes = Array.isArray(data) ? data : data.clientes;
      renderizarClientes(clientes || []);
    } catch (error) {
      console.error(error);
      await cargarListadoSimple(idArea, textoBuscar);
    }
  }

  async function cargarListadoSimple(idArea, textoBuscar, errorOriginal = "") {
    const parametros = [];

    if (idArea !== "TODOS") parametros.push(`id_area=${idArea}`);
    if (textoBuscar) parametros.push(`buscar=${encodeURIComponent(textoBuscar)}`);

    const queryString = parametros.length > 0 ? `?${parametros.join("&")}` : "";

    try {
      const response = await fetch(`${API_URL}/clientes/filtrar${queryString}`);
      const clientes = await leerRespuestaJson(response);

      if (!response.ok) {
        const mensaje = clientes.error || errorOriginal || "No se pudo cargar el listado de clientes.";
        tbody.innerHTML = `<tr><td colspan="5" class="text-loading">${mensaje}</td></tr>`;
        return;
      }

      renderizarClientes(Array.isArray(clientes) ? clientes : []);
      btnAnterior.disabled = true;
      btnSiguiente.disabled = true;
      txtIndicador.textContent = "Listado";
    } catch (error) {
      console.error(error);
      tbody.innerHTML = `<tr><td colspan="5" class="text-loading">Error al conectar con el servidor.</td></tr>`;
    }
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

  function renderizarClientes(clientes) {
    tbody.innerHTML = "";

    if (clientes.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-loading">No hay clientes para mostrar.</td></tr>`;
      btnAnterior.disabled = paginaActual === 1;
      btnSiguiente.disabled = true;
      txtIndicador.textContent = `Página ${paginaActual}`;
      return;
    }

    clientes.forEach(cliente => {
      const fila = document.createElement("tr");

      if (cliente.estado === "INACTIVO") {
        fila.classList.add("inactivo");
      }

      fila.innerHTML = `
        <td><strong>${cliente.rut}</strong></td>
        <td>${cliente.razon_social}</td>
        <td>${cliente.areas_nombres || "Sin área"}</td>
        <td>
          <span class="badge estado-${normalizarEstado(cliente.estado).toLowerCase()}">
            ${normalizarEstado(cliente.estado)}
          </span>
        </td>
        <td>
          <div class="clientes-actions">
            <a href="ficha_cliente.html?id=${cliente.id_cliente}" class="btn btn-secondary btn-small">Ficha</a>
            <a href="modificar_clientes.html?id=${cliente.id_cliente}" class="btn btn-primary btn-small">Editar</a>
            <a href="cambiar_estado.html?id=${cliente.id_cliente}" class="btn btn-warning btn-small">Estado</a>
            <a href="eliminar_cliente.html?id=${cliente.id_cliente}" class="btn btn-danger btn-small">Quitar</a>
          </div>
        </td>
      `;

      tbody.appendChild(fila);
    });

    txtIndicador.textContent = `Página ${paginaActual}`;
    btnAnterior.disabled = paginaActual === 1;
    btnSiguiente.disabled = clientes.length < limiteRegistros;
  }

  function normalizarEstado(estado) {
    return estado || "ACTIVO";
  }

  selectAreaFiltro.addEventListener("change", () => {
    paginaActual = 1;
    cargarListadoGeneral();
  });

  inputBuscarTexto.addEventListener("input", () => {
    paginaActual = 1;
    cargarListadoGeneral();
  });

  btnAnterior.addEventListener("click", () => {
    if (paginaActual > 1) {
      paginaActual--;
      cargarListadoGeneral();
    }
  });

  btnSiguiente.addEventListener("click", () => {
    paginaActual++;
    cargarListadoGeneral();
  });

  cargarListadoGeneral();
});
