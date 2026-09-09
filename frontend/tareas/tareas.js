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

const EXTENSIONES_ADJUNTOS_AVISO = "pdf, doc, docx, xls, xlsx, ppt, pptx, jpg, jpeg, png";

let tareasCache = [];
const tareasSeleccionadas = new Set();

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

  UsuariosAutocomplete.configurarSelectorUsuario({
    inputId: "redistribuir_destino_busqueda",
    hiddenId: "redistribuir_destino_id",
    datalistId: "usuarios_redistribuir_destino",
    soloActivos: true
  });

  document.getElementById("seleccionarTodas").addEventListener("change", alternarSeleccionarTodas);
  document.getElementById("btnVerCarga").addEventListener("click", mostrarCargaTrabajo);
  document.getElementById("btnRedistribuir").addEventListener("click", redistribuirSeleccionadas);

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

    tareasCache = tareas;

    const idsVisibles = new Set(tareas.map(tarea => Number(tarea.id_tarea)));
    for (const id of tareasSeleccionadas) {
      if (!idsVisibles.has(id)) tareasSeleccionadas.delete(id);
    }

    actualizarResumen(tareas);
    renderizarTabla(tareas, usuario);
    actualizarBarraRedistribucion(usuario);

  } catch (error) {
    console.error(error);
  }
}

function actualizarBarraRedistribucion(usuario) {
  const barra = document.getElementById("redistribuirBar");
  barra.hidden = usuario.nombre_rol !== "ADMINISTRADOR";

  const contador = document.getElementById("redistribuirContador");
  contador.textContent = `${tareasSeleccionadas.size} tarea(s) seleccionada(s)`;
  document.getElementById("redistribuirCarga").textContent = "";
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
    celdaVacia.colSpan = 10;
    celdaVacia.textContent = "No hay tareas pendientes para mostrar.";
    filaVacia.appendChild(celdaVacia);
    tablaTareas.appendChild(filaVacia);
    return;
  }

  const puedeAdministrar = usuario.nombre_rol === "ADMINISTRADOR";

  tareas.forEach(tarea => {
    const idTarea = Number(tarea.id_tarea);
    const fila = document.createElement("tr");

    const celdaSeleccion = document.createElement("td");
    if (puedeAdministrar) {
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = tareasSeleccionadas.has(idTarea);
      checkbox.addEventListener("change", () => alternarSeleccionTarea(idTarea, checkbox.checked, usuario));
      celdaSeleccion.appendChild(checkbox);
    }
    fila.appendChild(celdaSeleccion);

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
    tablaTareas.appendChild(crearFilaAdjuntos(idTarea));
  });
}

function alternarSeleccionarTodas(event) {
  const marcar = event.target.checked;

  tareasSeleccionadas.clear();
  if (marcar) {
    tareasCache.forEach(tarea => tareasSeleccionadas.add(Number(tarea.id_tarea)));
  }

  obtenerUsuarioActual().then(usuario => {
    renderizarTabla(tareasCache, usuario);
    actualizarBarraRedistribucion(usuario);
  });
}

