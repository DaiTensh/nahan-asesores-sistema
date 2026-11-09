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
  const form = document.getElementById("formReporte");
  const selectTipoReporte = document.getElementById("selectTipoReporte");
  const grupoCliente = document.getElementById("grupoCliente");
  const grupoResponsable = document.getElementById("grupoResponsable");
  const grupoAgruparHoras = document.getElementById("grupoAgruparHoras");
  const grupoGranularidad = document.getElementById("grupoGranularidad");
  const grupoHorasCliente = document.getElementById("grupoHorasCliente");
  const grupoHorasTarea = document.getElementById("grupoHorasTarea");
  const grupoHorasUsuario = document.getElementById("grupoHorasUsuario");
  const selectCliente = document.getElementById("selectCliente");
  const selectResponsable = document.getElementById("selectResponsable");
  const selectAgruparHoras = document.getElementById("selectAgruparHoras");
  const selectGranularidad = document.getElementById("selectGranularidad");
  const selectHorasCliente = document.getElementById("selectHorasCliente");
  const selectHorasTarea = document.getElementById("selectHorasTarea");
  const selectHorasUsuario = document.getElementById("selectHorasUsuario");
  const inputFechaInicio = document.getElementById("inputFechaInicio");
  const inputFechaFin = document.getElementById("inputFechaFin");
  const resultadoDetalle = document.getElementById("resultadoDetalle");
  const resultadoAreas = document.getElementById("resultadoAreas");
  const resultadoCobro = document.getElementById("resultadoCobro");
  const resultadoHoras = document.getElementById("resultadoHoras");
  const tablaAreas = document.getElementById("tablaAreas");
  const tablaComparacionAreas = document.getElementById("tablaComparacionAreas");
  const distribucionTareas = document.getElementById("distribucionTareas");
  document.getElementById("atajoPeriodo").addEventListener("change", event => {
    if (!event.target.value) return;
    const fin = new Date();
    const inicio = new Date(fin);
    if (event.target.value === "anio") inicio.setMonth(0, 1);
    else if (event.target.value === "mes") inicio.setMonth(inicio.getMonth() - 1);
    else inicio.setDate(inicio.getDate() - 6);
    const fechaLocal = fecha => `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;
    inputFechaInicio.value = fechaLocal(inicio);
    inputFechaFin.value = fechaLocal(fin);
  });
  // RF38 — si el usuario corrige las fechas a mano, el período deja de ser
  // el del atajo y no se debe informar como tal.
  [inputFechaInicio, inputFechaFin].forEach(input => input.addEventListener("input", () => {
    document.getElementById("atajoPeriodo").value = "";
  }));
  const mensaje = document.getElementById("mensajeReporte");
  const resultado = document.getElementById("resultadoReporte");
  const resultadoEntidadLabel = document.getElementById("resultadoEntidadLabel");
  const resultadoEntidad = document.getElementById("resultadoEntidad");
  const resultadoPeriodo = document.getElementById("resultadoPeriodo");
  const resultadoFechaGeneracion = document.getElementById("resultadoFechaGeneracion");
  const resumenEstadoCards = document.getElementById("resumenEstadoCards");
  const tablaTareasReporte = document.getElementById("tablaTareasReporte");
  const btnExportarExcel = document.getElementById("btnExportarExcel");

  let idReporteActual = null;
  let catalogosHorasCargados = false;
  let cargaCatalogosHorasPromise = null;
  let tareasHoras = [];

  cargarClientes();
  cargarResponsables();

  function actualizarCriterios() {
    const esCobro = selectTipoReporte.value === "cobro";
    const esHoras = selectTipoReporte.value === "horas";
    const esPorCliente = selectTipoReporte.value === "cliente" || esCobro;
    const esPorResponsable = selectTipoReporte.value === "responsable";
    grupoCliente.hidden = !esPorCliente;
    grupoResponsable.hidden = !esPorResponsable;
    selectCliente.required = esPorCliente;
    selectResponsable.required = esPorResponsable;
    grupoAgruparHoras.hidden = !esHoras;
    grupoGranularidad.hidden = !esHoras || selectAgruparHoras.value !== "periodo";
    grupoHorasCliente.hidden = !esHoras;
    grupoHorasTarea.hidden = !esHoras;
    grupoHorasUsuario.hidden = !esHoras;
    // RF75: el cobro puede calcularse para la totalidad de los registros, sin fechas.
    inputFechaInicio.required = !esCobro && !esHoras;
    inputFechaFin.required = !esCobro && !esHoras;
    document.getElementById("ayudaPeriodoCobro").hidden = !esCobro;
    document.getElementById("ayudaPeriodoHoras").hidden = !esHoras;
    // El aviso de error ya lo muestra cargarCatalogosHoras; aquí solo se evita el rechazo sin atender.
    if (esHoras) cargarCatalogosHoras().catch(() => {});
  }
  selectTipoReporte.addEventListener("change", actualizarCriterios);
  selectAgruparHoras.addEventListener("change", actualizarCriterios);
  selectHorasCliente.addEventListener("change", actualizarTareasHoras);
  if (new URLSearchParams(window.location.search).get("tipo") === "horas") {
    selectTipoReporte.value = "horas";
  }
  actualizarCriterios();

  async function cargarResponsables() {
    try {
      const response = await fetch(`${API_URL}/usuarios`, {
        credentials: window.API_CONFIG.credentials
      });
      const usuarios = await response.json();

      selectResponsable.textContent = "";

      if (!Array.isArray(usuarios) || usuarios.length === 0) {
        selectResponsable.appendChild(crearOpcion("", "No hay usuarios disponibles"));
        return;
      }

      selectResponsable.appendChild(crearOpcion("", "Seleccione un usuario"));

      usuarios
        .filter(usuario => usuario.estado === "ACTIVO")
        .forEach(usuario => {
          selectResponsable.appendChild(
            crearOpcion(usuario.id_usuario, `${usuario.nombres} (${usuario.nombre_area})`)
          );
        });
    } catch (error) {
      console.error(error);
      selectResponsable.textContent = "";
      selectResponsable.appendChild(crearOpcion("", "Error al cargar usuarios"));
    }
  }

  async function cargarClientes() {
    try {
      const response = await fetch(`${API_URL}/clientes/listado?limite=100`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();
      const clientes = Array.isArray(data) ? data : data.clientes || [];

      selectCliente.textContent = "";

      if (clientes.length === 0) {
        selectCliente.appendChild(crearOpcion("", "No hay clientes disponibles"));
        return;
      }

      selectCliente.appendChild(crearOpcion("", "Seleccione un cliente"));

      clientes.forEach(cliente => {
        selectCliente.appendChild(
          crearOpcion(cliente.id_cliente, `${cliente.razon_social} (${cliente.rut})`)
        );
      });
    } catch (error) {
      console.error(error);
      selectCliente.textContent = "";
      selectCliente.appendChild(crearOpcion("", "Error al cargar clientes"));
    }
  }

  function crearOpcion(valor, texto) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = texto;
    return opcion;
  }

  async function cargarCatalogosHoras() {
    if (catalogosHorasCargados) return;
    if (cargaCatalogosHorasPromise) return cargaCatalogosHorasPromise;

    cargaCatalogosHorasPromise = (async () => {
      try {
        const response = await fetch(`${API_URL}/control-horas/filtros`, {
          credentials: window.API_CONFIG.credentials
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "No fue posible cargar los filtros de horas.");
        }

        selectHorasCliente.textContent = "";
        selectHorasCliente.appendChild(crearOpcion("", "Todos los clientes"));
        (data.clientes || []).forEach(cliente => {
          selectHorasCliente.appendChild(crearOpcion(
            cliente.id_cliente,
            `${cliente.razon_social} (${cliente.rut})`
          ));
        });

        tareasHoras = Array.isArray(data.tareas) ? data.tareas : [];
        actualizarTareasHoras();

        selectHorasUsuario.textContent = "";
        selectHorasUsuario.appendChild(crearOpcion("", "Todos los usuarios"));
        (data.usuarios || []).forEach(usuario => {
          selectHorasUsuario.appendChild(crearOpcion(usuario.id_usuario, usuario.nombres));
        });

        catalogosHorasCargados = true;
        return true;
      } catch (error) {
        catalogosHorasCargados = false;
        console.error(error);
        mostrarMensaje(error.message || "No fue posible cargar los filtros de horas.", "error");
        throw error;
      } finally {
        cargaCatalogosHorasPromise = null;
      }
    })();

    return cargaCatalogosHorasPromise;
  }

  function actualizarTareasHoras() {
    const idCliente = selectHorasCliente.value;
    selectHorasTarea.textContent = "";
    selectHorasTarea.appendChild(crearOpcion("", "Todas las tareas"));
    tareasHoras
      .filter(tarea => !idCliente || String(tarea.id_cliente) === idCliente)
      .forEach(tarea => {
        selectHorasTarea.appendChild(crearOpcion(
          tarea.id_tarea,
          `${tarea.titulo} — ${tarea.cliente}`
        ));
      });
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    mostrarMensaje("");
    resultado.hidden = true;
    idReporteActual = null;
    btnExportarExcel.hidden = true;
    document.getElementById("btnExportarPdf").hidden = true;

    const esPorArea = selectTipoReporte.value === "area";
    const esPorResponsable = selectTipoReporte.value === "responsable";
    const esCobro = selectTipoReporte.value === "cobro";
    const esHoras = selectTipoReporte.value === "horas";
    const fechaInicio = inputFechaInicio.value;
    const fechaFin = inputFechaFin.value;
    const idEntidad = esPorResponsable ? selectResponsable.value : selectCliente.value;

    if (esHoras) {
      if (Boolean(fechaInicio) !== Boolean(fechaFin)) {
        mostrarMensaje("Indique ambas fechas o deje las dos vacías para incluir todas las horas registradas.", "error");
        return;
      }
      if (fechaInicio && fechaInicio > fechaFin) {
        mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.", "error");
        return;
      }

      const params = new URLSearchParams();
      params.set("agrupar_por", selectAgruparHoras.value);
      if (selectAgruparHoras.value === "periodo") {
        params.set("granularidad", selectGranularidad.value);
      }
      if (fechaInicio && fechaFin) {
        params.set("fecha_inicio", fechaInicio);
        params.set("fecha_fin", fechaFin);
        const atajo = document.getElementById("atajoPeriodo").value;
        if (atajo) params.set("periodo_etiqueta", atajo);
      }
      if (selectHorasCliente.value) params.set("id_cliente", selectHorasCliente.value);
      if (selectHorasTarea.value) params.set("id_tarea", selectHorasTarea.value);
      if (selectHorasUsuario.value) params.set("id_usuario", selectHorasUsuario.value);

      try {
        const response = await fetch(`${API_URL}/reportes/horas-trabajadas?${params.toString()}`, {
          credentials: window.API_CONFIG.credentials
        });
        const data = await response.json();
        if (!response.ok) {
          mostrarMensaje(data.error || "No fue posible generar el reporte.", "error");
          return;
        }
        if (data.mensaje) {
          mostrarMensaje(data.mensaje, "info");
          return;
        }
        renderizarResultadoHoras(data);
      } catch (error) {
        console.error(error);
        mostrarMensaje("Error al conectar con el servidor.", "error");
      }
      return;
    }

    if (esCobro) {
      if (!idEntidad) {
        mostrarMensaje("Seleccione un cliente.", "error");
        return;
      }
      if (Boolean(fechaInicio) !== Boolean(fechaFin)) {
        mostrarMensaje("Indique ambas fechas o deje las dos vacías para incluir todos los registros.", "error");
        return;
      }
    } else if ((!esPorArea && !idEntidad) || !fechaInicio || !fechaFin) {
      mostrarMensaje(
        esPorArea
          ? "Seleccione un período completo."
          : `Seleccione ${esPorResponsable ? "un usuario responsable" : "un cliente"} y un período completo.`,
        "error"
      );
      return;
    }

    if (fechaInicio && fechaFin && fechaInicio > fechaFin) {
      mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.", "error");
      return;
    }

    try {
      const endpoint = esCobro
        ? "cobro-por-cliente"
        : esPorArea
          ? "actividad-por-area"
          : esPorResponsable ? "tareas-por-responsable" : "tareas-por-cliente";
      const params = new URLSearchParams();
      if (fechaInicio && fechaFin) {
        params.set("fecha_inicio", fechaInicio);
        params.set("fecha_fin", fechaFin);
      }
      if (!esPorArea) {
        params.set(esPorResponsable ? "id_responsable" : "id_cliente", idEntidad);
      }
      const atajo = document.getElementById("atajoPeriodo").value;
      if (atajo && fechaInicio) params.set("periodo_etiqueta", atajo);

      const response = await fetch(`${API_URL}/reportes/${endpoint}?${params.toString()}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "No fue posible generar el reporte.", "error");
        return;
      }

      if (data.mensaje) {
        mostrarMensaje(data.mensaje, "info");
        return;
      }

      if (esCobro) renderizarResultadoCobro(data);
      else if (esPorArea) renderizarResultadoAreas(data);
      else renderizarResultado(data, esPorResponsable);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  });

  function renderizarResultado(data, esPorResponsable) {
    resultadoDetalle.hidden = false;
    resultadoAreas.hidden = true;
    resultadoCobro.hidden = true;
    resultadoHoras.hidden = true;
    document.getElementById("resultadoFiltrosHoras").hidden = true;
    resultadoEntidad.parentElement.hidden = false;
    const entidad = esPorResponsable ? data.responsable : data.cliente;
    const detalleEntidad = esPorResponsable ? entidad.email : entidad.rut;

    resultadoEntidadLabel.textContent = esPorResponsable ? "Usuario responsable" : "Cliente";
    resultadoEntidad.textContent = `${esPorResponsable ? entidad.nombres : entidad.razon_social} (${detalleEntidad})`;
    resultadoPeriodo.textContent = `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`
      + (data.periodo.etiqueta ? ` (${data.periodo.etiqueta})` : "");
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";

    renderizarResumenEstado(data.resumen_por_estado || {});
    renderizarTareas(data.tareas || []);

    idReporteActual = data.id_reporte || null;
    btnExportarExcel.hidden = !idReporteActual;
    document.getElementById("btnExportarPdf").hidden = !idReporteActual;

    resultado.hidden = false;
  }

  function renderizarResultadoHoras(data) {
    resultadoDetalle.hidden = true;
    resultadoAreas.hidden = true;
    resultadoCobro.hidden = true;
    resultadoHoras.hidden = false;
    resultadoEntidad.parentElement.hidden = false;
    resultadoEntidadLabel.textContent = "Agrupado por";
    const agrupacion = data.agrupar_por === "periodo"
      ? (data.granularidad === "mes" ? "Mes" : "Día")
      : ({ cliente: "Cliente", tarea: "Tarea", usuario: "Usuario" }[data.agrupar_por] || "Cliente");
    resultadoEntidad.textContent = agrupacion;
    resultadoPeriodo.textContent = data.periodo.todos_los_registros
      ? "Todos los registros"
      : `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`
        + (data.periodo.etiqueta ? ` (${data.periodo.etiqueta})` : "");
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";

    const filtrosActivos = [];
    if (data.filtros.cliente) filtrosActivos.push(`Cliente: ${data.filtros.cliente.razon_social}`);
    if (data.filtros.tarea) filtrosActivos.push(`Tarea: ${data.filtros.tarea.titulo}`);
    if (data.filtros.usuario) filtrosActivos.push(`Usuario: ${data.filtros.usuario.nombres}`);
    const resultadoFiltros = document.getElementById("resultadoFiltrosHoras");
    resultadoFiltros.textContent = filtrosActivos.length
      ? filtrosActivos.join(" · ")
      : "Sin filtros adicionales";
    resultadoFiltros.hidden = false;

    const moneda = data.moneda || "CLP";
    const resumen = document.getElementById("resumenHoras");
    resumen.textContent = "";
    [
      ["Horas trabajadas", `${formatearNumero(data.totales.horas, 2)} h`],
      ["Monto total", formatearMonto(data.totales.monto, moneda)],
      ["Registros incluidos", String(data.totales.registros)]
    ].forEach(([etiqueta, valor]) => {
      const dato = document.createElement("div");
      dato.className = "cobro-dato";
      const rotulo = document.createElement("span");
      rotulo.textContent = etiqueta;
      const cifra = document.createElement("strong");
      cifra.textContent = valor;
      dato.append(rotulo, cifra);
      resumen.appendChild(dato);
    });

    const nombreGrupo = data.agrupar_por === "periodo"
      ? (data.granularidad === "mes" ? "Mes" : "Día")
      : ({ cliente: "Cliente", tarea: "Tarea", usuario: "Usuario" }[data.agrupar_por] || "Cliente");
    const encabezados = [nombreGrupo];
    if (data.agrupar_por === "tarea") encabezados.push("Cliente");
    encabezados.push("Horas", "Registros", `Monto (${moneda})`);
    const encabezado = document.getElementById("encabezadoTablaHoras");
    encabezado.textContent = "";
    const filaEncabezado = document.createElement("tr");
    encabezados.forEach((texto, indice) => {
      const celda = document.createElement("th");
      celda.textContent = texto;
      if (indice >= encabezados.length - 3) celda.className = "numero";
      filaEncabezado.appendChild(celda);
    });
    encabezado.appendChild(filaEncabezado);

    const columnasNumericas = data.agrupar_por === "tarea" ? [2, 3, 4] : [1, 2, 3];
    llenarTabla(document.getElementById("cuerpoTablaHoras"), (data.filas || []).map(fila => {
      const valores = [fila.etiqueta];
      if (data.agrupar_por === "tarea") valores.push(fila.detalle);
      valores.push(
        formatearNumero(fila.horas, 2),
        String(fila.registros),
        formatearMonto(fila.monto, moneda)
      );
      return valores;
    }), columnasNumericas);

    document.getElementById("tituloTablaHoras").textContent = `Horas trabajadas por ${nombreGrupo.toLowerCase()}`;
    idReporteActual = data.id_reporte || null;
    btnExportarExcel.hidden = !idReporteActual;
    document.getElementById("btnExportarPdf").hidden = !idReporteActual;
    resultado.hidden = false;
  }

  // RF75 — monto a cobrar a un cliente: totales, desglose por tarifa y detalle de los registros.
  function renderizarResultadoCobro(data) {
    resultadoDetalle.hidden = true;
    resultadoAreas.hidden = true;
    resultadoCobro.hidden = false;
    resultadoHoras.hidden = true;
    document.getElementById("resultadoFiltrosHoras").hidden = true;
    resultadoEntidad.parentElement.hidden = false;
    resultadoEntidadLabel.textContent = "Cliente";
    resultadoEntidad.textContent = `${data.cliente.razon_social} (${data.cliente.rut})`;
    resultadoPeriodo.textContent = data.periodo.todos_los_registros
      ? "Todos los registros"
      : `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`
        + (data.periodo.etiqueta ? ` (${data.periodo.etiqueta})` : "");
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";

    const moneda = data.moneda || "CLP";
    const resumen = document.getElementById("resumenCobro");
    resumen.textContent = "";
    [
      ["Horas trabajadas", `${formatearNumero(data.totales.horas, 2)} h`],
      ["Monto total a cobrar", formatearMonto(data.totales.monto, moneda)],
      ["Registros incluidos", String(data.totales.registros)]
    ].forEach(([etiqueta, valor]) => {
      const dato = document.createElement("div");
      dato.className = "cobro-dato";
      const rotulo = document.createElement("span");
      rotulo.textContent = etiqueta;
      const cifra = document.createElement("strong");
      cifra.textContent = valor;
      dato.append(rotulo, cifra);
      resumen.appendChild(dato);
    });

    llenarTabla(document.getElementById("tablaDesgloseCobro"), (data.desglose_por_tarifa || []).map(item => [
      formatearMonto(item.tarifa_hora, moneda), `${formatearNumero(item.horas, 2)} h`, formatearMonto(item.monto, moneda)
    ]), [0, 1, 2]);
    llenarTabla(document.getElementById("tablaRegistrosCobro"), (data.registros || []).map(registro => [
      formatearFecha(registro.fecha), registro.tarea, registro.usuario, formatearNumero(registro.horas, 2),
      formatearMonto(registro.tarifa_hora, moneda), formatearMonto(registro.monto, moneda)
    ]), [3, 4, 5]);

    idReporteActual = data.id_reporte || null;
    btnExportarExcel.hidden = !idReporteActual;
    document.getElementById("btnExportarPdf").hidden = !idReporteActual;
    resultado.hidden = false;
  }

  function llenarTabla(cuerpo, filas, columnasNumericas = []) {
    cuerpo.textContent = "";
    filas.forEach(valores => {
      const fila = document.createElement("tr");
      valores.forEach((valor, indice) => {
        const celda = document.createElement("td");
        celda.textContent = valor;
        if (columnasNumericas.includes(indice)) celda.className = "numero";
        fila.appendChild(celda);
      });
      cuerpo.appendChild(fila);
    });
  }

  // Cifras con coma decimal y punto de miles, como se escriben en español de Chile.
  function formatearNumero(valor, decimales) {
    return Number(valor).toLocaleString("es-CL", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
  }

  function formatearMonto(valor, moneda) {
    return `${Number(valor).toLocaleString("es-CL", { maximumFractionDigits: 2 })} ${moneda}`;
  }

  function renderizarResultadoAreas(data) {
    resultadoDetalle.hidden = true;
    resultadoAreas.hidden = false;
    resultadoCobro.hidden = true;
    resultadoHoras.hidden = true;
    document.getElementById("resultadoFiltrosHoras").hidden = true;
    resultadoEntidad.parentElement.hidden = true;
    resultadoPeriodo.textContent = `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`
      + (data.periodo.etiqueta ? ` (${data.periodo.etiqueta})` : "");
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";
    idReporteActual = data.id_reporte || null;
    btnExportarExcel.hidden = !idReporteActual;
    document.getElementById("btnExportarPdf").hidden = !idReporteActual;

    renderizarResumenAreas(data.areas || []);
    renderizarComparacionAreas(data.comparacion || {});
    renderizarDistribucionTareas(data.areas || []);
    resultado.hidden = false;
  }

  function renderizarResumenAreas(areas) {
    tablaAreas.textContent = "";
    areas.forEach(area => {
      const fila = document.createElement("tr");
      [area.nombre_area, area.clientes, area.tareas, area.usuarios].forEach(valor => {
        const celda = document.createElement("td");
        celda.textContent = valor;
        fila.appendChild(celda);
      });
      tablaAreas.appendChild(fila);
    });
  }

  function renderizarComparacionAreas(comparacion) {
    tablaComparacionAreas.textContent = "";
    const mensajeComparacion = document.getElementById("mensajeComparacionAreas");
    const tabla = document.getElementById("comparacionAreas");
    tabla.hidden = !comparacion.disponible;
    mensajeComparacion.hidden = comparacion.disponible;
    if (!comparacion.disponible) {
      mensajeComparacion.textContent = "La comparación requiere que estén configuradas las áreas jurídica y contable.";
      return;
    }

    const metricas = [
      ["Clientes asignados", "clientes"],
      ["Tareas del período", "tareas"],
      ["Usuarios activos creados", "usuarios"]
    ];
    metricas.forEach(([etiqueta, clave]) => {
      const fila = document.createElement("tr");
      const diferencia = comparacion.diferencias[clave];
      [etiqueta, comparacion.juridica[clave], comparacion.contable[clave], diferencia > 0 ? `+${diferencia}` : diferencia]
        .forEach(valor => {
          const celda = document.createElement("td");
          celda.textContent = valor;
          fila.appendChild(celda);
        });
      tablaComparacionAreas.appendChild(fila);
    });
  }

  function renderizarDistribucionTareas(areas) {
    distribucionTareas.textContent = "";
    const total = areas.reduce((acumulado, area) => acumulado + area.tareas, 0);
    areas.forEach(area => {
      const porcentaje = total ? Math.round(area.tareas / total * 100) : 0;
      const fila = document.createElement("div");
      fila.className = "area-bar-row";

      const etiqueta = document.createElement("div");
      etiqueta.className = "area-bar-label";
      etiqueta.textContent = `${area.nombre_area}: ${area.tareas} (${porcentaje}%)`;

      const pista = document.createElement("div");
      pista.className = "area-bar-track";
      const barra = document.createElement("div");
      barra.className = "area-bar-fill";
      barra.setAttribute("role", "progressbar");
      barra.setAttribute("aria-label", `Tareas de ${area.nombre_area}`);
      barra.setAttribute("aria-valuemin", "0");
      barra.setAttribute("aria-valuemax", "100");
      barra.setAttribute("aria-valuenow", String(porcentaje));
      barra.style.width = `${porcentaje}%`;
      pista.appendChild(barra);
      fila.append(etiqueta, pista);
      distribucionTareas.appendChild(fila);
    });
  }

  async function exportar(formato) {
    if (!idReporteActual) return;

    try {
      const response = await fetch(`${API_URL}/reportes/${idReporteActual}/${formato}`, {
        credentials: window.API_CONFIG.credentials
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        mostrarMensaje(data.error || "No se pudo exportar el reporte.", "error");
        return;
      }

      const disposicion = response.headers.get("Content-Disposition") || "";
      const coincidencia = disposicion.match(/filename="?([^"]+)"?/);
      const nombreArchivo = coincidencia ? coincidencia[1] : `reporte.${formato === "excel" ? "xlsx" : "pdf"}`;

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = nombreArchivo;
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }
  btnExportarExcel.addEventListener("click", () => exportar("excel"));
  document.getElementById("btnExportarPdf").addEventListener("click", () => exportar("pdf"));

  function renderizarResumenEstado(resumen) {
    resumenEstadoCards.textContent = "";

    Object.entries(resumen).forEach(([estado, cantidad]) => {
      const card = document.createElement("div");
      card.className = "cliente-card";

      const etiqueta = document.createElement("p");
      etiqueta.textContent = formatearEstado(estado);

      const valor = document.createElement("h2");
      valor.textContent = cantidad;

      card.appendChild(etiqueta);
      card.appendChild(valor);
      resumenEstadoCards.appendChild(card);
    });
  }

  function renderizarTareas(tareas) {
    tablaTareasReporte.textContent = "";

    tareas.forEach(tarea => {
      const fila = document.createElement("tr");

      fila.innerHTML = `
        <td>${escapeHtml(tarea.titulo)}</td>
        <td>${escapeHtml(tarea.cliente)}</td>
        <td><span class="badge ${escapeHtml(tarea.estado.toLowerCase())}">${escapeHtml(formatearEstado(tarea.estado))}</span></td>
        <td><span class="badge prioridad-${escapeHtml(tarea.prioridad.toLowerCase())}">${escapeHtml(tarea.prioridad)}</span></td>
        <td>${escapeHtml(tarea.responsable)}</td>
        <td>${escapeHtml(tarea.fecha_creacion)}</td>
        <td>${escapeHtml(tarea.fecha_vencimiento || "Sin fecha")}</td>
      `;

      tablaTareasReporte.appendChild(fila);
    });
  }

  function formatearEstado(estado) {
    return String(estado || "").replaceAll("_", " ");
  }

  function formatearFecha(fecha) {
    const [anio, mes, dia] = String(fecha || "").split("-");
    return dia && mes && anio ? `${dia}-${mes}-${anio}` : fecha;
  }

  function mostrarMensaje(texto, tipo = "") {
    mensaje.textContent = texto;
    mensaje.className = `mensaje ${tipo}`.trim();
  }
});
