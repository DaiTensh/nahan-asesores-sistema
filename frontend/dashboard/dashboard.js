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

// La API entrega DATE y DATETIME de MySQL (hora local del servidor, sin
// zona) serializados como "... GMT". Se muestran en UTC para conservar el
// valor guardado: convertirlos a la zona del navegador restaba un día a los
// vencimientos y 3 horas a las fechas con hora.
function formatearFecha(fecha) {
  if (!fecha) return "Sin fecha";
  const valor = new Date(fecha);
  return Number.isNaN(valor.getTime()) ? String(fecha) : valor.toLocaleDateString("es-CL", { timeZone: "UTC" });
}

document.addEventListener("DOMContentLoaded", () => {
  cargarDatosUsuario();
  cargarResumenUsuarios();
  cargarResumenClientes();
  cargarTareasVencidas();
  cargarTareasPrioritarias();
  cargarResumenTareas();
  cargarCargaTrabajoPorUsuario();

  const inputDias = document.getElementById("inputDiasPorVencer");
  cargarTareasPorVencer(inputDias.value);
  inputDias.addEventListener("change", () => cargarTareasPorVencer(inputDias.value));
  cargarResumenTareasPendientes();
  cargarResumenTareasFinalizadas();
  cargarDistribucionPorArea();

  const selectAreaCargaTrabajo = document.getElementById("selectAreaCargaTrabajo");
  if (selectAreaCargaTrabajo) {
    selectAreaCargaTrabajo.addEventListener("change", cargarCargaTrabajoPorUsuario);
  }
});

function formatearRol(rol) {
  const roles = {
    ADMINISTRADOR: "Administrador",
    USUARIO_AREA_JURIDICA: "Usuario Área Jurídica",
    USUARIO_AREA_CONTABLE: "Usuario Área Contable"
  };

  return roles[rol] || rol;
}

function formatearArea(area) {
  const areas = {
    ADMINISTRACION: "Administración",
    JURIDICA: "Jurídica",
    CONTABLE: "Contable",
    1: "Jurídica",
    2: "Contable",
    3: "Ambas áreas"
  };

  return areas[area] || area;
}

async function cargarDatosUsuario() {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  document.getElementById("nombreUsuario").textContent = usuario.nombres;
  document.getElementById("rolUsuario").textContent = formatearRol(usuario.nombre_rol);
  document.getElementById("areaUsuario").textContent = formatearArea(usuario.nombre_area || usuario.id_area);
}

async function cargarResumenUsuarios() {
  try {
    const response = await fetch(`${API_URL}/usuarios`, {
      credentials: window.API_CONFIG.credentials
    });
    const usuarios = await response.json();

    if (!response.ok) {
      console.error("Error al cargar usuarios");
      return;
    }

    document.getElementById("totalUsuarios").textContent = usuarios.length;
    document.getElementById("usuariosActivos").textContent =
      usuarios.filter(usuario => usuario.estado === "ACTIVO").length;
    document.getElementById("usuariosInactivos").textContent =
      usuarios.filter(usuario => usuario.estado === "INACTIVO").length;
    document.getElementById("totalAdmins").textContent =
      usuarios.filter(usuario => usuario.nombre_rol === "ADMINISTRADOR").length;

    const selectAreaCargaTrabajo = document.getElementById("selectAreaCargaTrabajo");
    if (selectAreaCargaTrabajo) {
      const areas = [...new Map(
        usuarios
          .filter(usuario => usuario.estado === "ACTIVO" && usuario.id_area != null)
          .map(usuario => [String(usuario.id_area), usuario.nombre_area || formatearArea(usuario.id_area)])
      )].map(([idArea, nombreArea]) => ({ idArea, nombreArea }));

      const valorActual = selectAreaCargaTrabajo.value;
      selectAreaCargaTrabajo.innerHTML = '<option value="">Todas las áreas</option>' + areas.map(area =>
        `<option value="${escapeHtml(area.idArea)}">${escapeHtml(area.nombreArea)}</option>`
      ).join("");
      if (valorActual) {
        selectAreaCargaTrabajo.value = valorActual;
      }
    }

    cargarTablaUsuarios(usuarios);

  } catch (error) {
    console.error(error);
  }
}

