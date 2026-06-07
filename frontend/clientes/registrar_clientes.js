document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('formRegistroCliente');
    const mensaje = document.getElementById('mensajeFeedback');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Limpiar estados previos de mensajes
        mensaje.className = 'mensaje';
        mensaje.style.display = 'none';

        // Capturamos el estado de los checkboxes de asignación de área
        const checkLegal = document.getElementById('checkLegal').checked;
        const checkContable = document.getElementById('checkContable').checked;

        // Validación obligatoria: Al menos un área seleccionada
        if (!checkLegal && !checkContable) {
            mensaje.textContent = "❌ Error: Debe asignar el cliente a al menos una de las áreas (Legal o Contable).";
            mensaje.className = "mensaje error";
            return;
        }

        // Definimos el string del área según la combinación de checks
        let areaAsignada = "";
        if (checkLegal && checkContable) areaAsignada = "Ambas";
        else if (checkLegal) areaAsignada = "Legal";
        else if (checkContable) areaAsignada = "Contable";

        // Mapeo exacto de los campos del formulario tabular
        const payload = {
            rut: document.getElementById('rut').value.trim(),
            direccion: document.getElementById('direccion').value.trim(),
            nombre_contacto_1: document.getElementById('nombre_contacto_1').value.trim(),
            nombre_contacto_2: document.getElementById('nombre_contacto_2').value.trim(),
            telefono: document.getElementById('telefono').value.trim(),
            email: document.getElementById('email').value.trim(),
            area: areaAsignada
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
                mensaje.textContent = "✔ El cliente ha sido guardado exitosamente en el sistema.";
                mensaje.className = "mensaje success";
                form.reset();
            } else {
                mensaje.textContent = `❌ Error: ${resultado.error || 'No se pudo completar el registro.'}`;
                mensaje.className = "mensaje error";
            }
        } catch (error) {
            console.error('Error detectado:', error);
            mensaje.textContent = "❌ Error: No hay respuesta del servidor backend Flask.";
            mensaje.className = "mensaje error";
        }
    });
});