function alternarSeleccionTarea(idTarea, marcada, usuario) {
  if (marcada) {
    tareasSeleccionadas.add(idTarea);
  } else {
    tareasSeleccionadas.delete(idTarea);
  }

  actualizarBarraRedistribucion(usuario);
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

  const botonAdjuntos = document.createElement("button");
  botonAdjuntos.className = "btn btn-secondary btn-small";
  botonAdjuntos.textContent = "Adjuntos";
  botonAdjuntos.addEventListener("click", () => alternarPanelAdjuntos(tarea.id_tarea));
  contenedor.appendChild(botonAdjuntos);

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

// --- RF54/RF55 — Adjuntos de tarea ---------------------------------------

function crearFilaAdjuntos(idTarea) {
  const fila = document.createElement("tr");
  fila.id = `adjuntos-fila-${idTarea}`;
  fila.className = "adjuntos-fila";
  fila.hidden = true;

  const celda = document.createElement("td");
  celda.colSpan = 10;

  const panel = document.createElement("div");
  panel.className = "adjuntos-panel";

  const lista = document.createElement("ul");
  lista.className = "adjuntos-lista";
  lista.id = `adjuntos-lista-${idTarea}`;
  panel.appendChild(lista);

  const form = document.createElement("form");
  form.className = "adjuntos-form";

  const input = document.createElement("input");
  input.type = "file";
  input.id = `adjuntos-input-${idTarea}`;
  form.appendChild(input);

  const botonSubir = document.createElement("button");
  botonSubir.type = "submit";
  botonSubir.className = "btn btn-primary btn-small";
  botonSubir.textContent = "Adjuntar archivo";
  form.appendChild(botonSubir);

  const aviso = document.createElement("span");
  aviso.className = "mensaje";
  aviso.id = `adjuntos-mensaje-${idTarea}`;
  form.appendChild(aviso);

  form.addEventListener("submit", event => {
    event.preventDefault();
    subirAdjunto(idTarea, input, aviso);
  });

  panel.appendChild(form);

  const ayuda = document.createElement("p");
  ayuda.className = "redistribuir-carga";
  ayuda.textContent = `Extensiones permitidas: ${EXTENSIONES_ADJUNTOS_AVISO}.`;
  panel.appendChild(ayuda);

  celda.appendChild(panel);
  fila.appendChild(celda);

  return fila;
}

async function alternarPanelAdjuntos(idTarea) {
  const fila = document.getElementById(`adjuntos-fila-${idTarea}`);

  if (!fila) return;

  fila.hidden = !fila.hidden;

  if (!fila.hidden) {
    await cargarAdjuntos(idTarea);
  }
}

async function cargarAdjuntos(idTarea) {
  const lista = document.getElementById(`adjuntos-lista-${idTarea}`);
  lista.textContent = "";

  const itemCargando = document.createElement("li");
  itemCargando.textContent = "Cargando adjuntos...";
  lista.appendChild(itemCargando);

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/documentos`, {
      credentials: window.API_CONFIG.credentials
    });
    const documentos = await response.json();

    lista.textContent = "";

    if (!response.ok) {
      const itemError = document.createElement("li");
      itemError.textContent = documentos.error || "No se pudieron cargar los adjuntos";
      lista.appendChild(itemError);
      return;
    }

    if (documentos.length === 0) {
      const itemVacio = document.createElement("li");
      itemVacio.textContent = "Esta tarea todavía no tiene archivos adjuntos.";
      lista.appendChild(itemVacio);
      return;
    }

    documentos.forEach(documento => {
      lista.appendChild(crearItemAdjunto(documento));
    });

  } catch (error) {
    console.error(error);
    lista.textContent = "";
    const itemError = document.createElement("li");
    itemError.textContent = "Error al conectar con el servidor";
    lista.appendChild(itemError);
  }
}

function crearItemAdjunto(documento) {
  const item = document.createElement("li");
  item.className = "adjuntos-item";

  const nombre = document.createElement("span");
  nombre.className = "nombre";
  nombre.textContent = documento.nombre_documento;
  item.appendChild(nombre);

  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = `subido por ${documento.subido_por} — ${formatearFecha(documento.fecha_subida)}`;
  item.appendChild(meta);

  const botonDescargar = document.createElement("button");
  botonDescargar.type = "button";
  botonDescargar.className = "btn btn-secondary btn-small";
  botonDescargar.textContent = "Descargar";
  botonDescargar.addEventListener("click", () => descargarAdjunto(documento.id_documento, documento.nombre_documento));
  item.appendChild(botonDescargar);

  return item;
}

async function subirAdjunto(idTarea, input, aviso) {
  if (!input.files || input.files.length === 0) {
    aviso.textContent = "Seleccione un archivo";
    aviso.className = "mensaje error";
    return;
  }

  const datosFormulario = new FormData();
  datosFormulario.append("archivo", input.files[0]);

  aviso.textContent = "Subiendo...";
  aviso.className = "mensaje";

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/documentos`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      body: datosFormulario
    });

    const data = await response.json();

    if (!response.ok) {
      aviso.textContent = data.error || "No se pudo adjuntar el archivo";
      aviso.className = "mensaje error";
      return;
    }

    aviso.textContent = "Archivo adjuntado correctamente";
    aviso.className = "mensaje success";
    input.value = "";
    await cargarAdjuntos(idTarea);

  } catch (error) {
    console.error(error);
    aviso.textContent = "Error al conectar con el servidor";
    aviso.className = "mensaje error";
  }
}

