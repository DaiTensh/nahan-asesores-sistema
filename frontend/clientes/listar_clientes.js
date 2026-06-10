const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener('DOMContentLoaded', () => {
    const selectAreaFiltro = document.getElementById('selectAreaFiltro');
    const inputBuscarTexto = document.getElementById('inputBuscarTexto');
    const tbody = document.getElementById('tablaClientesGeneralCuerpo');
    
    const btnAnterior = document.getElementById('btnPaginaAnterior');
    const btnSiguiente = document.getElementById('btnPaginaSiguiente');
    const txtIndicador = document.getElementById('txtIndicadorPagina');

    // Variables de control de la carga progresiva paginada
    let paginaActual = 1;
    const limiteRegistros = 7; // Registros por carátula

    const cargarListadoGeneral = async () => {
        tbody.innerHTML = `<tr><td colspan="5" class="text-loading">Sincronizando grilla maestra de clientes...</td></tr>`;

        const idArea = selectAreaFiltro.value;
        const textoBuscar = inputBuscarTexto.value.trim();

        // Parámetros cruzados incluyendo paginación obligatoria
        let queryParams = [`pagina=${paginaActual}`, `limite=${limiteRegistros}`];
        if (idArea !== 'TODOS') queryParams.push(`id_area=${idArea}`);
        if (textoBuscar !== '') queryParams.push(`buscar=${encodeURIComponent(textoBuscar)}`);

        try {
            const respuesta = await fetch(`${API_URL}/clientes/listado?${queryParams.join('&')}`);

            if (!respuesta.ok) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-loading">No se pudo cargar el listado de clientes.</td></tr>`;
                return;
            }

            const data = await respuesta.json();
            tbody.innerHTML = '';

            if (data.clientes.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="text-loading">No se registran antecedentes bajo los criterios provistos.</td></tr>`;
                btnSiguiente.disabled = true;
                return;
            }

            // Renderizar cada fila inyectando los parámetros id_cliente dinámicamente en los botones
            data.clientes.forEach(cliente => {
                const tr = document.createElement('tr');

                // Si el estado es INACTIVO, se le inyecta la clase de opacidad exigida por la descripción
                if (cliente.estado === 'INACTIVO') {
                    tr.className = 'fila-inactiva';
                }

                tr.innerHTML = `
                    <td><strong>${cliente.rut}</strong></td>
                    <td>${cliente.razon_social}</td>
                    <td>${cliente.areas_nombres || 'Sin área'}</td>
                    <td><span class="status-pildora">${cliente.estado}</span></td>
                    <td style="text-align: center;">
                        <div class="acciones-celda-flex">
                            <a href="ficha_cliente.html?id=${cliente.id_cliente}" class="btn-accion-tabla btn-view" title="Ver Ficha">Ficha</a>
                            <a href="modificar_clientes.html?id=${cliente.id_cliente}" class="btn-accion-tabla btn-edit" title="Editar">Editar</a>
                            <a href="cambiar_estado.html?id=${cliente.id_cliente}" class="btn-accion-tabla btn-state" title="Toggle Estado">Estado</a>
                            <a href="eliminar_cliente.html?id=${cliente.id_cliente}" class="btn-accion-tabla btn-del" title="Eliminar/Deshabilitar">Quitar</a>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });

            // Control dinámico de los gatillos de la paginación
            txtIndicador.textContent = `Página ${paginaActual}`;
            btnAnterior.disabled = (paginaActual === 1);
            btnSiguiente.disabled = (data.clientes.length < limiteRegistros);

        } catch (error) {
            console.error(error);
            tbody.innerHTML = `<tr><td colspan="5" class="text-loading">Error al conectar con el backend de Nahan.</td></tr>`;
        }
    };

    // Escuchadores reactivos para filtros
    selectAreaFiltro.addEventListener('change', () => { paginaActual = 1; cargarListadoGeneral(); });
    inputBuscarTexto.addEventListener('input', () => { paginaActual = 1; cargarListadoGeneral(); });

    // Navegación de páginas
    btnAnterior.addEventListener('click', () => { if (paginaActual > 1) { paginaActual--; cargarListadoGeneral(); } });
    btnSiguiente.addEventListener('click', () => { paginaActual++; cargarListadoGeneral(); });

    // Carga inicial automatizada
    cargarListadoGeneral();
});
