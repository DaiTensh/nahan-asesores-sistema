const API_URL = window.API_CONFIG.API_URL;

const formTarea = document.getElementById("formTarea");
const mensajeTarea = document.getElementById("mensajeTarea");
const tablaTareas = document.getElementById("tablaTareas");
const ESTADOS_OPERATIVOS = [
  ["PENDIENTE", "Pendiente"],
  ["EN_PROCESO", "En proceso"],
  ["EN_REVISION", "En revisión"]
];
const ESTADOS_FINALES = [
  ["COMPLETADA", "Completada"],
  ["CANCELADA", "Cancelada"]
];

document.addEventListener("DOMContentLoaded", () => {
  ClientesAutocomplete.configurarSelectorCliente({
    inputId: "cliente_busqueda",
    hiddenId: "id_cliente",
    datalistId: "clientes_datalist",
    soloActivos: true
  });

  UsuariosAutocomplete.configurarSelectorUsuario({
    inputId: "responsable_busqueda",
    hiddenId: "id_responsable",
    datalistId: "usuarios_responsables",
    soloActivos: true
  });

  cargarTareasPendientes();
});

formTarea.addEventListener("submit", async (event) => {
  event.preventDefault();

  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const cliente = await ClientesAutocomplete.obtenerClienteSeleccionado(
    "cliente_busqueda",
    { soloActivos: true }
  );

  if (!cliente) {
    mostrarMensaje("Seleccione un cliente de la lista", "error");
    return;
  }

  const responsable = await UsuariosAutocomplete.obtenerUsuarioSeleccionado(
    "responsable_busqueda",
    { soloActivos: true }
  );

  if (!responsable) {
    mostrarMensaje("Seleccione un responsable de la lista", "error");
    return;
  }

  const areaSeleccionada = document.getElementById("id_area").value;
  const areas = areaSeleccionada === "AMBAS"
    ? [1, 2]
    : [Number(areaSeleccionada)];

  if (areas.some(idArea => !idArea)) {
    mostrarMensaje("Seleccione un área", "error");
    return;
  }

  const confirmar = confirm("Desea crear esta nueva tarea?");

  if (!confirmar) return;

  const nuevaTarea = {
    id_cliente: Number(cliente.id_cliente),
    areas,
    id_responsable: Number(responsable.id_usuario),
    titulo: document.getElementById("titulo").value.trim(),
    descripcion: document.getElementById("descripcion").value.trim(),
    prioridad: document.getElementById("prioridad").value,
    fecha_vencimiento: document.getElementById("fecha_vencimiento").value || null
  };

  try {
    const response = await fetch(`${API_URL}/tareas`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(nuevaTarea)
    });

    const data = await response.json();

    if (!response.ok) {
      mostrarMensaje(data.error || "No se pudo crear la tarea", "error");
      return;
    }

    mostrarMensaje(data.message, "success");
    formTarea.reset();
    cargarTareasPendientes();

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor", "error");
  }
});