async function descargarAdjunto(idDocumento, nombreDocumento) {
  try {
    const response = await fetch(`${API_URL}/documentos/${idDocumento}/descargar`, {
      credentials: window.API_CONFIG.credentials
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      alert(data.error || "No se pudo descargar el archivo");
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombreDocumento;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    window.URL.revokeObjectURL(url);

  } catch (error) {
    console.error(error);
    alert("Error al conectar con el servidor");
  }
}

// --- RF19 — Reasignando y Redistribuyendo Tareas --------------------------

async function obtenerDestinoSeleccionado() {
  const usuario = await UsuariosAutocomplete.obtenerUsuarioSeleccionado(
    "redistribuir_destino_busqueda",
    { soloActivos: true }
  );

  return usuario ? Number(usuario.id_usuario) : null;
}

async function mostrarCargaTrabajo() {
  const contenedor = document.getElementById("redistribuirCarga");

  if (tareasSeleccionadas.size === 0) {
    contenedor.textContent = "Seleccione al menos una tarea";
    return;
  }

  const idsOrigen = new Set();
  tareasCache.forEach(tarea => {
    if (tareasSeleccionadas.has(Number(tarea.id_tarea))) {
      idsOrigen.add(Number(tarea.id_responsable));
    }
  });

  const idDestino = await obtenerDestinoSeleccionado();
  const idsConsulta = new Set(idsOrigen);
  if (idDestino) idsConsulta.add(idDestino);

  if (idsConsulta.size === 0) {
    contenedor.textContent = "";
    return;
  }

  try {
    const response = await fetch(
      `${API_URL}/tareas/carga?ids_usuario=${Array.from(idsConsulta).join(",")}`,
      { credentials: window.API_CONFIG.credentials }
    );
    const carga = await response.json();

    if (!response.ok) {
      contenedor.textContent = carga.error || "No se pudo consultar la carga";
      return;
    }

    const partes = Array.from(idsConsulta).map(id => {
      const etiqueta = idDestino && id === idDestino ? "destino" : "origen";
      return `usuario ${id} (${etiqueta}): ${carga[id] ?? 0} tarea(s)`;
    });

    contenedor.textContent = partes.join(" · ");

  } catch (error) {
    console.error(error);
    contenedor.textContent = "Error al conectar con el servidor";
  }
}

async function redistribuirSeleccionadas() {
  if (tareasSeleccionadas.size === 0) {
    alert("Seleccione al menos una tarea");
    return;
  }

  const idResponsable = await obtenerDestinoSeleccionado();

  if (!idResponsable) {
    alert("Seleccione un responsable de destino de la lista");
    return;
  }

  await mostrarCargaTrabajo();

  const confirmar = confirm(
    `Desea reasignar ${tareasSeleccionadas.size} tarea(s) seleccionada(s) al responsable indicado?`
  );

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/reasignar-masivo`, {
      method: "PUT",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        ids_tarea: Array.from(tareasSeleccionadas),
        id_responsable: idResponsable
      })
    });

    const data = await response.json();

    if (!response.ok) {
      alert(data.error || "No se pudieron reasignar las tareas");
      return;
    }

    alert(data.message);
    tareasSeleccionadas.clear();
    cargarTareasPendientes();

  } catch (error) {
    console.error(error);
    alert("Error al conectar con el servidor");
  }
}
