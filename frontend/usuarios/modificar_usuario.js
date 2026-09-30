const API_URL = window.API_CONFIG.API_URL;

let usuarioActual = null;

const AREA_POR_ROL = {
    1: 3,
    2: 1,
    3: 2
};

function sincronizarAreaConRol() {
    const selectorRol = document.getElementById("id_rol");
    const selectorArea = document.getElementById("id_area");
    const idRol = Number(selectorRol.value);
    const idArea = AREA_POR_ROL[idRol];

    if (!idArea) {
        selectorArea.disabled = false;
        return;
    }

    selectorArea.value = String(idArea);
    selectorArea.disabled = true;
}

document.addEventListener("DOMContentLoaded", () => {
    UsuariosAutocomplete.configurarSelectorUsuario({
        inputId: "usuario_busqueda",
        hiddenId: "id_usuario",
        datalistId: "usuarios_datalist",
        onSelect: (usuario) => cargarUsuarioPorId(usuario.id_usuario)
    });

    document.getElementById("id_rol").addEventListener("change", sincronizarAreaConRol);
    sincronizarAreaConRol();

    const idUsuario = new URLSearchParams(window.location.search).get("id");
    if (idUsuario && /^\d+$/.test(idUsuario) && Number(idUsuario) > 0) {
        cargarUsuarioPorId(idUsuario);
    }
});

async function buscarUsuario() {
    const usuario = await UsuariosAutocomplete.obtenerUsuarioSeleccionado("usuario_busqueda");

    if (!usuario) {
        alert("Seleccione un usuario de la lista");
        return;
    }

    await cargarUsuarioPorId(usuario.id_usuario);
}

async function cargarUsuarioPorId(id) {
    try {
        const response = await fetch(
            `${API_URL}/usuarios/${id}`,
            {
                credentials: window.API_CONFIG.credentials
            }
        );

        const data = await response.json();

        if (!response.ok) {
            alert(data.error || "Usuario no encontrado");
            return;
        }

        usuarioActual = data;
        UsuariosAutocomplete.mostrarUsuarioEnInput("usuario_busqueda", "id_usuario", data);

        document.getElementById("nombres").value = data.nombres;
        document.getElementById("email").value = data.email;
        document.getElementById("id_rol").value = data.id_rol;
        document.getElementById("id_area").value = data.id_area;
        document.getElementById("estado").value = data.estado;
        document.getElementById("perfilId").textContent = data.id_usuario;
        document.getElementById("perfilRol").textContent = data.nombre_rol || "Sin rol";
        document.getElementById("perfilArea").textContent = data.nombre_area || "Sin área";
        document.getElementById("fechaCreacion").textContent = data.fecha_creacion || "Sin fecha";
        document.getElementById("perfilUsuario").hidden = false;
        sincronizarAreaConRol();

    }
    catch(error) {
        console.error(error);
        alert("Error al buscar usuario");
    }
}

async function actualizarUsuario() {
    const botonActualizar = document.getElementById("btnActualizarUsuario");
    const id = usuarioActual ? usuarioActual.id_usuario : document.getElementById("id_usuario").value;

    if (!id) {
        alert("Debe buscar un usuario antes de actualizar");
        return;
    }

    const confirmar = confirm(
        "¿Desea guardar los cambios realizados en este usuario?"
    );

    if (!confirmar) {
        return;
    }

    sincronizarAreaConRol();

    const datos = {
        id_rol: parseInt(document.getElementById("id_rol").value),
        id_area: parseInt(document.getElementById("id_area").value),
        nombres: document.getElementById("nombres").value,
        email: document.getElementById("email").value,
        estado: document.getElementById("estado").value
    };

    try {
        botonActualizar.disabled = true;
        botonActualizar.textContent = "Actualizando...";

        const response = await fetch(
            `${API_URL}/usuarios/${id}`,
            {
                method: "PUT",
                credentials: window.API_CONFIG.credentials,
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(datos)
            }
        );

        const resultado = await response.json();

        if (!response.ok) {
            alert(resultado.error || "Error al actualizar usuario");
            return;
        }

        alert(resultado.message);
        usuarioActual = {
            ...usuarioActual,
            ...datos,
            id_usuario: id
        };

    }
    catch(error) {
        console.error(error);
        alert("Error al actualizar usuario");
    } finally {
        botonActualizar.disabled = false;
        botonActualizar.textContent = "Guardar cambios";
    }
}
