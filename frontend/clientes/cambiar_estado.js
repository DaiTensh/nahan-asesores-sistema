const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", async () => {
    const txtRazonSocial = document.getElementById("txtRazonSocial");
    const txtRut = document.getElementById("txtRut");
    const badgeEstado = document.getElementById("badgeEstado");
    const btnCambiarEstado = document.getElementById("btnCambiarEstado");
    const btnVolver = document.getElementById("btnVolver");
    const mensaje = document.getElementById("mensajeFeedback");

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get("id");
    const usuario = JSON.parse(localStorage.getItem("usuario")) || {};

    let estadoActual = "";

    function mostrarMensaje(texto, tipo) {
        mensaje.textContent = texto;
        mensaje.className = `mensaje ${tipo}`;
    }

    function bloquearAccion(texto) {
        btnCambiarEstado.disabled = true;
        btnCambiarEstado.textContent = texto;
    }

    async function cargarEstadoCliente() {
        if (!idCliente) {
            txtRazonSocial.textContent = "Cliente no seleccionado";
            txtRut.textContent = "-";
            badgeEstado.textContent = "-";
            bloquearAccion("Sin cliente");
            mostrarMensaje("No se recibió un cliente válido desde el listado.", "error");
            return;
        }

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}`);
            const cliente = await respuesta.json();

            if (!respuesta.ok) {
                bloquearAccion("No disponible");
                mostrarMensaje(cliente.error || "No se pudo cargar el cliente.", "error");
                return;
            }

            txtRazonSocial.textContent = cliente.razon_social;
            txtRut.textContent = cliente.rut;
            estadoActual = cliente.estado || "ACTIVO";

            badgeEstado.textContent = estadoActual;
            badgeEstado.className = `indicador-estado-actual ${estadoActual.toLowerCase()}`;

            btnCambiarEstado.disabled = false;

            if (estadoActual === "ACTIVO") {
                btnCambiarEstado.textContent = "Desactivar cliente";
                btnCambiarEstado.className = "btn-cambiar-accion bg-rojo";
            } else {
                btnCambiarEstado.textContent = "Reactivar cliente";
                btnCambiarEstado.className = "btn-cambiar-accion bg-azul";
            }
        } catch (error) {
            console.error(error);
            bloquearAccion("No disponible");
            mostrarMensaje("Error de conexión al cargar el estado del cliente.", "error");
        }
    }

    btnCambiarEstado.addEventListener("click", async () => {
        mensaje.className = "mensaje";

        const nuevoEstado = estadoActual === "ACTIVO" ? "INACTIVO" : "ACTIVO";
        const confirmado = confirm(`¿Confirma cambiar el estado del cliente a ${nuevoEstado}?`);

        if (!confirmado) return;

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}/cambiar-estado`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    nuevo_estado: nuevoEstado,
                    id_usuario_auditoria: usuario.id_usuario || 1
                })
            });

            const resultado = await respuesta.json();

            if (!respuesta.ok) {
                mostrarMensaje(resultado.error || "No se pudo actualizar el estado.", "error");
                return;
            }

            mostrarMensaje(resultado.message || `Estado actualizado a ${nuevoEstado}.`, "success");
            await cargarEstadoCliente();
        } catch (error) {
            console.error(error);
            mostrarMensaje("Error de red al procesar el cambio de estado.", "error");
        }
    });

    btnVolver.addEventListener("click", () => {
        window.location.href = "listar_clientes.html";
    });

    await cargarEstadoCliente();
});
