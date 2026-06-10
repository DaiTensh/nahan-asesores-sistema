document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('formRegistroCliente');
    const mensaje = document.getElementById('mensajeFeedback');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        mensaje.className = 'mensaje';
        mensaje.style.display = 'none';

        const checkLegal = document.getElementById('checkLegal').checked;
        const checkContable = document.getElementById('checkContable').checked;

        // Validación obligatoria: elegir al menos una área
        if (!checkLegal && !checkContable) {
            mensaje.textContent = "❌ Error: Debe asignar el cliente a al menos un área (Legal o Contable).";
            mensaje.className = "mensaje error";
            return;
        }

        // Guardamos los IDs de las áreas seleccionadas (Coinciden con los IDs insertados en tu DB)
        const areasSeleccionadas = [];
        if (checkLegal) areasSeleccionadas.push(1);    // 1 = JURIDICA
        if (checkContable) areasSeleccionadas.push(2); // 2 = CONTABLE

        const payload = {
            rut: document.getElementById('rut').value.trim(),
            razon_social: document.getElementById('razon_social').value.trim(),
            direccion: document.getElementById('direccion').value.trim(),
            telefono: document.getElementById('telefono').value.trim(),
            email: document.getElementById('email').value.trim(),
            areas: areasSeleccionadas
        };

        try {
            const respuesta = await fetch('http://localhost:5000/api/clientes', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const resultado = await respuesta.json();

            if (respuesta.ok) {
                mensaje.textContent = "✔ El cliente ha sido guardado exitosamente en la plataforma.";
                mensaje.className = "mensaje success";
                form.reset();
            } else {
                mensaje.textContent = `❌ Error: ${resultado.error || 'No se pudo completar el registro.'}`;
                mensaje.className = "mensaje error";
            }
        } catch (error) {
            console.error(error);
            mensaje.textContent = "❌ Error: No hay respuesta por parte del servidor Flask.";
            mensaje.className = "mensaje error";
        }
    });
});