function mostrarMensaje(texto, tipo) {
  mensajeTarea.textContent = texto;
  mensajeTarea.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

async function cargarTareasPendientes() {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  try {
    const response = await fetch(`${API_URL}/tareas/pendientes`, {
      credentials: window.API_CONFIG.credentials
    });
    let tareas = await response.json();

    if (!response.ok) {
      console.error(tareas.error || "Error al cargar tareas");
      return;
    }

    if (usuario.nombre_rol !== "ADMINISTRADOR") {
      tareas = tareas.filter(
        tarea => Number(tarea.id_responsable) === Number(usuario.id_usuario)
      );
    }

    actualizarResumen(tareas);
    renderizarTabla(tareas, usuario);

  } catch (error) {
    console.error(error);
  }
}

function actualizarResumen(tareas) {
  const pendientes = tareas.filter(t => t.estado === "PENDIENTE").length;
  const proceso = tareas.filter(t => t.estado === "EN_PROCESO").length;
  const revision = tareas.filter(t => t.estado === "EN_REVISION").length;
  const urgentes = tareas.filter(t => t.prioridad === "URGENTE").length;

  document.getElementById("totalPendientes").textContent = pendientes;
  document.getElementById("totalProceso").textContent = proceso;
  document.getElementById("totalRevision").textContent = revision;
  document.getElementById("totalUrgentes").textContent = urgentes;
}

function renderizarTabla(tareas, usuario) {
  tablaTareas.textContent = "";

  if (tareas.length === 0) {
    const filaVacia = document.createElement("tr");
    const celdaVacia = document.createElement("td");
    celdaVacia.colSpan = 9;
    celdaVacia.textContent = "No hay tareas pendientes para mostrar.";
    filaVacia.appendChild(celdaVacia);
    tablaTareas.appendChild(filaVacia);
    return;
  }

  tareas.forEach(tarea => {
    const fila = document.createElement("tr");

    fila.appendChild(crearCeldaTexto(tarea.id_tarea));
    fila.appendChild(crearCeldaTexto(tarea.titulo));
    fila.appendChild(crearCeldaTexto(tarea.cliente));
    fila.appendChild(crearCeldaTexto(tarea.area));
    fila.appendChild(crearCeldaTexto(tarea.responsable));
    fila.appendChild(crearCeldaBadge(`estado-${tarea.estado.toLowerCase()}`, formatearEstado(tarea.estado)));
    fila.appendChild(crearCeldaBadge(`prioridad-${tarea.prioridad.toLowerCase()}`, formatearPrioridad(tarea.prioridad)));
    fila.appendChild(crearCeldaTexto(formatearFecha(tarea.fecha_vencimiento)));

    const celdaAcciones = document.createElement("td");
    celdaAcciones.appendChild(accionesTarea(tarea, usuario));
    fila.appendChild(celdaAcciones);

    tablaTareas.appendChild(fila);
  });
}

function crearCeldaTexto(valor) {
  const celda = document.createElement("td");
  celda.textContent = valor ?? "";
  return celda;
}

function crearCeldaBadge(clase, texto) {
  const celda = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `badge ${clase}`;
  badge.textContent = texto;
  celda.appendChild(badge);
  return celda;
}

function accionesTarea(tarea, usuario) {
  const puedeAdministrar = usuario.nombre_rol === "ADMINISTRADOR";
  const contenedor = document.createElement("div");
  contenedor.className = "tareas-actions";

  if (puedeAdministrar) {
    const responsable = document.createElement("input");
    responsable.type = "text";
    responsable.id = `responsable-${tarea.id_tarea}`;
    responsable.setAttribute("list", "usuarios_responsables");
    responsable.placeholder = "Responsable";
    contenedor.appendChild(responsable);

    const botonAsignar = document.createElement("button");
    botonAsignar.className = "btn btn-primary btn-small";
    botonAsignar.textContent = "Asignar";
    botonAsignar.addEventListener("click", () => asignarTarea(tarea.id_tarea));
    contenedor.appendChild(botonAsignar);
  }

  const selectorEstado = document.createElement("select");
  selectorEstado.id = `estado-${tarea.id_tarea}`;
  agregarOpciones(selectorEstado, ESTADOS_OPERATIVOS);

  if (puedeAdministrar) {
    const grupoFinales = document.createElement("optgroup");
    grupoFinales.label = "Revisión administrativa";
    agregarOpciones(grupoFinales, ESTADOS_FINALES);
    selectorEstado.appendChild(grupoFinales);
  }

  selectorEstado.value = tarea.estado;
  contenedor.appendChild(selectorEstado);

  const botonEstado = document.createElement("button");
  botonEstado.className = "btn btn-primary btn-small";
  botonEstado.textContent = "Estado";
  botonEstado.addEventListener("click", () => actualizarEstado(tarea.id_tarea));
  contenedor.appendChild(botonEstado);

  const selectorPrioridad = document.createElement("select");
  selectorPrioridad.id = `prioridad-${tarea.id_tarea}`;
  agregarOpciones(selectorPrioridad, [
    ["BAJA", "Baja"],
    ["MEDIA", "Media"],
    ["ALTA", "Alta"],
    ["URGENTE", "Urgente"]
  ]);
  selectorPrioridad.value = tarea.prioridad;
  contenedor.appendChild(selectorPrioridad);

  const botonPrioridad = document.createElement("button");
  botonPrioridad.className = "btn btn-primary btn-small";
  botonPrioridad.textContent = "Prioridad";
  botonPrioridad.addEventListener("click", () => actualizarPrioridad(tarea.id_tarea));
  contenedor.appendChild(botonPrioridad);

  return contenedor;
}

function agregarOpciones(selector, opciones) {
  opciones.forEach(([valor, etiqueta]) => {
    const option = document.createElement("option");
    option.value = valor;
    option.textContent = etiqueta;
    selector.appendChild(option);
  });
}

async function asignarTarea(idTarea) {
  const responsable = await UsuariosAutocomplete.obtenerUsuarioSeleccionado(
    `responsable-${idTarea}`,
    { soloActivos: true }
  );

  if (!responsable) {
    alert("Seleccione un responsable de la lista");
    return;
  }

  const confirmar = confirm("Desea asignar esta tarea a otro usuario?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/asignar`, {
      method: "PUT",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        id_responsable: Number(responsable.id_usuario)
      })
    });

    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "No se pudo asignar la tarea");
      return;
    }

    alert(data.message);
    cargarTareasPendientes();

  } catch (error) {
    console.error(error);
    alert("Error al conectar con el servidor");
  }
}

async function actualizarEstado(idTarea) {
  const estado = document.getElementById(`estado-${idTarea}`).value;
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  if (
    ESTADOS_FINALES.some(([valor]) => valor === estado)
    && usuario.nombre_rol !== "ADMINISTRADOR"
  ) {
    alert("Solo un administrador puede marcar una tarea como final o cancelada");
    return;
  }

  const confirmar = confirm("Desea actualizar el estado de esta tarea?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/estado`, {
      method: "PUT",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ estado })
    });

    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "No se pudo actualizar el estado");
      return;
    }

    alert(data.message);
    cargarTareasPendientes();

  } catch (error) {
    console.error(error);
    alert("Error al conectar con el servidor");
  }
}

async function actualizarPrioridad(idTarea) {
  const prioridad = document.getElementById(`prioridad-${idTarea}`).value;

  const confirmar = confirm("Desea actualizar la prioridad de esta tarea?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/prioridad`, {
      method: "PUT",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ prioridad })
    });

    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "No se pudo actualizar la prioridad");
      return;
    }

    alert(data.message);
    cargarTareasPendientes();

  } catch (error) {
    console.error(error);
    alert("Error al conectar con el servidor");
  }
}

function formatearEstado(estado) {
  const estados = {
    PENDIENTE: "Pendiente",
    EN_PROCESO: "En proceso",
    EN_REVISION: "En revisión",
    COMPLETADA: "Completada",
    CANCELADA: "Cancelada"
  };

  return estados[estado] || estado;
}

function formatearPrioridad(prioridad) {
  const prioridades = {
    BAJA: "Baja",
    MEDIA: "Media",
    ALTA: "Alta",
    URGENTE: "Urgente"
  };

  return prioridades[prioridad] || prioridad;
}

function formatearFecha(fecha) {
  if (!fecha) {
    return "Sin fecha";
  }

  return new Date(fecha).toLocaleDateString("es-CL");
}
