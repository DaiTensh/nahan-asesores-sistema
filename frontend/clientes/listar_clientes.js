const API_URL = window.API_CONFIG.API_URL;

document.addEventListener("DOMContentLoaded", async () => {
  const selectAreaFiltro = document.getElementById("selectAreaFiltro");
  const inputBuscarTexto = document.getElementById("inputBuscarTexto");
  const tbody = document.getElementById("tablaClientesGeneralCuerpo");
  const btnAnterior = document.getElementById("btnPaginaAnterior");
  const btnSiguiente = document.getElementById("btnPaginaSiguiente");
  const txtIndicador = document.getElementById("txtIndicadorPagina");
  const encabezadosOrden = document.querySelectorAll(".clientes-table [data-sort]");
  const usuarioActual = await obtenerUsuarioActual();

  let paginaActual = 1;
  let ordenActual = "razon_social";
  let direccionActual = "asc";
  const limiteRegistros = 7;
  const esAdmin = usuarioActual && usuarioActual.nombre_rol === "ADMINISTRADOR";

  if (!usuarioActual) {
    window.location.href = "../auth/login.html";
    return;
  }

  async function cargarListadoGeneral() {
    mostrarFilaMensaje("Cargando clientes...");

    const idArea = selectAreaFiltro.value;
    const textoBuscar = inputBuscarTexto.value.trim();
    const queryParams = new URLSearchParams({
      pagina: String(paginaActual),
      limite: String(limiteRegistros),
      orden: ordenActual,
      direccion: direccionActual
    });

    if (idArea !== "TODOS") queryParams.set("id_area", idArea);
    if (textoBuscar) queryParams.set("buscar", textoBuscar);

    try {
      const response = await fetch(`${API_URL}/clientes/listado?${queryParams.toString()}`, {
        credentials: window.API_CONFIG.credentials
      });
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
      const response = await fetch(`${API_URL}/clientes/filtrar${queryString}`, {
        credentials: window.API_CONFIG.credentials
      });
      const clientes = await leerRespuestaJson(response);

      if (!response.ok) {
        const mensaje = clientes.error || errorOriginal || "No se pudo cargar el listado de clientes.";
        mostrarFilaMensaje(mensaje);
        return;
      }

      renderizarClientes(Array.isArray(clientes) ? clientes : []);
      btnAnterior.disabled = true;
      btnSiguiente.disabled = true;
      txtIndicador.textContent = "Listado";
    } catch (error) {
      console.error(error);
      mostrarFilaMensaje("Error al conectar con el servidor.");
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
    tbody.textContent = "";

    if (clientes.length === 0) {
      mostrarFilaMensaje("No hay clientes para mostrar.");
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

      const celdaRut = document.createElement("td");
      const rut = document.createElement("strong");
      rut.textContent = cliente.rut;
      celdaRut.appendChild(rut);

      fila.appendChild(celdaRut);
      fila.appendChild(crearCeldaTexto(cliente.razon_social));
      fila.appendChild(crearCeldaTexto(cliente.areas_nombres || "Sin área"));
      fila.appendChild(crearCeldaEstado(cliente.estado));
      fila.appendChild(crearCeldaTexto(cliente.fecha_creacion));
      fila.appendChild(crearCeldaAcciones(cliente));

      tbody.appendChild(fila);
    });

    txtIndicador.textContent = `Página ${paginaActual}`;
    btnAnterior.disabled = paginaActual === 1;
    btnSiguiente.disabled = clientes.length < limiteRegistros;
  }

  function normalizarEstado(estado) {
    return estado || "ACTIVO";
  }

  function mostrarFilaMensaje(mensaje) {
    tbody.textContent = "";

    const fila = document.createElement("tr");
    const celda = document.createElement("td");
    celda.colSpan = 6;
    celda.className = "text-loading";
    celda.textContent = mensaje;
    fila.appendChild(celda);
    tbody.appendChild(fila);
  }

  function crearCeldaTexto(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto || "";
    return celda;
  }

  function actualizarIndicadoresOrden() {
    encabezadosOrden.forEach(encabezado => {
      const indicador = encabezado.querySelector(".sort-indicator");
      const activo = encabezado.dataset.sort === ordenActual;

      indicador.textContent = activo
        ? (direccionActual === "asc" ? "▲" : "▼")
        : "";
      encabezado.closest("th").setAttribute(
        "aria-sort",
        activo ? (direccionActual === "asc" ? "ascending" : "descending") : "none"
      );
    });
  }

  function crearCeldaEstado(estadoCliente) {
    const estado = normalizarEstado(estadoCliente);
    const celda = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge estado-${estado.toLowerCase()}`;
    badge.textContent = estado;
    celda.appendChild(badge);
    return celda;
  }

  function crearCeldaAcciones(cliente) {
    const celda = document.createElement("td");
    const contenedor = document.createElement("div");
    contenedor.className = "clientes-actions";

    contenedor.appendChild(crearEnlaceAccion("Ficha", `ficha_cliente.html?id=${cliente.id_cliente}`, "btn btn-secondary btn-small"));
    contenedor.appendChild(crearEnlaceAccion("Editar", `modificar_clientes.html?id=${cliente.id_cliente}`, "btn btn-primary btn-small"));

    if (esAdmin) {
      contenedor.appendChild(crearEnlaceAccion("Estado", `cambiar_estado.html?id=${cliente.id_cliente}`, "btn btn-warning btn-small"));
      contenedor.appendChild(crearEnlaceAccion("Quitar", `eliminar_cliente.html?id=${cliente.id_cliente}`, "btn btn-danger btn-small"));
    }

    celda.appendChild(contenedor);
    return celda;
  }

  function crearEnlaceAccion(texto, href, clase) {
    const enlace = document.createElement("a");
    enlace.href = href;
    enlace.className = clase;
    enlace.textContent = texto;
    return enlace;
  }

  selectAreaFiltro.addEventListener("change", () => {
    paginaActual = 1;
    cargarListadoGeneral();
  });

  encabezadosOrden.forEach(encabezado => {
    encabezado.addEventListener("click", () => {
      const nuevoOrden = encabezado.dataset.sort;

      if (nuevoOrden === ordenActual) {
        direccionActual = direccionActual === "asc" ? "desc" : "asc";
      } else {
        ordenActual = nuevoOrden;
        direccionActual = "asc";
      }

      paginaActual = 1;
      actualizarIndicadoresOrden();
      cargarListadoGeneral();
    });
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

  actualizarIndicadoresOrden();
  cargarListadoGeneral();
});
