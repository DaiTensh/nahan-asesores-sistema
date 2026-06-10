document.addEventListener('DOMContentLoaded', () => {
    const selectArea = document.getElementById('selectArea');
    const inputBuscar = document.getElementById('inputBuscar');
    const tbodyClientes = document.getElementById('tablaClientesCuerpo');

    // Función asíncrona encargada de solicitar la data cruzando ambos parámetros
    const cargarClientesFiltrados = async () => {
        const idArea = selectArea.value;
        const textoBusqueda = inputBuscar.value.trim();

        // Construcción limpia de Query Parameters (?id_area=1&buscar=alfa)
        let parametros = [];
        if (idArea !== 'TODOS') parametros.push(`id_area=${idArea}`);
        if (textoBusqueda !== '') parametros.push(`buscar=${encodeURIComponent(textoBusqueda)}`);

        let url = 'http://localhost:5000/api/clientes/filtrar';
        if (parametros.length > 0) {
            url += `?${parametros.join('&')}`;
        }

        try {
            const respuesta = await fetch(url);
            if (respuesta.ok) {
                const clientes = await respuesta.json();
                tbodyClientes.innerHTML = ''; 

                if (clientes.length === 0) {
                    tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">No se encontraron clientes activos con los criterios seleccionados.</td></tr>`;
                    return;
                }

                clientes.forEach(cliente => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${cliente.rut}</strong></td>
                        <td>${cliente.razon_social}</td>
                        <td>${cliente.telefono || 'Sin fono'}</td>
                        <td><span class="badge-estado">${cliente.estado}</span></td>
                        <td style="text-align: center;">
                            <a href="ficha_cliente.html?id=${cliente.id_cliente}" class="btn-tabla-ver">Ver Ficha</a>
                        </td>
                    `;
                    tbodyClientes.appendChild(tr);
                });
            } else {
                tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">❌ Error al procesar la segmentación.</td></tr>`;
            }
        } catch (error) {
            console.error(error);
            tbodyClientes.innerHTML = `<tr><td colspan="5" class="text-loading">❌ Error: Sin respuesta del backend Flask.</td></tr>`;
        }
    };

    // Escuchadores de eventos para recarga automática interactiva
    selectArea.addEventListener('change', cargarClientesFiltrados);
    inputBuscar.addEventListener('input', cargarClientesFiltrados);

    // Carga inicial al desplegar el componente
    cargarClientesFiltrados();
});