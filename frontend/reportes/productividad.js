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
  const form = document.getElementById("formProductividad");
  const selectArea = document.getElementById("selectArea");
  const inputFechaInicio = document.getElementById("inputFechaInicio");
  const inputFechaFin = document.getElementById("inputFechaFin");
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
  const mensaje = document.getElementById("mensajeProductividad");
  const resultado = document.getElementById("resultadoProductividad");
  const resultadoPeriodo = document.getElementById("resultadoPeriodo");
  const resultadoFechaGeneracion = document.getElementById("resultadoFechaGeneracion");
  const tablaProductividad = document.getElementById("tablaProductividad");

  let idReporteActual = null;
  const btnExportarExcel = document.getElementById("btnExportarExcel");

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

  cargarAreas();

  async function cargarAreas() {
    try {
      const response = await fetch(`${API_URL}/usuarios`, {
        credentials: window.API_CONFIG.credentials
      });
      const usuarios = await response.json();

      if (!Array.isArray(usuarios)) return;

      const areas = new Map();
      usuarios.forEach(usuario => {
        if (usuario.id_area && !areas.has(usuario.id_area)) {
          areas.set(usuario.id_area, usuario.nombre_area);
        }
      });

      [...areas.entries()]
        .sort((a, b) => String(a[1]).localeCompare(String(b[1])))
        .forEach(([idArea, nombreArea]) => {
          const opcion = document.createElement("option");
          opcion.value = idArea;
          opcion.textContent = nombreArea;
          selectArea.appendChild(opcion);
        });
    } catch (error) {
      console.error(error);
    }
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    mostrarMensaje("");
    resultado.hidden = true;

    const fechaInicio = inputFechaInicio.value;
    const fechaFin = inputFechaFin.value;

    if (!fechaInicio || !fechaFin) {
      mostrarMensaje("Seleccione un período completo.", "error");
      return;
    }

    if (fechaInicio > fechaFin) {
      mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.", "error");
      return;
    }

    try {
      const params = new URLSearchParams({ fecha_inicio: fechaInicio, fecha_fin: fechaFin });
      if (selectArea.value) {
        params.set("id_area", selectArea.value);
      }

      const response = await fetch(`${API_URL}/reportes/productividad?${params.toString()}`, {
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

      renderizarResultado(data);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  });

  function renderizarResultado(data) {
    idReporteActual = data.id_reporte || null;
    resultadoPeriodo.textContent = `${formatearFecha(data.periodo.fecha_inicio)} — ${formatearFecha(data.periodo.fecha_fin)}`;
    resultadoFechaGeneracion.textContent = data.fecha_generacion || "-";

    renderizarTabla(data.usuarios || []);

    resultado.hidden = false;
  }

  function renderizarTabla(usuarios) {
    tablaProductividad.textContent = "";

    usuarios.forEach(fila => {
      const tr = document.createElement("tr");

      tr.innerHTML = `
        <td>${escapeHtml(fila.usuario)}</td>
        <td>${escapeHtml(fila.tareas_completadas)}</td>
        <td>${fila.tiempo_promedio_resolucion_horas != null ? escapeHtml(`${fila.tiempo_promedio_resolucion_horas} h`) : "Sin tareas completadas"}</td>
        <td>${escapeHtml(fila.carga_vigente)}</td>
      `;

      tablaProductividad.appendChild(tr);
    });
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
