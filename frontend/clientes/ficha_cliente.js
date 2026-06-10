document.addEventListener('DOMContentLoaded', async () => {
    const btnVolver = document.getElementById('btnVolver');
    
    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get('id') || 1; // ID 1 por defecto para desarrollo

    // 1. CONSUMIR LA API CONSOLIDADA (GET)
    try {
        const respuesta = await fetch(`http://localhost:5000/api/clientes/${idCliente}/ficha`);
        
        if (respuesta.ok) {
            const data = await respuesta.json();
            
            // Rellenar Datos de Contacto
            document.getElementById('fichaRut').textContent = data.rut;
            document.getElementById('fichaRazonSocial').textContent = data.razon_social;
            document.getElementById('fichaDireccion').textContent = data.direccion || 'No registrada';
            document.getElementById('fichaTelefono').textContent = data.telefono || 'No registrado';
            document.getElementById('fichaEmail').textContent = data.email || 'No registrado';
            document.getElementById('fichaAreas').textContent = data.areas_nombres || 'Ninguna asignada';

            // Rellenar Bloque de Tareas
            const tbodyTareas = document.getElementById('tablaTareasCuerpo');
            tbodyTareas.innerHTML = '';
            
            if (data.tareas.length === 0) {
                tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">No existen gestiones registradas para este cliente.</td></tr>`;
            } else {
                data.tareas.forEach(tarea => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${tarea.titulo}</strong></td>
                        <td>${tarea.nombre_area}</td>
                        <td>${tarea.fecha_vencimiento || 'Sin fecha'}</td>
                        <td><span class="status-texto">${tarea.estado}</span></td>
                    `;
                    tbodyTareas.appendChild(tr);
                });
            }

            // Rellenar Bloque de Documentos
            const tbodyDocs = document.getElementById('tablaDocumentoCuerpo');
            tbodyDocs.innerHTML = '';
            
            if (data.documentos.length === 0) {
                tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">No se registran archivos asociados en la plataforma.</td></tr>`;
            } else {
                data.documentos.forEach(doc => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${doc.nombre_documento}</td>
                        <td>${doc.fecha_subida}</td>
                        <td><a href="${doc.url_archivo}" target="_blank" class="link-descarga">Ver Archivo</a></td>
                    `;
                    tbodyDocs.appendChild(tr);
                });
            }

        } else {
            alert("No fue posible recuperar el expediente consolidado de este cliente.");
        }
    } catch (error) {
        console.error("Error al procesar la consolidación de la ficha:", error);
    }

    btnVolver.addEventListener('click', () => {
        window.location.href = 'listar_clientes.html';
    });
});