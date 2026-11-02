// RF60 — Respaldando históricamente la información: administración de respaldos
// (solo administradores). La autorización real se valida en el backend.
(function () {
  const API_URL = window.API_CONFIG.API_URL;
  const CLASE_ESTADO = { EXITOSO: "badge-success", FALLIDO: "badge-danger", EN_CURSO: "badge-warning" };
  const CLASE_NIVEL = { ok: "badge-success", aviso: "badge-warning", error: "badge-danger" };
  const TEXTO_NIVEL = { ok: "Correcto", aviso: "Aviso", error: "Error" };
  const TEXTO_OPERACION = { RESPALDO: "Respaldo", RESTAURACION: "Restauración" };
  const TEXTO_TIPO = { MANUAL: "Manual", PROGRAMADO: "Programado", PREVIO_RESTAURACION: "Previo a restauración" };

  let restauracionHabilitada = false;
  let respaldoARestaurar = null;

  function mostrarMensaje(id, texto, tipo) {
    const mensaje = document.getElementById(id);
    mensaje.textContent = texto || "";
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }

  function celda(texto) {
    const td = document.createElement("td");
    td.textContent = texto ?? "-";
    return td;
  }

  function formatearFecha(valor) {
    if (!valor) return "-";
    const [fecha, hora = ""] = String(valor).split(" ");
    const [anio, mes, dia] = fecha.split("-");
    return `${dia}-${mes}-${anio} ${hora.substring(0, 8)}`;
  }

  function formatearTamano(bytes) {
    if (bytes === null || bytes === undefined) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function insignia(texto, clase) {
    const span = document.createElement("span");
    span.className = `badge ${clase || ""}`.trim();
    span.textContent = texto;
    return span;
  }

  async function pedir(ruta, opciones) {
    const response = await fetch(`${API_URL}${ruta}`, {
      credentials: window.API_CONFIG.credentials,
      ...opciones
    });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, estado: response.status, data };
  }

  function pintarEstado(estado) {
    const lista = document.getElementById("listaAlmacenamiento");
    lista.textContent = "";
    const almacenamiento = estado.almacenamiento;
    almacenamiento.verificaciones.forEach(verificacion => {
      const li = document.createElement("li");
      li.appendChild(insignia(TEXTO_NIVEL[verificacion.nivel] || verificacion.nivel, CLASE_NIVEL[verificacion.nivel]));
      li.appendChild(document.createTextNode(verificacion.mensaje));
      lista.appendChild(li);
    });
    if (almacenamiento.directorio) {
      const li = document.createElement("li");
      li.appendChild(document.createTextNode(`Ubicación: ${almacenamiento.directorio}`));
      lista.appendChild(li);
    }

    const ultimo = estado.ultimo_exitoso;
    document.getElementById("textoUltimo").textContent = ultimo
      ? `#${ultimo.id_respaldo} (${TEXTO_TIPO[ultimo.tipo] || ultimo.tipo}), ${formatearFecha(ultimo.fecha_fin)}, ${formatearTamano(ultimo.tamano_bytes)}`
      : "Aún no hay respaldos exitosos.";
    document.getElementById("textoProgramacion").textContent = estado.programacion;
    restauracionHabilitada = estado.restauracion_habilitada;
    document.getElementById("textoRestauracion").textContent = restauracionHabilitada
      ? `Habilitada (destino: ${estado.base_de_destino})`
      : "Deshabilitada en este entorno (RESTAURACION_HABILITADA).";
    document.getElementById("btnRespaldar").disabled = !almacenamiento.apto || estado.operacion_en_curso;
  }

  async function cargarEstado() {
    try {
      const { ok, data } = await pedir("/respaldos/estado");
      if (!ok) {
        mostrarMensaje("mensajeRespaldo", data.error || "No fue posible cargar el estado.", "error");
        return;
      }
      pintarEstado(data);
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeRespaldo", "No fue posible conectar con el servidor.", "error");
    }
  }

  function botonAccion(texto, clase, alHacerClic) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = `btn ${clase} btn-sm`;
    boton.textContent = texto;
    boton.addEventListener("click", alHacerClic);
    return boton;
  }

  function filaRespaldo(respaldo) {
    const fila = document.createElement("tr");
    fila.appendChild(celda(formatearFecha(respaldo.fecha_inicio)));
    fila.appendChild(celda(TEXTO_OPERACION[respaldo.operacion] || respaldo.operacion));
    fila.appendChild(celda(TEXTO_TIPO[respaldo.tipo] || respaldo.tipo));

    const tdEstado = document.createElement("td");
    tdEstado.appendChild(insignia(respaldo.estado, CLASE_ESTADO[respaldo.estado]));
    fila.appendChild(tdEstado);

    fila.appendChild(celda(respaldo.usuario || (respaldo.tipo === "PROGRAMADO" ? "Automático" : "-")));
    fila.appendChild(celda(respaldo.duracion_segundos !== null ? `${respaldo.duracion_segundos.toFixed(1)} s` : "-"));
    fila.appendChild(celda(formatearTamano(respaldo.tamano_bytes)));

    const tdResultado = celda(respaldo.mensaje_error || respaldo.detalle || "-");
    tdResultado.className = "respaldos-resultado";
    fila.appendChild(tdResultado);

    const tdAcciones = document.createElement("td");
    const contenedor = document.createElement("div");
    contenedor.className = "respaldos-fila-acciones";
    const utilizable = respaldo.operacion === "RESPALDO" && respaldo.estado === "EXITOSO" && respaldo.archivo_disponible;
    if (utilizable) {
      contenedor.appendChild(botonAccion("Verificar", "btn-secondary", () => verificar(respaldo.id_respaldo)));
      if (restauracionHabilitada) {
        contenedor.appendChild(botonAccion("Restaurar", "btn-danger", () => prepararRestauracion(respaldo)));
      }
    } else if (respaldo.operacion === "RESPALDO" && respaldo.estado === "EXITOSO") {
      contenedor.appendChild(document.createTextNode("Archivo no disponible"));
    }
    tdAcciones.appendChild(contenedor);
    fila.appendChild(tdAcciones);
    return fila;
  }

  async function cargarHistorial() {
    const tabla = document.getElementById("tablaRespaldos");
    const limite = document.getElementById("selectLimite").value;
    try {
      const { ok, data } = await pedir(`/respaldos?limite=${encodeURIComponent(limite)}`);
      if (!ok) {
        mostrarMensaje("mensajeHistorial", data.error || "No fue posible cargar el historial.", "error");
        return;
      }
      mostrarMensaje("mensajeHistorial", "");
      tabla.textContent = "";
      if (!data.respaldos.length) {
        const fila = document.createElement("tr");
        const td = celda("Todavía no se registran respaldos.");
        td.colSpan = 9;
        fila.appendChild(td);
        tabla.appendChild(fila);
        return;
      }
      data.respaldos.forEach(respaldo => tabla.appendChild(filaRespaldo(respaldo)));
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeHistorial", "No fue posible conectar con el servidor.", "error");
    }
  }

  async function refrescar() {
    await cargarEstado();
    await cargarHistorial();
  }

  async function ejecutarRespaldo() {
    if (!confirm("¿Ejecutar un respaldo ahora? Puede tardar unos segundos.")) return;
    const boton = document.getElementById("btnRespaldar");
    boton.disabled = true;
    mostrarMensaje("mensajeRespaldo", "Ejecutando respaldo...", "info");
    try {
      const { ok, data } = await pedir("/respaldos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      mostrarMensaje("mensajeRespaldo", ok ? `Respaldo #${data.respaldo.id_respaldo} completado.` : (data.error || "El respaldo falló."),
        ok ? "success" : "error");
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeRespaldo", "No fue posible conectar con el servidor.", "error");
    }
    await refrescar();
  }

  async function verificar(idRespaldo) {
    mostrarMensaje("mensajeHistorial", `Verificando el respaldo #${idRespaldo}...`, "info");
    try {
      const { ok, data } = await pedir(`/respaldos/${idRespaldo}/verificar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      if (ok) {
        const resumen = data.resumen;
        mostrarMensaje("mensajeHistorial",
          `Respaldo #${idRespaldo} íntegro: ${resumen.tablas} tablas, ${resumen.filas} filas, ${resumen.adjuntos} adjuntos.`, "success");
      } else {
        mostrarMensaje("mensajeHistorial", data.error || "La verificación falló.", "error");
      }
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeHistorial", "No fue posible conectar con el servidor.", "error");
    }
  }

  function prepararRestauracion(respaldo) {
    respaldoARestaurar = respaldo.id_respaldo;
    document.getElementById("textoRestaurar").textContent =
      `Respaldo #${respaldo.id_respaldo} del ${formatearFecha(respaldo.fecha_inicio)}.`;
    document.getElementById("formRestaurar").reset();
    mostrarMensaje("mensajeRestaurar", "");
    const seccion = document.getElementById("seccionRestaurar");
    seccion.hidden = false;
    seccion.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function cancelarRestauracion() {
    respaldoARestaurar = null;
    document.getElementById("formRestaurar").reset();
    document.getElementById("seccionRestaurar").hidden = true;
  }

  async function restaurar(event) {
    event.preventDefault();
    if (respaldoARestaurar === null) return;
    const confirmacion = document.getElementById("inputConfirmacion").value.trim();
    const clave = document.getElementById("inputClave").value;
    if (confirmacion !== "RESTAURAR") {
      mostrarMensaje("mensajeRestaurar", "Escriba RESTAURAR para confirmar.", "error");
      return;
    }

    const boton = document.getElementById("btnConfirmarRestaurar");
    boton.disabled = true;
    mostrarMensaje("mensajeRestaurar", "Restaurando... no cierre esta página.", "info");
    try {
      const { ok, data } = await pedir(`/respaldos/${respaldoARestaurar}/restaurar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacion, password: clave })
      });
      document.getElementById("inputClave").value = "";
      if (ok) {
        mostrarMensaje("mensajeRestaurar", "Restauración completada. Vuelva a iniciar sesión si el sistema se lo solicita.", "success");
      } else {
        const recuperacion = data.recuperacion ? ` ${data.recuperacion}` : "";
        mostrarMensaje("mensajeRestaurar", `${data.error || "La restauración falló."}${recuperacion}`, "error");
      }
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeRestaurar", "No fue posible conectar con el servidor.", "error");
    }
    boton.disabled = false;
    await refrescar();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btnRespaldar").addEventListener("click", ejecutarRespaldo);
    document.getElementById("selectLimite").addEventListener("change", cargarHistorial);
    document.getElementById("formRestaurar").addEventListener("submit", restaurar);
    document.getElementById("btnCancelarRestaurar").addEventListener("click", cancelarRestauracion);
    refrescar();
  });
})();
