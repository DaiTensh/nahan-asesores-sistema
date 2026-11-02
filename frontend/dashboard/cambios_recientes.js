(function () {
  const API_URL = window.API_CONFIG.API_URL;
  const INTERVALO_ACTUALIZACION_MS = 30000;
  let solicitudEnCurso = false;
  let actualizacionPendiente = false;
  let temporizador = null;

  function mostrarEstado(mensaje) {
    document.getElementById("estadoCambiosRecientes").textContent = mensaje;
  }

  function agregarOpciones(select, valores) {
    valores.forEach(valor => {
      const opcion = document.createElement("option");
      opcion.value = valor;
      opcion.textContent = valor;
      select.appendChild(opcion);
    });
  }

  function ocultarPorPermisos() {
    document.getElementById("seccionCambiosRecientes").hidden = true;
    detenerTemporizador();
  }

  function iniciarTemporizador() {
    if (temporizador === null) {
      temporizador = window.setInterval(cargarCambios, INTERVALO_ACTUALIZACION_MS);
    }
  }

  function detenerTemporizador() {
    if (temporizador !== null) {
      window.clearInterval(temporizador);
      temporizador = null;
    }
  }

  async function cargarFiltros() {
    const response = await fetch(`${API_URL}/cambios-recientes/filtros`, {
      credentials: window.API_CONFIG.credentials
    });
    if (response.status === 401 || response.status === 403) {
      ocultarPorPermisos();
      return false;
    }
    if (!response.ok) throw new Error("No fue posible cargar los filtros.");

    const filtros = await response.json();
    agregarOpciones(document.getElementById("filtroModuloCambios"), filtros.modulos || []);
    agregarOpciones(document.getElementById("filtroTipoCambio"), filtros.tipos || []);
    return true;
  }

  function crearCelda(fila, texto) {
    const celda = document.createElement("td");
    celda.textContent = texto == null ? "" : String(texto);
    fila.appendChild(celda);
    return celda;
  }

  function agregarAcceso(fila, cambio) {
    const celda = document.createElement("td");
    const id = Number(cambio.id_registro);
    if (Number.isSafeInteger(id) && id > 0) {
      let destino = null;
      if (cambio.tipo_registro === "cliente") {
        destino = `../clientes/ficha_cliente.html?id=${encodeURIComponent(id)}`;
      } else if (cambio.tipo_registro === "tarea") {
        destino = `../tareas/detalle_tarea.html?id=${encodeURIComponent(id)}`;
      }
      if (destino) {
        const enlace = document.createElement("a");
        enlace.className = "rf49-enlace-registro";
        enlace.href = destino;
        enlace.textContent = "Ver registro";
        celda.appendChild(enlace);
      }
    }
    if (!celda.childElementCount) celda.textContent = "No disponible";
    fila.appendChild(celda);
  }

  function renderizarCambios(cambios) {
    const tabla = document.getElementById("tablaCambiosRecientes");
    tabla.replaceChildren();
    if (!cambios.length) {
      mostrarEstado("No hay cambios recientes para los filtros seleccionados.");
      return;
    }

    cambios.forEach(cambio => {
      const fila = document.createElement("tr");
      crearCelda(fila, cambio.tipo);
      crearCelda(fila, cambio.modulo);
      crearCelda(fila, cambio.fecha);
      crearCelda(fila, cambio.hora);
      crearCelda(fila, cambio.usuario);
      agregarAcceso(fila, cambio);
      tabla.appendChild(fila);
    });
    mostrarEstado("");
  }

  async function cargarCambios() {
    if (solicitudEnCurso) {
      actualizacionPendiente = true;
      return;
    }
    solicitudEnCurso = true;
    const parametros = new URLSearchParams();
    const modulo = document.getElementById("filtroModuloCambios").value;
    const accion = document.getElementById("filtroTipoCambio").value;
    if (modulo) parametros.set("modulo", modulo);
    if (accion) parametros.set("accion", accion);

    try {
      const sufijo = parametros.toString();
      const url = `${API_URL}/cambios-recientes${sufijo ? `?${sufijo}` : ""}`;
      const response = await fetch(url, {
        credentials: window.API_CONFIG.credentials
      });
      if (response.status === 401 || response.status === 403) {
        ocultarPorPermisos();
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        mostrarEstado(data.error || "No fue posible cargar los cambios recientes.");
        return;
      }
      renderizarCambios(data.cambios || []);
    } catch (error) {
      console.error(error);
      mostrarEstado("No fue posible conectar con el servidor.");
    } finally {
      solicitudEnCurso = false;
      if (actualizacionPendiente && !document.getElementById("seccionCambiosRecientes").hidden) {
        actualizacionPendiente = false;
        cargarCambios();
      }
    }
  }

  window.addEventListener("pagehide", detenerTemporizador);
  window.addEventListener("pageshow", event => {
    if (!event.persisted || document.getElementById("seccionCambiosRecientes").hidden) return;
    cargarCambios();
    iniciarTemporizador();
  });

  document.addEventListener("DOMContentLoaded", async () => {
    const seccion = document.getElementById("seccionCambiosRecientes");
    if (!seccion || window.rf49CambiosRecientesIniciado) return;
    window.rf49CambiosRecientesIniciado = true;

    document.getElementById("filtroModuloCambios").addEventListener("change", cargarCambios);
    document.getElementById("filtroTipoCambio").addEventListener("change", cargarCambios);
    try {
      if (!(await cargarFiltros())) return;
      await cargarCambios();
      if (seccion.hidden) return;
      iniciarTemporizador();
    } catch (error) {
      console.error(error);
      mostrarEstado("No fue posible cargar los filtros de cambios recientes.");
    }
  });
})();