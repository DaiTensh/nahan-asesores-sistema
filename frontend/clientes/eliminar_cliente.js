document.addEventListener('DOMContentLoaded', async () => {
    const btnConfirmarDeshabilitar = document.getElementById('btnConfirmarDeshabilitar');
    const btnVolver = document.getElementById('btnVolver');
    const txtRut = document.getElementById('resumenRut');
    const txtNombre = document.getElementById('resumenNombre');
    const txtAlertaText = document.querySelector('.modal-alert-text');
    const mensaje = document.getElementById('mensajeFeedback');

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get('id') || 1;

    let puedeEliminarDefinitivo = false;

    // 1. CARGA INICIAL: Validar el estado de los vínculos del cliente en tiempo real
    try {
        const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}/verificar-vinculos`);
        if (respuesta.ok) {
            const data = await respuesta.json();
            txtRut.textContent = data.rut;
            txtNombre.textContent = data.razon_social;
            
            if (data.tiene_vinculos) {
                // Regla de negocio: Posee vínculos activos, solo ofrece deshabilitar
                puedeEliminarDefinitivo = false;
                txtAlertaText.innerHTML = `
                    ⚠️ <strong>Opción Única: Deshabilitación.</strong> Este cliente posee <strong>${data.tareas_activas} tareas vigentes</strong> o documentos en revisión. Por integridad legal, el sistema solo permite deshabilitarlo para congelar la creación de nuevas tareas.
                `;
                btnConfirmarDeshabilitar.textContent = "Deshabilitar cliente (Borrado Lógico)";
            } else {
                // Cliente limpio: Se permite la remoción completa del registro activo
                puedeEliminarDefinitivo = true;
                txtAlertaText.innerHTML = `
                    ✔ <strong>Eliminación Definitiva Permitida.</strong> Este cliente no posee tareas activas ni documentos pendientes. Puede proceder a borrarlo completamente del registro del sistema.
                `;
                btnConfirmarDeshabilitar.textContent = "Eliminar definitivamente (Borrado Físico)";
            }
        } else {
            mensaje.textContent = "❌ Error: No se pudo verificar el estado del expediente.";
            mensaje.className = "mensaje error";
            btnConfirmarDeshabilitar.disabled = true;
        }
    } catch (error) {
        console.error(error);
        mensaje.textContent = "❌ Error de red al consultar el estado del cliente.";
        mensaje.className = "mensaje error";
    }

    // 2. DISPARAR ACCIÓN (Rutea a PATCH o a DELETE según la regla de negocio)
    btnConfirmarDeshabilitar.addEventListener('click', async () => {
        mensaje.className = 'mensaje';
        mensaje.style.display = 'none';

        const accionTexto = puedeEliminarDefinitivo ? 'ELIMINAR DEFINITIVAMENTE' : 'DESHABILITAR';
        if (!confirm(`¿Está seguro de que desea ${accionTexto} este cliente? Esta acción quedará registrada en el historial de auditoría.`)) {
            return;
        }

        // Seleccionamos dinámicamente el endpoint y el método HTTP
        const urlEndpoint = puedeEliminarDefinitivo 
            ? `http://localhost:5000/api/clientes/${idCliente}/eliminar-definitivo`
            : `http://localhost:5000/api/clientes/${idCliente}/deshabilitar`;
        
        const metodoHttp = puedeEliminarDefinitivo ? 'DELETE' : 'PATCH';

        try {
            const respuesta = await fetch(urlEndpoint, {
                method: metodoHttp,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id_usuario_auditoria: 1 }) // Simulamos id_usuario=1 (Administrador) para la auditoría
            });

            if (respuesta.ok) {
                mensaje.textContent = puedeEliminarDefinitivo 
                    ? "✔ El cliente ha sido eliminado definitivamente del registro activo."
                    : "✔ El cliente ha sido deshabilitado con éxito (Estado: INACTIVO).";
                mensaje.className = "mensaje success";
                btnConfirmarDeshabilitar.disabled = true;
                
                setTimeout(() => { window.location.href = 'listar_clientes.html'; }, 2500);
            } else {
                const err = await respuesta.json();
                mensaje.textContent = `❌ Error: ${err.error}`;
                mensaje.className = "mensaje error";
            }
        } catch (error) {
            mensaje.textContent = "❌ Error de red al procesar la solicitud.";
            mensaje.className = "mensaje error";
        }
    });

    btnVolver.addEventListener('click', () => { window.location.href = 'listar_clientes.html'; });
});