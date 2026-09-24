// RF40 — Historiando Consolidadamente las Actividades.
(function () {
  const API_URL = window.API_CONFIG.API_URL;
  let idReporteActual = null;

  const $ = id => document.getElementById(id);

  function fechaLocal(fecha) {
    return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;
  }

  function formatearFechaIso(valor) {
    if (!valor) return "-";
    const [fecha, hora = ""] = String(valor).split(" ");
    const [anio, mes, dia] = fecha.split("-");
    return hora ? `${dia}-${mes}-${anio} ${hora.substring(0, 5)}` : `${dia}-${mes}-${anio}`;
  }

  function mostrarMensaje(texto) {
    $("mensajeConsolidado").textContent = texto || "";
  }

  function celda(texto) {
    const td = document.createElement("td");
    td.textContent = texto ?? "-";
    return td;
  }

  function celdaDetalle(evento) {
    const td = document.createElement("td");
    td.className = "historial-detalle";
    const partes = [];
    if (evento.id_registro) partes.push(["Registro", `${evento.tabla_afectada} #${evento.id_registro}`]);
    if (evento.datos_anteriores) partes.push(["Antes", evento.datos_anteriores]);
    if (evento.datos_nuevos) partes.push(["Después", evento.datos_nuevos]);
    if (!partes.length) {
      td.textContent = "-";
      return td;
    }
    partes.forEach(([etiqueta, valor], indice) => {
      if (indice) td.appendChild(document.createElement("br"));
      const strong = document.createElement("strong");
      strong.textContent = `${etiqueta}: `;
      td.appendChild(strong);
      td.appendChild(document.createTextNode(valor));
    });
    return td;
  }

  async function cargarFiltros() {
    try {
      const response = await fetch(`${API_URL}/historial/filtros`, {
        credentials: window.API_CONFIG.credentials
      });
      if (!response.ok) return;
      const data = await response.json();
      data.modulos.forEach(modulo => {
        const opcion = document.createElement("option");
        opcion.value = modulo;
        opcion.textContent = modulo;
        $("selectModulo").appendChild(opcion);
      });
      data.usuarios.forEach(usuario => {
        const opcion = document.createElement("option");
        opcion.value = usuario.id_usuario;
        opcion.textContent = usuario.nombres;
        $("selectUsuario").appendChild(opcion);
      });
    } catch (error) {
      console.error(error);
    }
  }

  function renderizarResumen(resumen) {
    const contenedor = $("resumenModulos");
    contenedor.textContent = "";
    Object.entries(resumen)
      .sort(([a], [b]) => a.localeCompare(b))
      .forEach(([modulo, total]) => {
        const item = document.createElement("div");
        item.className = "historial-resumen-item";
        const etiqueta = document.createElement("p");
        etiqueta.textContent = modulo;
        const valor = document.createElement("strong");
        valor.textContent = total;
        item.appendChild(etiqueta);
        item.appendChild(valor);
        contenedor.appendChild(item);
      });
  }

  function renderizar(data) {
    $("resultadoPeriodo").textContent =
      `${formatearFechaIso(data.periodo.fecha_inicio)} al ${formatearFechaIso(data.periodo.fecha_fin)}`;
    const filtros = [
      data.filtros.modulo || "Todos los módulos",
      data.filtros.usuario ? data.filtros.usuario.nombres : "Todos los usuarios"
    ];
    $("resultadoFiltros").textContent = filtros.join(" · ");
    $("resultadoFechaGeneracion").textContent = data.fecha_generacion || "-";

    renderizarResumen(data.resumen_por_modulo);

    $("avisoTruncado").hidden = !data.truncado;
    $("avisoTruncado").textContent = data.truncado
      ? `Se muestran los ${data.eventos.length} eventos más recientes de ${data.total}. Acote el período para ver el resto.`
      : "";

    const tabla = $("tablaConsolidado");
    tabla.textContent = "";
    data.eventos.forEach(evento => {
      const fila = document.createElement("tr");
      fila.appendChild(celda(formatearFechaIso(evento.fecha)));
      fila.appendChild(celda(evento.usuario));
      fila.appendChild(celda(evento.modulo));
      fila.appendChild(celda(evento.accion));
      fila.appendChild(celdaDetalle(evento));
      tabla.appendChild(fila);
    });

    $("resultadoConsolidado").hidden = false;
  }

  async function generar() {
    const inicio = $("inputFechaInicio").value;
    const fin = $("inputFechaFin").value;

    if (!inicio || !fin) {
      mostrarMensaje("Indique la fecha de inicio y de término.");
      return;
    }
    if (inicio > fin) {
      mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.");
      return;
    }

    const parametros = new URLSearchParams({ fecha_inicio: inicio, fecha_fin: fin });
    if ($("selectModulo").value) parametros.set("modulo", $("selectModulo").value);
    if ($("selectUsuario").value) parametros.set("id_usuario", $("selectUsuario").value);

    mostrarMensaje("Generando...");
    try {
      const response = await fetch(`${API_URL}/reportes/historial-consolidado?${parametros}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        mostrarMensaje(data.error || "No fue posible generar el historial.");
        $("resultadoConsolidado").hidden = true;
        return;
      }

      if (!data.eventos.length) {
        idReporteActual = null;
        $("resultadoConsolidado").hidden = true;
        mostrarMensaje(data.mensaje);
        return;
      }

      idReporteActual = data.id_reporte;
      mostrarMensaje("");
      renderizar(data);
    } catch (error) {
      console.error(error);
      mostrarMensaje("No fue posible conectar con el servidor.");
    }
  }

  async function exportar(formato) {
    if (!idReporteActual) return;
    try {
      const response = await fetch(`${API_URL}/reportes/${idReporteActual}/${formato}`, {
        credentials: window.API_CONFIG.credentials
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        mostrarMensaje(data.error || "No se pudo exportar el historial.");
        return;
      }
      const disposicion = response.headers.get("Content-Disposition") || "";
      const coincidencia = disposicion.match(/filename="?([^"]+)"?/);
      const nombreArchivo = coincidencia ? coincidencia[1] : `historial.${formato === "excel" ? "xlsx" : "pdf"}`;
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
      mostrarMensaje("No fue posible conectar con el servidor.");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("atajoPeriodo").addEventListener("change", event => {
      if (!event.target.value) return;
      const fin = new Date();
      const inicio = new Date(fin);
      if (event.target.value === "anio") inicio.setMonth(0, 1);
      else if (event.target.value === "mes") inicio.setMonth(inicio.getMonth() - 1);
      else inicio.setDate(inicio.getDate() - 6);
      $("inputFechaInicio").value = fechaLocal(inicio);
      $("inputFechaFin").value = fechaLocal(fin);
    });

    $("formConsolidado").addEventListener("submit", event => {
      event.preventDefault();
      generar();
    });

    $("btnExportarPdf").addEventListener("click", () => exportar("pdf"));
    $("btnExportarExcel").addEventListener("click", () => exportar("excel"));

    cargarFiltros();
  });
})();
