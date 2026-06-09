const API_URL = "http://127.0.0.1:5000/api";

const formTarea = document.getElementById("formTarea");
const mensajeTarea = document.getElementById("mensajeTarea");
const tablaTareas = document.getElementById("tablaTareas");

document.addEventListener("DOMContentLoaded", () => {
  cargarTareasPendientes();
});

formTarea.addEventListener("submit", async (event) => {
  event.preventDefault();

  const usuario = JSON.parse(localStorage.getItem("usuario"));

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  const confirmar = confirm("Desea crear esta nueva tarea?");

  if (!confirmar) return;

  const nuevaTarea = {
    id_cliente: Number(document.getElementById("id_cliente").value),
    id_area: Number(document.getElementById("id_area").value),
    id_responsable: Number(document.getElementById("id_responsable").value),
    id_creador: usuario.id_usuario,
    titulo: document.getElementById("titulo").value.trim(),
    descripcion: document.getElementById("descripcion").value.trim(),
    prioridad: document.getElementById("prioridad").value,
    fecha_vencimiento: document.getElementById("fecha_vencimiento").value || null
  };

  try {
    const response = await fetch(`${API_URL}/tareas`, {
      method: "POST",
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
  const usuario = JSON.parse(localStorage.getItem("usuario"));

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  try {
    const response = await fetch(`${API_URL}/tareas/pendientes`);
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
  tablaTareas.innerHTML = "";

  if (tareas.length === 0) {
    tablaTareas.innerHTML = `
      <tr>
        <td colspan="9">No hay tareas pendientes para mostrar.</td>
      </tr>
    `;
    return;
  }

  tareas.forEach(tarea => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${tarea.id_tarea}</td>
      <td>${tarea.titulo}</td>
      <td>${tarea.cliente}</td>
      <td>${tarea.area}</td>
      <td>${tarea.responsable}</td>
      <td>
        <span class="badge estado-${tarea.estado.toLowerCase()}">
          ${formatearEstado(tarea.estado)}
        </span>
      </td>
      <td>
        <span class="badge prioridad-${tarea.prioridad.toLowerCase()}">
          ${formatearPrioridad(tarea.prioridad)}
        </span>
      </td>
      <td>${formatearFecha(tarea.fecha_vencimiento)}</td>
      <td>
        ${accionesTarea(tarea, usuario)}
      </td>
    `;

    tablaTareas.appendChild(fila);
  });
}

function accionesTarea(tarea, usuario) {
  const puedeAdministrar = usuario.nombre_rol === "ADMINISTRADOR";

  return `
    <div class="tareas-actions">
      ${
        puedeAdministrar
          ? `
            <input type="number" id="responsable-${tarea.id_tarea}" placeholder="ID Usuario">
            <button class="btn btn-primary btn-small" onclick="asignarTarea(${tarea.id_tarea})">
              Asignar
            </button>
          `
          : ""
      }

      <select id="estado-${tarea.id_tarea}">
        <option value="PENDIENTE">Pendiente</option>
        <option value="EN_PROCESO">En proceso</option>
        <option value="EN_REVISION">En revisión</option>
        <option value="COMPLETADA">Completada</option>
        <option value="CANCELADA">Cancelada</option>
      </select>

      <button class="btn btn-primary btn-small" onclick="actualizarEstado(${tarea.id_tarea})">
        Estado
      </button>

      <select id="prioridad-${tarea.id_tarea}">
        <option value="BAJA">Baja</option>
        <option value="MEDIA">Media</option>
        <option value="ALTA">Alta</option>
        <option value="URGENTE">Urgente</option>
      </select>

      <button class="btn btn-primary btn-small" onclick="actualizarPrioridad(${tarea.id_tarea})">
        Prioridad
      </button>
    </div>
  `;
}

async function asignarTarea(idTarea) {
  const idResponsable = document.getElementById(`responsable-${idTarea}`).value;

  if (!idResponsable) {
    alert("Debe ingresar el ID del responsable");
    return;
  }

  const confirmar = confirm("Desea asignar esta tarea a otro usuario?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/asignar`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        id_responsable: Number(idResponsable)
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

  const confirmar = confirm("Desea actualizar el estado de esta tarea?");

  if (!confirmar) return;

  try {
    const response = await fetch(`${API_URL}/tareas/${idTarea}/estado`, {
      method: "PUT",
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