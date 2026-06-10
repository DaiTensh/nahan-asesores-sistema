const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", async () => {
    const btnConfirmarDeshabilitar = document.getElementById("btnConfirmarDeshabilitar");
    const btnVolver = document.getElementById("btnVolver");
    const txtRut = document.getElementById("resumenRut");
    const txtNombre = document.getElementById("resumenNombre");
    const txtAlertaText = document.querySelector(".modal-alert-text");
    const mensaje = document.getElementById("mensajeFeedback");

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get("id");
    const usuario = JSON.parse(localStorage.getItem("usuario")) || {};

    let puedeEliminarDefinitivo = false;

    function mostrarMensaje(texto, tipo) {
        mensaje.textContent = texto;
        mensaje.className = `mensaje ${tipo}`;
    }

    function bloquearAccion(texto) {
        btnConfirmarDeshabilitar.disabled = true;
        btnConfirmarDeshabilitar.textContent = texto;
    }

    async function cargarVerificacion() {
        if (!idCliente) {
            txtRut.textContent = "-";
            txtNombre.textContent = "Cliente no seleccionado";
            bloquearAccion("Sin cliente");
            mostrarMensaje("No se recibió un cliente válido desde el listado.", "error");
            return;
        }

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}/verificar-vinculos`);
            const data = await respuesta.json();

            if (!respuesta.ok) {
                bloquearAccion("No disponible");
                mostrarMensaje(data.error || "No se pudo verificar el expediente.", "error");
                return;
            }

            txtRut.textContent = data.rut;
            txtNombre.textContent = data.razon_social;

            if (data.tiene_vinculos) {
                puedeEliminarDefinitivo = false;
                txtAlertaText.innerHTML = `
                    <strong>Deshabilitación disponible.</strong> Este cliente posee ${data.tareas_activas} tareas vigentes o documentos activos. Por integridad, se mantendrá el registro y quedará INACTIVO.
                `;
                btnConfirmarDeshabilitar.textContent = "Deshabilitar cliente";
            } else {
                puedeEliminarDefinitivo = true;
                txtAlertaText.innerHTML = `
                    <strong>Eliminación definitiva disponible.</strong> Este cliente no posee tareas activas ni documentos pendientes.
                `;
                btnConfirmarDeshabilitar.textContent = "Eliminar definitivamente";
            }
        } catch (error) {
            console.error(error);
            bloquearAccion("No disponible");
            mostrarMensaje("Error de red al consultar el estado del cliente.", "error");
        }
    }

    btnConfirmarDeshabilitar.addEventListener("click", async () => {
        mensaje.className = "mensaje";

        const accionTexto = puedeEliminarDefinitivo ? "eliminar definitivamente" : "deshabilitar";
        const confirmado = confirm(`¿Está seguro de que desea ${accionTexto} este cliente?`);

        if (!confirmado) return;

        const urlEndpoint = puedeEliminarDefinitivo
            ? `${API_URL}/clientes/${idCliente}/eliminar-definitivo`
            : `${API_URL}/clientes/${idCliente}/deshabilitar`;

        const metodoHttp = puedeEliminarDefinitivo ? "DELETE" : "PATCH";

        try {
            const respuesta = await fetch(urlEndpoint, {
                method: metodoHttp,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id_usuario_auditoria: usuario.id_usuario || 1 })
            });

            const resultado = await respuesta.json();

            if (!respuesta.ok) {
                mostrarMensaje(resultado.error || "No se pudo procesar la acción.", "error");
                return;
            }

            mostrarMensaje(resultado.message || "Acción completada correctamente.", "success");
            bloquearAccion("Acción completada");

            setTimeout(() => {
                window.location.href = "listar_clientes.html";
            }, 1500);
        } catch (error) {
            console.error(error);
            mostrarMensaje("Error de red al procesar la solicitud.", "error");
        }
    });

    btnVolver.addEventListener("click", () => {
        window.location.href = "listar_clientes.html";
    });

    await cargarVerificacion();
});
