// RF56 — Historiando la Actividad y RF30 — accesos y modificaciones de usuarios:
// vista del historial global (solo administradores).
(function () {
  const API_URL = window.API_CONFIG.API_URL;
  const POR_PAGINA = 25;

  let paginaActual = 1;
  let totalPaginas = 1;

  function celda(texto) {
    const td = document.createElement("td");
    td.textContent = texto ?? "-";
    return td;
  }

  function formatearFecha(valor) {
    if (!valor) return "-";
    const [fecha, hora = ""] = String(valor).split(" ");
    const [anio, mes, dia] = fecha.split("-");
    return `${dia}-${mes}-${anio} ${hora.substring(0, 5)}`;
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

  function mostrarMensaje(texto) {
    document.getElementById("mensajeHistorial").textContent = texto || "";
  }

  function parametrosFiltro() {
    const parametros = new URLSearchParams();
    const modulo = document.getElementById("selectModulo").value;
    const usuario = document.getElementById("selectUsuario").value;
    const accion = document.getElementById("selectAccion").value;
    const inicio = document.getElementById("inputFechaInicio").value;
    const fin = document.getElementById("inputFechaFin").value;

    if (modulo) parametros.set("modulo", modulo);
    if (usuario) parametros.set("id_usuario", usuario);
    if (accion) parametros.set("accion", accion);
    if (inicio || fin) {
      parametros.set("fecha_inicio", inicio);
      parametros.set("fecha_fin", fin);
    }
    parametros.set("pagina", paginaActual);
    parametros.set("por_pagina", POR_PAGINA);
    return parametros;
  }

  async function cargarFiltros() {
    try {
      const response = await fetch(`${API_URL}/historial/filtros`, {
        credentials: window.API_CONFIG.credentials
      });
      if (!response.ok) return;
      const data = await response.json();

      const selectModulo = document.getElementById("selectModulo");
      data.modulos.forEach(modulo => {
        const opcion = document.createElement("option");
        opcion.value = modulo;
        opcion.textContent = modulo;
        selectModulo.appendChild(opcion);
      });

      const selectAccion = document.getElementById("selectAccion");
      (data.acciones || []).forEach(accion => {
        const opcion = document.createElement("option");
        opcion.value = accion;
        opcion.textContent = accion;
        selectAccion.appendChild(opcion);
      });

      const selectUsuario = document.getElementById("selectUsuario");
      data.usuarios.forEach(usuario => {
        const opcion = document.createElement("option");
        opcion.value = usuario.id_usuario;
        opcion.textContent = usuario.nombres;
        selectUsuario.appendChild(opcion);
      });
    } catch (error) {
      console.error(error);
    }
  }

  async function cargarHistorial() {
    const inicio = document.getElementById("inputFechaInicio").value;
    const fin = document.getElementById("inputFechaFin").value;

    if ((inicio && !fin) || (!inicio && fin)) {
      mostrarMensaje("Indique ambas fechas para filtrar por período.");
      return;
    }
    if (inicio && fin && inicio > fin) {
      mostrarMensaje("La fecha de inicio no puede ser posterior a la fecha de término.");
      return;
    }

    mostrarMensaje("");
    const tabla = document.getElementById("tablaHistorial");

    try {
      const response = await fetch(`${API_URL}/historial?${parametrosFiltro()}`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        mostrarMensaje(data.error || "No fue posible cargar el historial.");
        return;
      }

      tabla.textContent = "";
      totalPaginas = data.total_paginas;
      document.getElementById("totalEventos").textContent = `${data.total} evento(s)`;
      document.getElementById("textoPagina").textContent = `Página ${data.pagina} de ${data.total_paginas}`;
      document.getElementById("btnAnterior").disabled = data.pagina <= 1;
      document.getElementById("btnSiguiente").disabled = data.pagina >= data.total_paginas;

      if (!data.eventos.length) {
        const fila = document.createElement("tr");
        const td = celda("No se registran eventos para los filtros seleccionados.");
        td.colSpan = 5;
        fila.appendChild(td);
        tabla.appendChild(fila);
        return;
      }

      data.eventos.forEach(evento => {
        const fila = document.createElement("tr");
        fila.appendChild(celda(formatearFecha(evento.fecha)));
        fila.appendChild(celda(evento.usuario));
        fila.appendChild(celda(evento.modulo));
        fila.appendChild(celda(evento.accion));
        fila.appendChild(celdaDetalle(evento));
        tabla.appendChild(fila);
      });
    } catch (error) {
      console.error(error);
      mostrarMensaje("No fue posible conectar con el servidor.");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("formHistorial").addEventListener("submit", event => {
      event.preventDefault();
      paginaActual = 1;
      cargarHistorial();
    });

    document.getElementById("btnLimpiar").addEventListener("click", () => {
      document.getElementById("formHistorial").reset();
      paginaActual = 1;
      cargarHistorial();
    });

    document.getElementById("btnAnterior").addEventListener("click", () => {
      if (paginaActual > 1) {
        paginaActual -= 1;
        cargarHistorial();
      }
    });

    document.getElementById("btnSiguiente").addEventListener("click", () => {
      if (paginaActual < totalPaginas) {
        paginaActual += 1;
        cargarHistorial();
      }
    });

    cargarFiltros();
    cargarHistorial();
  });
})();
