const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  const btnPrepararGuardado = document.getElementById("btnPrepararGuardado");
  const panelConfirmacion = document.getElementById("panelConfirmacion");
  const listaCambios = document.getElementById("listaCambios");
  const btnConfirmarFinal = document.getElementById("btnConfirmarFinal");
  const btnCancelarConfirmacion = document.getElementById("btnCancelarConfirmacion");
  const mensaje = document.getElementById("mensajeFeedback");
  const parametrosUrl = new URLSearchParams(window.location.search);
  const idCliente = parametrosUrl.get("id");

  let datosOriginales = {};

  cargarCliente();

  btnPrepararGuardado.addEventListener("click", prepararConfirmacion);
  btnConfirmarFinal.addEventListener("click", guardarCambios);
  btnCancelarConfirmacion.addEventListener("click", () => {
    panelConfirmacion.classList.remove("visible");
  });

  async function cargarCliente() {
    if (!idCliente) {
      bloquearFormulario("Sin cliente");
      mostrarMensaje("No se recibió un cliente válido desde el listado.", "error");
      return;
    }

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}`);
      const cliente = await response.json();

      if (!response.ok) {
        bloquearFormulario("No disponible");
        mostrarMensaje(cliente.error || "No se pudo cargar el cliente.", "error");
        return;
      }

      document.getElementById("rut").value = cliente.rut;
      document.getElementById("direccion").value = cliente.direccion || "";
      document.getElementById("razon_social").value = cliente.razon_social;
      document.getElementById("telefono").value = cliente.telefono || "";
      document.getElementById("email").value = cliente.email || "";

      const areas = cliente.areas || [];
      document.getElementById("checkLegal").checked = areas.includes(1);
      document.getElementById("checkContable").checked = areas.includes(2);

      datosOriginales = obtenerDatosFormulario();
    } catch (error) {
      console.error(error);
      bloquearFormulario("No disponible");
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  function prepararConfirmacion() {
    mensaje.textContent = "";
    mensaje.className = "mensaje";
    listaCambios.innerHTML = "";

    const datosActuales = obtenerDatosFormulario();
    const nombresCampos = {
      direccion: "Dirección",
      razon_social: "Razón Social",
      telefono: "Teléfono",
      email: "Correo",
      areas: "Áreas"
    };

    Object.keys(datosActuales).forEach(campo => {
      if (datosActuales[campo] !== datosOriginales[campo]) {
        const item = document.createElement("li");
        item.textContent = nombresCampos[campo];
        listaCambios.appendChild(item);
      }
    });

    if (listaCambios.children.length === 0) {
      mostrarMensaje("No se detectaron cambios para guardar.", "error");
      return;
    }

    panelConfirmacion.classList.add("visible");
  }

  async function guardarCambios() {
    const areas = obtenerAreasSeleccionadas();

    if (areas.length === 0) {
      mostrarMensaje("Debe asignar el cliente a al menos un área.", "error");
      return;
    }

    const payload = {
      direccion: document.getElementById("direccion").value.trim(),
      razon_social: document.getElementById("razon_social").value.trim(),
      telefono: document.getElementById("telefono").value.trim(),
      email: document.getElementById("email").value.trim(),
      areas
    };

    try {
      const response = await fetch(`${API_URL}/clientes/${idCliente}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        mostrarMensaje(data.error || "No se pudieron guardar los cambios.", "error");
        return;
      }

      mostrarMensaje(data.message || "Cliente actualizado correctamente.", "success");
      panelConfirmacion.classList.remove("visible");
      datosOriginales = obtenerDatosFormulario();

      setTimeout(() => {
        window.location.href = "listar_clientes.html";
      }, 1200);
    } catch (error) {
      console.error(error);
      mostrarMensaje("Error al conectar con el servidor.", "error");
    }
  }

  function obtenerDatosFormulario() {
    return {
      direccion: document.getElementById("direccion").value.trim(),
      razon_social: document.getElementById("razon_social").value.trim(),
      telefono: document.getElementById("telefono").value.trim(),
      email: document.getElementById("email").value.trim(),
      areas: obtenerAreasSeleccionadas().sort().toString()
    };
  }

  function obtenerAreasSeleccionadas() {
    const areas = [];

    if (document.getElementById("checkLegal").checked) areas.push(1);
    if (document.getElementById("checkContable").checked) areas.push(2);

    return areas;
  }

  function bloquearFormulario(texto) {
    btnPrepararGuardado.disabled = true;
    btnPrepararGuardado.textContent = texto;
  }

  function mostrarMensaje(texto, tipo) {
    mensaje.textContent = texto;
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }
});
