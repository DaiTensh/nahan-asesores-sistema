const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", async () => {
    const btnDispararGuardado = document.getElementById("btnDispararGuardado");
    const panelConfirmacion = document.getElementById("panelConfirmacion");
    const flujoFlecha = document.getElementById("flujoFlecha");
    const listaCambios = document.getElementById("listaCambios");
    const btnConfirmarFinal = document.getElementById("btnConfirmarFinal");
    const btnVolver = document.getElementById("btnVolver");
    const mensaje = document.getElementById("mensajeFeedback");

    const parametrosUrl = new URLSearchParams(window.location.search);
    const idCliente = parametrosUrl.get("id");

    let datosOriginales = {};

    function obtenerAreasSeleccionadas() {
        const areas = [];
        if (document.getElementById("checkLegal").checked) areas.push(1);
        if (document.getElementById("checkContable").checked) areas.push(2);
        return areas;
    }

    function obtenerDatosFormulario() {
        const areas = obtenerAreasSeleccionadas();

        return {
            direccion: document.getElementById("direccion").value.trim(),
            razon_social: document.getElementById("razon_social").value.trim(),
            nombre_contacto_2: document.getElementById("nombre_contacto_2").value.trim(),
            telefono: document.getElementById("telefono").value.trim(),
            email: document.getElementById("email").value.trim(),
            areas: areas.sort().toString()
        };
    }

    function mostrarMensaje(texto, tipo) {
        mensaje.textContent = texto;
        mensaje.className = `mensaje ${tipo}`;
    }

    function bloquearFormulario(texto) {
        btnDispararGuardado.disabled = true;
        btnDispararGuardado.textContent = texto;
    }

    async function cargarCliente() {
        if (!idCliente) {
            bloquearFormulario("Sin cliente");
            alert("No se recibió un cliente válido desde el listado.");
            return;
        }

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}`);
            const cliente = await respuesta.json();

            if (!respuesta.ok) {
                bloquearFormulario("No disponible");
                alert(cliente.error || "No se pudo cargar el cliente.");
                return;
            }

            document.getElementById("rut").value = cliente.rut;
            document.getElementById("direccion").value = cliente.direccion || "";
            document.getElementById("razon_social").value = cliente.razon_social;
            document.getElementById("nombre_contacto_2").value = cliente.nombre_contacto_2 || "";
            document.getElementById("telefono").value = cliente.telefono || "";
            document.getElementById("email").value = cliente.email || "";

            const areas = cliente.areas || [];
            document.getElementById("checkLegal").checked = areas.includes(1);
            document.getElementById("checkContable").checked = areas.includes(2);

            datosOriginales = obtenerDatosFormulario();
        } catch (error) {
            console.error(error);
            bloquearFormulario("No disponible");
            alert("Error de conexión al cargar los antecedentes del cliente.");
        }
    }

    btnDispararGuardado.addEventListener("click", () => {
        listaCambios.innerHTML = "";
        mensaje.className = "mensaje";

        const datosActuales = obtenerDatosFormulario();
        const traducciones = {
            direccion: "Dirección",
            razon_social: "Nombre contacto 1",
            nombre_contacto_2: "Nombre contacto 2",
            telefono: "Fono",
            email: "Correo",
            areas: "Áreas"
        };

        let cambiosContador = 0;

        Object.keys(datosActuales).forEach(key => {
            if (datosActuales[key] !== datosOriginales[key]) {
                cambiosContador++;
                const li = document.createElement("li");
                li.textContent = `Cambio ${cambiosContador}: ${traducciones[key]}`;
                listaCambios.appendChild(li);
            }
        });

        if (cambiosContador === 0) {
            alert("No se detectó ningún cambio respecto a los datos iniciales.");
            return;
        }

        panelConfirmacion.style.display = "flex";
        flujoFlecha.style.display = "block";
    });

    btnConfirmarFinal.addEventListener("click", async () => {
        mensaje.className = "mensaje";

        const areasActuales = obtenerAreasSeleccionadas();

        if (areasActuales.length === 0) {
            mostrarMensaje("Debe asignar el cliente a al menos un área.", "error");
            return;
        }

        const payload = {
            direccion: document.getElementById("direccion").value.trim(),
            razon_social: document.getElementById("razon_social").value.trim(),
            nombre_contacto_2: document.getElementById("nombre_contacto_2").value.trim(),
            telefono: document.getElementById("telefono").value.trim(),
            email: document.getElementById("email").value.trim(),
            areas: areasActuales
        };

        try {
            const respuesta = await fetch(`${API_URL}/clientes/${idCliente}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const resultado = await respuesta.json();

            if (!respuesta.ok) {
                mostrarMensaje(resultado.error || "No se pudieron guardar los cambios.", "error");
                return;
            }

            mostrarMensaje(resultado.message || "Cambios almacenados.", "success");

            setTimeout(() => {
                window.location.href = "listar_clientes.html";
            }, 1200);
        } catch (error) {
            console.error(error);
            mostrarMensaje("Error de conexión al guardar los cambios.", "error");
        }
    });

    btnVolver.addEventListener("click", () => {
        panelConfirmacion.style.display = "none";
        flujoFlecha.style.display = "none";
    });

    await cargarCliente();
});
