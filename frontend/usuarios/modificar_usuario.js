async function buscarUsuario() {
    const id = document.getElementById("id_usuario").value;

    if (!id) {
        alert("Ingrese un ID");
        return;
    }

    try {
        const response = await fetch(
            `http://127.0.0.1:5000/api/usuarios/${id}`
        );

        const data = await response.json();

        if (!response.ok) {
            alert(data.error || "Usuario no encontrado");
            return;
        }

        document.getElementById("nombres").value = data.nombres;
        document.getElementById("email").value = data.email;
        document.getElementById("id_rol").value = data.id_rol;
        document.getElementById("id_area").value = data.id_area;
        document.getElementById("estado").value = data.estado;

    }
    catch(error) {
        console.error(error);
        alert("Error al buscar usuario");
    }
}

async function actualizarUsuario() {
    const id = document.getElementById("id_usuario").value;

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

    const datos = {
        id_rol: parseInt(document.getElementById("id_rol").value),
        id_area: parseInt(document.getElementById("id_area").value),
        nombres: document.getElementById("nombres").value,
        email: document.getElementById("email").value,
        estado: document.getElementById("estado").value
    };

    try {
        const response = await fetch(
            `http://127.0.0.1:5000/api/usuarios/${id}`,
            {
                method: "PUT",
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

    }
    catch(error) {
        console.error(error);
        alert("Error al actualizar usuario");
    }
}