const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  cargarDatosUsuario();
  cargarResumenUsuarios();
});

function formatearRol(rol) {
  const roles = {
    ADMINISTRADOR: "Administrador",
    USUARIO_AREA_JURIDICA: "Usuario Área Jurídica",
    USUARIO_AREA_CONTABLE: "Usuario Área Contable"
  };

  return roles[rol] || rol;
}

function formatearArea(area) {
  const areas = {
    ADMINISTRACION: "Administración",
    JURIDICA: "Jurídica",
    CONTABLE: "Contable"
  };

  return areas[area] || area;
}

function cargarDatosUsuario() {
  const usuario = JSON.parse(localStorage.getItem("usuario"));

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  document.getElementById("nombreUsuario").textContent = usuario.nombres;
  document.getElementById("rolUsuario").textContent = formatearRol(usuario.nombre_rol);
  document.getElementById("areaUsuario").textContent = formatearArea(usuario.nombre_area);
}

async function cargarResumenUsuarios() {
  try {
    const response = await fetch(`${API_URL}/usuarios`);
    const usuarios = await response.json();

    if (!response.ok) {
      console.error("Error al cargar usuarios");
      return;
    }

    document.getElementById("totalUsuarios").textContent = usuarios.length;
    document.getElementById("usuariosActivos").textContent =
      usuarios.filter(usuario => usuario.estado === "ACTIVO").length;
    document.getElementById("usuariosInactivos").textContent =
      usuarios.filter(usuario => usuario.estado === "INACTIVO").length;
    document.getElementById("totalAdmins").textContent =
      usuarios.filter(usuario => usuario.nombre_rol === "ADMINISTRADOR").length;

    cargarTablaUsuarios(usuarios);

  } catch (error) {
    console.error(error);
  }
}

function cargarTablaUsuarios(usuarios) {
  const tabla = document.getElementById("tablaUsuarios");
  tabla.innerHTML = "";

  usuarios.forEach(usuario => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${usuario.id_usuario}</td>
      <td>${usuario.nombres}</td>
      <td>${usuario.email}</td>
      <td>${formatearRol(usuario.nombre_rol)}</td>
      <td>${formatearArea(usuario.nombre_area)}</td>
      <td>
        <span class="badge ${usuario.estado.toLowerCase()}">
          ${usuario.estado}
        </span>
      </td>
    `;

    tabla.appendChild(fila);
  });
}