async function cargarCargaTrabajoPorUsuario() {
  try {
    const selectAreaCargaTrabajo = document.getElementById("selectAreaCargaTrabajo");
    const params = new URLSearchParams();
    if (selectAreaCargaTrabajo && selectAreaCargaTrabajo.value) {
      params.set("id_area", selectAreaCargaTrabajo.value);
    }

    const response = await fetch(`${API_URL}/reportes/carga-por-usuario${params.toString() ? `?${params.toString()}` : ""}`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar la carga de trabajo por usuario");
      return;
    }

    const tabla = document.getElementById("tablaCargaTrabajoUsuarios");
    tabla.innerHTML = "";

    if (!data.usuarios || data.usuarios.length === 0) {
      tabla.innerHTML = '<tr><td colspan="8">No hay usuarios activos para los criterios seleccionados.</td></tr>';
      return;
    }

    data.usuarios.forEach(usuario => {
      const fila = document.createElement("tr");
      fila.innerHTML = `
        <td>${escapeHtml(usuario.usuario || "-")}</td>
        <td>${escapeHtml(usuario.nombre_area || "-")}</td>
        <td>${escapeHtml(usuario.por_estado.PENDIENTE ?? 0)}</td>
        <td>${escapeHtml(usuario.por_estado.EN_PROCESO ?? 0)}</td>
        <td>${escapeHtml(usuario.por_estado.EN_REVISION ?? 0)}</td>
        <td>${escapeHtml(usuario.por_estado.COMPLETADA ?? 0)}</td>
        <td>${escapeHtml(usuario.por_estado.CANCELADA ?? 0)}</td>
        <td>${escapeHtml(usuario.total_tareas ?? 0)}</td>
      `;
      tabla.appendChild(fila);
    });
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaUsuarios(usuarios) {
  const tabla = document.getElementById("tablaUsuarios");
  tabla.innerHTML = "";

  usuarios.forEach(usuario => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${escapeHtml(usuario.id_usuario)}</td>
      <td>${escapeHtml(usuario.nombres)}</td>
      <td>${escapeHtml(usuario.email)}</td>
      <td>${escapeHtml(formatearRol(usuario.nombre_rol))}</td>
      <td>${escapeHtml(formatearArea(usuario.nombre_area))}</td>
      <td>
        <span class="badge ${escapeHtml(usuario.estado.toLowerCase())}">
          ${escapeHtml(usuario.estado)}
        </span>
      </td>
    `;

    tabla.appendChild(fila);
  });
}

async function cargarResumenClientes() {
  try {
    const response = await fetch(`${API_URL}/clientes/resumen`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      await cargarClientesDesdeListado();
      return;
    }

    document.getElementById("totalClientes").textContent = data.total_clientes;
    document.getElementById("clientesActivos").textContent = data.clientes_activos;
    document.getElementById("clientesInactivos").textContent = data.clientes_inactivos;

    cargarTablaClientes(data.ultimos_clientes || []);
  } catch (error) {
    console.error(error);
    await cargarClientesDesdeListado();
  }
}

async function cargarClientesDesdeListado() {
  try {
    const response = await fetch(`${API_URL}/clientes/listado?pagina=1&limite=5`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar clientes");
      return;
    }

    const clientes = Array.isArray(data) ? data : data.clientes || [];

    document.getElementById("totalClientes").textContent = clientes.length;
    document.getElementById("clientesActivos").textContent =
      clientes.filter(cliente => normalizarEstado(cliente.estado) === "ACTIVO").length;
    document.getElementById("clientesInactivos").textContent =
      clientes.filter(cliente => normalizarEstado(cliente.estado) === "INACTIVO").length;

    cargarTablaClientes(clientes);
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaClientes(clientes) {
  const tabla = document.getElementById("tablaClientes");
  tabla.innerHTML = "";

  if (clientes.length === 0) {
    tabla.innerHTML = `
      <tr>
        <td colspan="6">No hay clientes registrados.</td>
      </tr>
    `;
    return;
  }

  clientes.forEach(cliente => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${escapeHtml(cliente.rut)}</td>
      <td>${escapeHtml(cliente.razon_social)}</td>
      <td>${escapeHtml(cliente.email || "Sin correo")}</td>
      <td>${escapeHtml(cliente.telefono || "Sin teléfono")}</td>
      <td>
        <span class="badge ${escapeHtml(normalizarEstado(cliente.estado).toLowerCase())}">
          ${escapeHtml(normalizarEstado(cliente.estado))}
        </span>
      </td>
      <td>
        <div class="dashboard-row-actions">
          <a href="../clientes/ficha_cliente.html?id=${encodeURIComponent(cliente.id_cliente)}">Ficha</a>
          <a href="../clientes/modificar_clientes.html?id=${encodeURIComponent(cliente.id_cliente)}">Editar</a>
        </div>
      </td>
    `;

    tabla.appendChild(fila);
  });
}

async function cargarTareasVencidas() {
  try {
    const response = await fetch(`${API_URL}/tareas/vencidas`, {
      credentials: window.API_CONFIG.credentials
    });
    const tareas = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(tareas.error || "Error al cargar tareas vencidas");
      return;
    }

    cargarTablaTareasVencidas(tareas);
  } catch (error) {
    console.error(error);
  }
}

