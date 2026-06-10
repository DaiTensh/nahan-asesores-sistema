const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", async () => {
    const btnVolver = document.getElementById("btnVolver");
    const tbodyTareas = document.getElementById("tablaTareasCuerpo");
    const tbodyDocs = document.getElementById("tablaDocumentoCuerpo");

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get("id");

    function mostrarError(texto) {
        tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">${texto}</td></tr>`;
        tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">${texto}</td></tr>`;
    }

    async function cargarFichaCliente() {
        if (!idCliente) {
            mostrarError("No se recibió un cliente válido desde el listado.");
            return;
        }

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}/ficha`);
            const data = await respuesta.json();

            if (!respuesta.ok) {
                mostrarError(data.error || "No fue posible recuperar el expediente consolidado.");
                return;
            }

            document.getElementById("fichaRut").textContent = data.rut;
            document.getElementById("fichaRazonSocial").textContent = data.razon_social;
            document.getElementById("fichaDireccion").textContent = data.direccion || "No registrada";
            document.getElementById("fichaTelefono").textContent = data.telefono || "No registrado";
            document.getElementById("fichaEmail").textContent = data.email || "No registrado";
            document.getElementById("fichaAreas").textContent = data.areas_nombres || "Ninguna asignada";

            tbodyTareas.innerHTML = "";

            if (!data.tareas || data.tareas.length === 0) {
                tbodyTareas.innerHTML = `<tr><td colspan="4" class="text-loading">No existen gestiones registradas para este cliente.</td></tr>`;
            } else {
                data.tareas.forEach(tarea => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><strong>${tarea.titulo}</strong></td>
                        <td>${tarea.nombre_area}</td>
                        <td>${tarea.fecha_vencimiento || "Sin fecha"}</td>
                        <td><span class="status-texto">${tarea.estado}</span></td>
                    `;
                    tbodyTareas.appendChild(tr);
                });
            }

            tbodyDocs.innerHTML = "";

            if (!data.documentos || data.documentos.length === 0) {
                tbodyDocs.innerHTML = `<tr><td colspan="3" class="text-loading">No se registran archivos asociados en la plataforma.</td></tr>`;
            } else {
                data.documentos.forEach(doc => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${doc.nombre_documento}</td>
                        <td>${doc.fecha_subida}</td>
                        <td><a href="${doc.url_archivo}" target="_blank" class="link-descarga">Ver Archivo</a></td>
                    `;
                    tbodyDocs.appendChild(tr);
                });
            }
        } catch (error) {
            console.error(error);
            mostrarError("Error de conexión al cargar la ficha del cliente.");
        }
    }

    btnVolver.addEventListener("click", () => {
        window.location.href = "listar_clientes.html";
    });

    await cargarFichaCliente();
});
