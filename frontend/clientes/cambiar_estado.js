document.addEventListener('DOMContentLoaded', async () => {
    const txtRazonSocial = document.getElementById('txtRazonSocial');
    const txtRut = document.getElementById('txtRut');
    const badgeEstado = document.getElementById('badgeEstado');
    const btnCambiarEstado = document.getElementById('btnCambiarEstado');
    const btnVolver = document.getElementById('btnVolver');
    const mensaje = document.getElementById('mensajeFeedback');

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get('id') || 1;

    let estadoActual = "ACTIVO";

    // 1. CARGA INICIAL: Consultar estado actual del cliente
    const cargarEstadoCliente = async () => {
        try {
            const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}`);
            if (respuesta.ok) {
                const cliente = await respuesta.json();
                
                txtRazonSocial.textContent = cliente.razon_social;
                txtRut.textContent = cliente.rut;
                estadoActual = cliente.estado || "ACTIVO";

                // Renderizado condicional del badge píldora
                badgeEstado.textContent = estadoActual;
                badgeEstado.className = `indicador-estado-actual ${estadoActual.toLowerCase()}`;

                // Adaptar el botón de acción según la paleta oficial corporativa
                if (estadoActual === "ACTIVO") {
                    btnCambiarEstado.textContent = "Desactivar Cuenta";
                    btnCambiarEstado.className = "btn-cambiar-accion bg-rojo";
                } else {
                    btnCambiarEstado.textContent = "Reactivar Cuenta";
                    btnCambiarEstado.className = "btn-cambiar-accion bg-azul";
                }
            }
        } catch (error) {
            console.error("Error al rescatar estado:", error);
        }
    };

    // 2. DISPARAR CONMUTACIÓN (POST)
    btnCambiarEstado.addEventListener('click', async () => {
        mensaje.className = 'mensaje';
        mensaje.style.display = 'none';

        const nuevoEstado = (estadoActual === "ACTIVO") ? "INACTIVO" : "ACTIVO";

        if (!confirm(`¿Confirma que desea cambiar el estado operativo del cliente a ${nuevoEstado}? El cambio quedará registrado en auditoría.`)) {
            return;
        }

        try {
            const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}/cambiar-estado`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    nuevo_estado: nuevoEstado,
                    id_usuario_auditoria: 1 // Simulamos ID del Administrador operativo
                })
            });

            if (respuesta.ok) {
                mensaje.textContent = `✔ Estado actualizado con éxito a ${nuevoEstado}.`;
                mensaje.className = "mensaje success";
                
                // Refrescar el componente para actualizar la UI
                await cargarEstadoCliente();
            } else {
                const err = await respuesta.json();
                mensaje.textContent = `❌ Error: ${err.error}`;
                mensaje.className = "mensaje error";
            }
        } catch (error) {
            mensaje.textContent = "❌ Error de red al procesar el cambio de estado.";
            mensaje.className = "mensaje error";
        }
    });

    btnVolver.addEventListener('click', () => {
        window.location.href = 'listar_clientes.html';
    });

    // Ejecutar inicialización
    await cargarEstadoCliente();
});