async function cargarResumenTareasPendientes() {
  try {
    const response = await fetch(`${API_URL}/tareas/pendientes/resumen`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar tareas pendientes");
      return;
    }

    document.getElementById("totalTareasPendientes").textContent = data.total_pendientes ?? 0;

    const diferenciaElemento = document.getElementById("diferenciaPendientes");
    if (data.comparacion && data.comparacion.disponible) {
      const diferencia = Number(data.comparacion.diferencia || 0);
      diferenciaElemento.textContent = `${diferencia > 0 ? "+" : ""}${diferencia}`;
    } else {
      diferenciaElemento.textContent = "N/A";
    }

    renderizarListaResumen("tareasPendientesPorArea", data.por_area || [], "area", "total");
    renderizarListaResumen("tareasPendientesPorCliente", data.por_cliente || [], "cliente", "total");
    renderizarListaResumen("tareasPendientesPorResponsable", data.por_responsable || [], "responsable", "total");
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaTareasVencidas(tareas) {
  const tabla = document.getElementById("tablaTareasVencidas");
  tabla.innerHTML = "";

  if (tareas.length === 0) {
    tabla.innerHTML = `
      <tr>
        <td colspan="6">No hay tareas vencidas.</td>
      </tr>
    `;
    return;
  }

  tareas.forEach(tarea => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${escapeHtml(tarea.titulo)}</td>
      <td>${escapeHtml(tarea.cliente)}</td>
      <td>${escapeHtml(tarea.responsable)}</td>
      <td>
        <span class="badge prioridad-${escapeHtml(tarea.prioridad.toLowerCase())}">
          ${escapeHtml(tarea.prioridad)}
        </span>
      </td>
      <td>${escapeHtml(formatearFecha(tarea.fecha_vencimiento))}</td>
      <td>${escapeHtml(tarea.dias_retraso)}</td>
    `;

    tabla.appendChild(fila);
  });
}

async function cargarTareasPorVencer(dias) {
  try {
    const response = await fetch(`${API_URL}/tareas/por-vencer?dias=${encodeURIComponent(dias)}`, {
      credentials: window.API_CONFIG.credentials
    });
    const tareas = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(tareas.error || "Error al cargar tareas próximas a vencer");
      return;
    }

    cargarTablaTareasPorVencer(tareas);
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaTareasPorVencer(tareas) {
  const tabla = document.getElementById("tablaTareasPorVencer");
  tabla.innerHTML = "";

  if (tareas.length === 0) {
    tabla.innerHTML = `
      <tr>
        <td colspan="6">No hay tareas próximas a vencer en este período.</td>
      </tr>
    `;
    return;
  }

  tareas.forEach(tarea => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${escapeHtml(tarea.titulo)}</td>
      <td>${escapeHtml(tarea.cliente)}</td>
      <td>${escapeHtml(tarea.responsable)}</td>
      <td>
        <span class="badge prioridad-${escapeHtml(tarea.prioridad.toLowerCase())}">
          ${escapeHtml(tarea.prioridad)}
        </span>
      </td>
      <td>${escapeHtml(formatearFecha(tarea.fecha_vencimiento))}</td>
      <td>${escapeHtml(tarea.dias_restantes)}</td>
    `;

    tabla.appendChild(fila);
  });
}

async function cargarTareasPrioritarias() {
  try {
    const response = await fetch(`${API_URL}/tareas/prioritarias`, {
      credentials: window.API_CONFIG.credentials
    });
    const tareas = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(tareas.error || "Error al cargar tareas prioritarias");
      return;
    }

    cargarTablaTareasPrioritarias(tareas);
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaTareasPrioritarias(tareas) {
  const tabla = document.getElementById("tablaTareasPrioritarias");
  tabla.innerHTML = "";

  if (tareas.length === 0) {
    tabla.innerHTML = `
      <tr>
        <td colspan="5">No tienes tareas prioritarias pendientes.</td>
      </tr>
    `;
    return;
  }

  tareas.forEach(tarea => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${escapeHtml(tarea.titulo)}</td>
      <td>${escapeHtml(tarea.cliente)}</td>
      <td>
        <span class="badge prioridad-${escapeHtml(tarea.prioridad.toLowerCase())}">
          ${escapeHtml(tarea.prioridad)}
        </span>
      </td>
      <td>
        <span class="badge ${escapeHtml(tarea.estado.toLowerCase())}">
          ${escapeHtml(tarea.estado)}
        </span>
      </td>
      <td>${escapeHtml(formatearFecha(tarea.fecha_vencimiento))}</td>
    `;

    tabla.appendChild(fila);
  });
}

async function cargarResumenTareas() {
  try {
    const response = await fetch(`${API_URL}/tareas/resumen`, {
      credentials: window.API_CONFIG.credentials
    });
    const resumen = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(resumen.error || "Error al cargar el resumen de tareas");
      return;
    }

    document.getElementById("resumenPendiente").textContent = resumen.PENDIENTE ?? 0;
    document.getElementById("resumenEnProceso").textContent = resumen.EN_PROCESO ?? 0;
    document.getElementById("resumenEnRevision").textContent = resumen.EN_REVISION ?? 0;
    document.getElementById("resumenCompletada").textContent = resumen.COMPLETADA ?? 0;
    document.getElementById("resumenCancelada").textContent = resumen.CANCELADA ?? 0;
  } catch (error) {
    console.error(error);
  }
}

async function cargarResumenTareasFinalizadas() {
  try {
    const response = await fetch(`${API_URL}/tareas/finalizadas/resumen`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar tareas finalizadas");
      return;
    }

    document.getElementById("totalTareasFinalizadas").textContent = data.total_finalizadas ?? 0;
    document.getElementById("totalTareasAsignadas").textContent = data.total_asignadas ?? 0;
    const porcentaje = Number(data.porcentaje_cumplimiento ?? 0);
    document.getElementById("cumplimientoTareasFinalizadas").textContent = `${porcentaje.toFixed(1)}%`;

    const diferenciaElemento = document.getElementById("diferenciaFinalizadas");
    if (data.comparacion && data.comparacion.disponible) {
      const diferencia = Number(data.comparacion.diferencia || 0);
      diferenciaElemento.textContent = `${diferencia > 0 ? "+" : ""}${diferencia}`;
    } else {
      diferenciaElemento.textContent = "N/A";
    }

    renderizarListaResumen("tareasFinalizadasPorArea", data.por_area || [], "area", "total");
    renderizarListaResumen("tareasFinalizadasPorCliente", data.por_cliente || [], "cliente", "total");
    renderizarListaResumen("tareasFinalizadasPorUsuario", data.por_usuario || [], "usuario", "total");
  } catch (error) {
    console.error(error);
  }
}

async function cargarDistribucionPorArea() {
  try {
    const response = await fetch(`${API_URL}/reportes/distribucion-por-area`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar la distribución por área");
      return;
    }

    document.getElementById("totalClientesDistribucionArea").textContent = data.total_clientes ?? 0;
    document.getElementById("totalRelacionesClientesArea").textContent = data.total_asignaciones_cliente_area ?? 0;
    document.getElementById("totalTareasDistribucionArea").textContent = data.total_tareas ?? 0;

    renderizarDistribucionArea(
      "distribucionClientesPorArea",
      data.areas || [],
      "clientes",
      "porcentaje_clientes"
    );
    renderizarDistribucionArea(
      "distribucionTareasPorArea",
      data.areas || [],
      "tareas",
      "porcentaje_tareas"
    );
  } catch (error) {
    console.error(error);
  }
}

function renderizarDistribucionArea(idContenedor, areas, claveCantidad, clavePorcentaje) {
  const contenedor = document.getElementById(idContenedor);
  contenedor.replaceChildren();

  if (!areas.length) {
    const vacio = document.createElement("p");
    vacio.textContent = "No hay áreas registradas.";
    contenedor.appendChild(vacio);
    return;
  }

  areas.forEach(area => {
    const cantidad = Number(area[claveCantidad] || 0);
    const porcentaje = Math.min(100, Math.max(0, Number(area[clavePorcentaje] || 0)));
    const fila = document.createElement("div");
    fila.className = "dashboard-area-row";

    const encabezado = document.createElement("div");
    encabezado.className = "dashboard-area-row-heading";
    const nombre = document.createElement("span");
    nombre.textContent = area.nombre_area;
    const valor = document.createElement("strong");
    valor.textContent = `${cantidad} (${porcentaje.toFixed(1)}%)`;
    encabezado.append(nombre, valor);

    const pista = document.createElement("div");
    pista.className = "dashboard-area-track";
    pista.setAttribute("role", "progressbar");
    pista.setAttribute("aria-label", `${area.nombre_area}: ${cantidad}`);
    pista.setAttribute("aria-valuemin", "0");
    pista.setAttribute("aria-valuemax", "100");
    pista.setAttribute("aria-valuenow", porcentaje.toFixed(1));
    const barra = document.createElement("span");
    barra.className = "dashboard-area-fill";
    barra.style.width = `${porcentaje}%`;
    pista.appendChild(barra);

    fila.append(encabezado, pista);
    contenedor.appendChild(fila);
  });
}

function renderizarListaResumen(idLista, elementos, etiquetaClave, etiquetaValor) {
  const lista = document.getElementById(idLista);
  lista.innerHTML = "";

  if (!elementos.length) {
    const item = document.createElement("li");
    item.textContent = "Sin tareas pendientes.";
    lista.appendChild(item);
    return;
  }

  elementos.forEach(elemento => {
    const item = document.createElement("li");
    item.textContent = `${elemento[etiquetaClave]}: ${elemento[etiquetaValor]}`;
    lista.appendChild(item);
  });
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

function normalizarEstado(estado) {
  return estado || "ACTIVO";
}
