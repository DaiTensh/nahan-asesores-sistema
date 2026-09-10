const API_URL = window.API_CONFIG.API_URL;

const ESTADOS_FINALES = ["COMPLETADA", "CANCELADA"];

let tareaActual = null;

document.addEventListener("DOMContentLoaded", async () => {
  const idTarea = new URLSearchParams(window.location.search).get("id");

  if (!idTarea) {
    mostrarMensaje("No se recibió una tarea válida desde el listado.", "error");
    return;
  }

  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  await UsuariosAutocomplete.configurarSelectorUsuario({
    inputId: "responsable_busqueda",
    hiddenId: "id_responsable",
    datalistId: "usuarios_responsables",
    soloActivos: true
  });

  await cargarTarea(idTarea);

  document.getElementById("formEditarTarea").addEventListener("submit", event => {
    event.preventDefault();
    guardarCambios(idTarea);
  });
});

async function cargarTarea(idTarea) {
  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}`, {
      credentials: window.API_CONFIG.credentials
    });
    const tarea = await response.json();

    if (response.status === 401) {
      window.location.href = "../auth/login.html";
      return;
    }

    if (!response.ok) {
      mostrarMensaje(tarea.error || "No fue posible cargar la tarea.", "error");
      return;
    }

    if (ESTADOS_FINALES.includes(tarea.estado)) {
      mostrarMensaje(
        "Esta tarea está COMPLETADA o CANCELADA y ya no se puede editar.",
        "error"
      );
      return;
    }

    tareaActual = tarea;

    document.getElementById("titulo").value = tarea.titulo || "";
    document.getElementById("descripcion").value = tarea.descripcion || "";
    document.getElementById("prioridad").value = tarea.prioridad;
    document.getElementById("fecha_vencimiento").value = aFechaInput(tarea.fecha_vencimiento);

    await prellenarResponsable(tarea.id_responsable, tarea.responsable);

    document.getElementById("editarSeccion").hidden = false;

  } catch (error) {
    console.error(error);
    mostrarMensaje("Error al conectar con el servidor.", "error");
  }
}

async function prellenarResponsable(idResponsable, nombreResponsable) {
  try {
    const response = await fetch(`${API_URL}/usuarios`, {
      credentials: window.API_CONFIG.credentials
    });
    const usuarios = await response.json();

    if (!response.ok) return;

    const responsable = usuarios.find(u => Number(u.id_usuario) === Number(idResponsable));

    if (responsable) {
      UsuariosAutocomplete.mostrarUsuarioEnInput("responsable_busqueda", "id_responsable", responsable);
    } else {
      document.getElementById("responsable_busqueda").value = nombreResponsable || "";
      document.getElementById("id_responsable").value = idResponsable;
    }
  } catch (error) {
    console.error(error);
  }
}

async function guardarCambios(idTarea) {
  const titulo = document.getElementById("titulo").value.trim();

  if (!titulo) {
    mostrarMensajeGuardar("Ingrese un título", "error");
    return;
  }

  const responsable = await UsuariosAutocomplete.obtenerUsuarioSeleccionado(
    "responsable_busqueda",
    { soloActivos: true }
  );

  if (!responsable) {
    mostrarMensajeGuardar("Seleccione un responsable de la lista", "error");
    return;
  }

  const prioridad = document.getElementById("prioridad").value;
  const fechaVencimiento = document.getElementById("fecha_vencimiento").value || null;

  if (fechaVencimiento && tareaActual && tareaActual.fecha_creacion) {
    const fechaCreacion = aFechaInput(tareaActual.fecha_creacion);
    if (fechaVencimiento < fechaCreacion) {
      mostrarMensajeGuardar("La fecha de vencimiento no puede ser anterior a la fecha de creación", "error");
      return;
    }
  }

  const confirmar = confirm("Desea guardar los cambios de esta tarea?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}`, {
      method: "PUT",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        titulo,
        descripcion: document.getElementById("descripcion").value.trim(),
        id_responsable: Number(responsable.id_usuario),
        prioridad,
        fecha_vencimiento: fechaVencimiento
      })
    });

    const data = await response.json();

    if (!response.ok) {
      mostrarMensajeGuardar(data.error || "No se pudo guardar la tarea", "error");
      return;
    }

    window.location.href = `detalle_tarea.html?id=${idTarea}`;

  } catch (error) {
    console.error(error);
    mostrarMensajeGuardar("Error al conectar con el servidor", "error");
  }
}

function aFechaInput(fecha) {
  if (!fecha) return "";

  const valor = new Date(fecha);

  const anio = valor.getUTCFullYear();
  const mes = String(valor.getUTCMonth() + 1).padStart(2, "0");
  const dia = String(valor.getUTCDate()).padStart(2, "0");

  return `${anio}-${mes}-${dia}`;
}

function mostrarMensaje(texto, tipo) {
  const mensaje = document.getElementById("editarMensaje");
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}

function mostrarMensajeGuardar(texto, tipo) {
  const mensaje = document.getElementById("mensajeGuardar");
  mensaje.textContent = texto;
  mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
}
