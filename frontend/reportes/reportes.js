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
  const selectCliente = document.getElementById("selectCliente");
  const selectResponsable = document.getElementById("selectResponsable");
  const inputFechaInicio = document.getElementById("inputFechaInicio");
  const inputFechaFin = document.getElementById("inputFechaFin");
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

  cargarClientes();
  cargarResponsables();

  selectTipoReporte.addEventListener("change", () => {
    const esPorResponsable = selectTipoReporte.value === "responsable";
    grupoCliente.hidden = esPorResponsable;
    grupoResponsable.hidden = !esPorResponsable;
  });

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

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    mostrarMensaje("");
    resultado.hidden = true;

    const esPorResponsable = selectTipoReporte.value === "responsable";
    const fechaInicio = inputFechaInicio.value;
    const fechaFin = inputFechaFin.value;
    const idEntidad = esPorResponsable ? selectResponsable.value : selectCliente.value;

    if (!idEntidad || !fechaInicio || !fechaFin) {
      mostrarMensaje(
        `Seleccione ${esPorResponsable ? "un usuario responsable" : "un cliente"} y un período completo.`,
        "error"
      );
      return;
    }

    if (fechaInicio > fechaFin) {
      mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.", "error");
      return;
    }

    try {
      const endpoint = esPorResponsable ? "tareas-por-responsable" : "tareas-por-cliente";
      const nombreParametro = esPorResponsable ? "id_responsable" : "id_cliente";
      const params = new URLSearchParams({
        [nombreParametro]: idEntidad,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin
      });

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

      renderizarResultado(data, esPorResponsable);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  });

  function renderizarResultado(data, esPorResponsable) {
    const entidad = esPorResponsable ? data.responsable : data.cliente;
    const detalleEntidad = esPorResponsable ? entidad.email : entidad.rut;

    resultadoEntidadLabel.textContent = esPorResponsable ? "Usuario responsable" : "Cliente";
    resultadoEntidad.textContent = `${esPorResponsable ? entidad.nombres : entidad.razon_social} (${detalleEntidad})`;
    resultadoPeriodo.textContent = `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`;
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";

    renderizarResumenEstado(data.resumen_por_estado || {});
    renderizarTareas(data.tareas || []);

    idReporteActual = data.id_reporte || null;
    btnExportarExcel.hidden = !idReporteActual;

    resultado.hidden = false;
  }

  btnExportarExcel.addEventListener("click", async () => {
    if (!idReporteActual) return;

    try {
      const response = await fetch(`${API_URL}/reportes/${idReporteActual}/excel`, {
        credentials: window.API_CONFIG.credentials
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        mostrarMensaje(data.error || "No se pudo exportar el reporte.", "error");
        return;
      }

      const disposicion = response.headers.get("Content-Disposition") || "";
      const coincidencia = disposicion.match(/filename="?([^"]+)"?/);
      const nombreArchivo = coincidencia ? coincidencia[1] : "reporte.xlsx";

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
  });

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
