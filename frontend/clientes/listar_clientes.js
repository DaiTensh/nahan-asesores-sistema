const API_URL = window.API_CONFIG.API_URL;

document.addEventListener("DOMContentLoaded", async () => {
  const selectAreaFiltro = document.getElementById("selectAreaFiltro");
  const inputBuscarTexto = document.getElementById("inputBuscarTexto");
  const inputRutFiltro = document.getElementById("inputRutFiltro");
  const selectEstadoFiltro = document.getElementById("selectEstadoFiltro");
  const selectResponsableFiltro = document.getElementById("selectResponsableFiltro");
  const tbody = document.getElementById("tablaClientesGeneralCuerpo");
  const btnAnterior = document.getElementById("btnPaginaAnterior");
  const btnSiguiente = document.getElementById("btnPaginaSiguiente");
  const txtIndicador = document.getElementById("txtIndicadorPagina");
  const indicadorFiltros = document.getElementById("indicadorFiltrosActivos");
  const btnLimpiarFiltros = document.getElementById("btnLimpiarFiltros");
  const btnExportar = document.getElementById("btnExportarClientes");
  const encabezadosOrden = document.querySelectorAll(".clientes-table [data-sort]");
  const usuarioActual = await obtenerUsuarioActual();

  let paginaActual = 1;
  let ordenActual = "razon_social";
  let direccionActual = "asc";
  let temporizadorBusqueda = null;
  let solicitudActual = 0;
  const limiteRegistros = 7;
  const esAdmin = usuarioActual && usuarioActual.nombre_rol === "ADMINISTRADOR";

  if (!usuarioActual) {
    window.location.href = "../auth/login.html";
    return;
  }

  const claveFiltros = `nahan_clientes_filtros_${usuarioActual.id_usuario}`;
  const filtrosGuardados = leerFiltrosGuardados();
  restaurarFiltros(filtrosGuardados);
  await cargarResponsables(filtrosGuardados.id_responsable);
  guardarFiltros();
  actualizarIndicadorFiltros();

  async function cargarListadoGeneral() {
    const idSolicitud = ++solicitudActual;
    mostrarFilaMensaje("Cargando clientes...");

    const queryParams = construirParametros(true);

    try {
      const response = await fetch(`${API_URL}/clientes/listado?${queryParams.toString()}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await leerRespuestaJson(response);
      if (idSolicitud !== solicitudActual) return;

      if (!response.ok) {
        if (!hayFiltrosAvanzados()) {
          await cargarListadoSimple(selectAreaFiltro.value, inputBuscarTexto.value.trim(), data.error);
        } else {
          mostrarFilaMensaje(data.error || "No se pudo cargar el listado de clientes.");
        }
        return;
      }

      const clientes = Array.isArray(data) ? data : data.clientes;
      renderizarClientes(clientes || []);
    } catch (error) {
      console.error(error);
      if (idSolicitud !== solicitudActual) return;
      if (!hayFiltrosAvanzados()) {
        await cargarListadoSimple(selectAreaFiltro.value, inputBuscarTexto.value.trim());
      } else {
        mostrarFilaMensaje("Error al conectar con el servidor.");
      }
    }
  }

  function construirParametros(incluirPaginacion) {
    const queryParams = new URLSearchParams({
      orden: ordenActual,
      direccion: direccionActual
    });
    if (incluirPaginacion) {
      queryParams.set("pagina", String(paginaActual));
      queryParams.set("limite", String(limiteRegistros));
    }

    if (selectAreaFiltro.value !== "TODOS") queryParams.set("id_area", selectAreaFiltro.value);
    if (inputBuscarTexto.value.trim()) queryParams.set("nombre", inputBuscarTexto.value.trim());
    if (inputRutFiltro.value.trim()) queryParams.set("rut", inputRutFiltro.value.trim());
    if (selectEstadoFiltro.value) queryParams.set("estado", selectEstadoFiltro.value);
    if (selectResponsableFiltro.value) queryParams.set("id_responsable", selectResponsableFiltro.value);
    return queryParams;
  }

  function hayFiltrosAvanzados() {
    return Boolean(
      inputBuscarTexto.value.trim() || inputRutFiltro.value.trim()
      || selectEstadoFiltro.value || selectResponsableFiltro.value
    );
  }

  function leerFiltrosGuardados() {
    try {
      const filtros = JSON.parse(sessionStorage.getItem(claveFiltros) || "{}");
      return filtros && typeof filtros === "object" ? filtros : {};
    } catch (error) {
      return {};
    }
  }

  function restaurarFiltros(filtros) {
    const valoresArea = Array.from(selectAreaFiltro.options, opcion => opcion.value);
    if (valoresArea.includes(filtros.id_area)) selectAreaFiltro.value = filtros.id_area;
    inputBuscarTexto.value = typeof filtros.nombre === "string" ? filtros.nombre : "";
    inputRutFiltro.value = typeof filtros.rut === "string" ? filtros.rut : "";
    selectEstadoFiltro.value = ["ACTIVO", "INACTIVO"].includes(filtros.estado) ? filtros.estado : "";
  }

  async function cargarResponsables(idResponsableGuardado) {
    try {
      const response = await fetch(`${API_URL}/usuarios`, {
        credentials: window.API_CONFIG.credentials
      });
      const usuarios = await leerRespuestaJson(response);
      if (!response.ok || !Array.isArray(usuarios)) throw new Error("No se pudieron cargar los responsables.");

      selectResponsableFiltro.textContent = "";
      selectResponsableFiltro.appendChild(crearOpcion("", "Todos los responsables"));
      usuarios
        .slice()
        .sort((a, b) => String(a.nombres).localeCompare(String(b.nombres)))
        .forEach(usuario => selectResponsableFiltro.appendChild(
          crearOpcion(usuario.id_usuario, usuario.nombres)
        ));
      if (usuarios.some(usuario => String(usuario.id_usuario) === String(idResponsableGuardado))) {
        selectResponsableFiltro.value = String(idResponsableGuardado);
      }
    } catch (error) {
      console.error(error);
      selectResponsableFiltro.textContent = "";
      selectResponsableFiltro.appendChild(crearOpcion("", "Responsables no disponibles"));
    }
  }

  function crearOpcion(valor, texto) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = texto || "";
    return opcion;
  }

  function guardarFiltros() {
    const filtros = {
      id_area: selectAreaFiltro.value,
      nombre: inputBuscarTexto.value,
      rut: inputRutFiltro.value,
      estado: selectEstadoFiltro.value,
      id_responsable: selectResponsableFiltro.value
    };
    try {
      sessionStorage.setItem(claveFiltros, JSON.stringify(filtros));
    } catch (error) {
      console.warn("No se pudieron recordar los filtros de clientes.", error);
    }
  }

  function actualizarIndicadorFiltros() {
    const activos = [];
    if (selectAreaFiltro.value !== "TODOS") {
      activos.push(`Área: ${selectAreaFiltro.options[selectAreaFiltro.selectedIndex].text}`);
    }
    if (inputBuscarTexto.value.trim()) activos.push(`Nombre: ${inputBuscarTexto.value.trim()}`);
    if (inputRutFiltro.value.trim()) activos.push(`RUT: ${inputRutFiltro.value.trim()}`);
    if (selectEstadoFiltro.value) {
      activos.push(`Estado: ${selectEstadoFiltro.options[selectEstadoFiltro.selectedIndex].text}`);
    }
    if (selectResponsableFiltro.value) {
      activos.push(`Responsable: ${selectResponsableFiltro.options[selectResponsableFiltro.selectedIndex].text}`);
    }
    indicadorFiltros.textContent = activos.length
      ? `Filtros activos: ${activos.join(" · ")}`
      : "Sin filtros activos.";
  }

  function programarBusqueda() {
    paginaActual = 1;
    guardarFiltros();
    actualizarIndicadorFiltros();
    clearTimeout(temporizadorBusqueda);
    temporizadorBusqueda = setTimeout(cargarListadoGeneral, 250);
  }

  async function exportarResultados() {
    const parametros = construirParametros(false);
    parametros.set("formato", "excel");
    try {
      const response = await fetch(`${API_URL}/clientes/listado?${parametros.toString()}`, {
        credentials: window.API_CONFIG.credentials
      });
      if (!response.ok) {
        const data = await leerRespuestaJson(response);
        mostrarFilaMensaje(data.error || "No se pudieron exportar los resultados.");
        return;
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = "clientes_busqueda.xlsx";
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      mostrarFilaMensaje("Error al exportar los resultados.");
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
      fila.appendChild(crearCeldaTexto(cliente.responsables_nombres || "Sin responsable"));
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
    celda.colSpan = 7;
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

  [selectAreaFiltro, selectEstadoFiltro, selectResponsableFiltro].forEach(control => {
    control.addEventListener("change", programarBusqueda);
  });
  [inputBuscarTexto, inputRutFiltro].forEach(control => {
    control.addEventListener("input", programarBusqueda);
  });
  btnLimpiarFiltros.addEventListener("click", () => {
    selectAreaFiltro.value = "TODOS";
    inputBuscarTexto.value = "";
    inputRutFiltro.value = "";
    selectEstadoFiltro.value = "";
    selectResponsableFiltro.value = "";
    programarBusqueda();
  });
  btnExportar.addEventListener("click", exportarResultados);

  encabezadosOrden.forEach(encabezado => {
    encabezado.addEventListener("click", () => {
      const nuevoOrden = encabezado.dataset.sort;
      clearTimeout(temporizadorBusqueda);

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
