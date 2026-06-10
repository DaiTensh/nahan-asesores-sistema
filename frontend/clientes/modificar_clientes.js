document.addEventListener('DOMContentLoaded', async () => {
    const form = document.getElementById('formModificarCliente');
    const btnDispararGuardado = document.getElementById('btnDispararGuardado');
    const panelConfirmacion = document.getElementById('panelConfirmacion');
    const flujoFlecha = document.getElementById('flujoFlecha');
    const listaCambios = document.getElementById('listaCambios');
    const btnConfirmarFinal = document.getElementById('btnConfirmarFinal');
    const btnVolver = document.getElementById('btnVolver');
    const mensaje = document.getElementById('mensajeFeedback');

    // Estructura de control para contrastar diferencias
    let datosOriginales = {};

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get('id') || 1; // Respaldo ID 1 para testing local

    // 1. CARGA INICIAL (GET) - Trae el registro actual desde MySQL
    try {
        const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}`);
        if (respuesta.ok) {
            const cliente = await respuesta.json();
            
            document.getElementById('rut').value = cliente.rut;
            document.getElementById('direccion').value = cliente.direccion || '';
            document.getElementById('razon_social').value = cliente.razon_social;
            document.getElementById('nombre_contacto_2').value = cliente.nombre_contacto_2 || '';
            document.getElementById('telefono').value = cliente.telefono || '';
            document.getElementById('email').value = cliente.email || '';

            // Mapeamos las áreas asociadas que vienen desde la tabla intermedia cliente_area
            if (cliente.areas.includes(1)) document.getElementById('checkLegal').checked = true;
            if (cliente.areas.includes(2)) document.getElementById('checkContable').checked = true;

            // Almacenamos el estado inicial exacto
            datosOriginales = {
                direccion: cliente.direccion || '',
                razon_social: cliente.razon_social,
                nombre_contacto_2: cliente.nombre_contacto_2 || '',
                telefono: cliente.telefono || '',
                email: cliente.email || '',
                areas: [...cliente.areas].sort().toString()
            };
        }
    } catch (error) {
        console.error("Error al cargar antecedentes:", error);
    }

    // 2. DETECTAR DIFERENCIAS Y DESPLEGAR PANEL INTERACTIVO
    btnDispararGuardado.addEventListener('click', () => {
        listaCambios.innerHTML = ""; // Reset de la lista
        
        const checkLegal = document.getElementById('checkLegal').checked;
        const checkContable = document.getElementById('checkContable').checked;
        
        const areasActuales = [];
        if (checkLegal) areasActuales.push(1);
        if (checkContable) areasActuales.push(2);

        const datosActuales = {
            direccion: document.getElementById('direccion').value.trim(),
            razon_social: document.getElementById('razon_social').value.trim(),
            nombre_contacto_2: document.getElementById('nombre_contacto_2').value.trim(),
            telefono: document.getElementById('telefono').value.trim(),
            email: document.getElementById('email').value.trim(),
            areas: areasActuales.sort().toString()
        };

        // Encontrar diferencias relativas
        let cambiosContador = 0;
        const traducciones = {
            direccion: "Direccion", razon_social: "Nombre contacto 1",
            nombre_contacto_2: "Nombre contacto 2", telefono: "Fono", email: "Correo", areas: "Áreas"
        };

        for (let key in datosActuales) {
            if (datosActuales[key] !== datosOriginales[key]) {
                cambiosContador++;
                const li = document.createElement('li');
                li.textContent = `Cambio ${cambiosContador}: ${traducciones[key]}`;
                listaCambios.appendChild(li);
            }
        }

        if (cambiosContador === 0) {
            alert("No se detectó ningún cambio en los campos respecto a los datos iniciales.");
            return;
        }

        // Levantar bloques laterales de Figma
        panelConfirmacion.style.display = "flex";
        flujoFlecha.style.display = "block";
    });

    // 3. CONFIRMAR Y GUARDAR (PUT)
    btnConfirmarFinal.addEventListener('click', async () => {
        mensaje.className = 'mensaje';
        mensaje.style.display = 'none';

        const checkLegal = document.getElementById('checkLegal').checked;
        const checkContable = document.getElementById('checkContable').checked;
        
        const areasActuales = [];
        if (checkLegal) areasActuales.push(1);
        if (checkContable) areasActuales.push(2);

        if (areasActuales.length === 0) {
            mensaje.textContent = "❌ Debe asignar el cliente a al menos un área.";
            mensaje.className = "mensaje error";
            return;
        }

        const payload = {
            direccion: document.getElementById('direccion').value.trim(),
            razon_social: document.getElementById('razon_social').value.trim(),
            nombre_contacto_2: document.getElementById('nombre_contacto_2').value.trim(),
            telefono: document.getElementById('telefono').value.trim(),
            email: document.getElementById('email').value.trim(),
            areas: areasActuales
        };

        try {
            const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (respuesta.ok) {
                mensaje.textContent = "✔ Cambios almacenados.";
                mensaje.className = "mensaje success";
                setTimeout(() => { window.location.href = 'listar_clientes.html'; }, 1500);
            } else {
                const err = await respuesta.json();
                mensaje.textContent = `❌ ${err.error}`;
                mensaje.className = "mensaje error";
            }
        } catch (error) {
            mensaje.textContent = "❌ Error de conexión.";
            mensaje.className = "mensaje error";
        }
    });

    // 4. BOTÓN VOLVER: Ocultar el panel
    btnVolver.addEventListener('click', () => {
        panelConfirmacion.style.display = "none";
        flujoFlecha.style.display = "none";
    });
});