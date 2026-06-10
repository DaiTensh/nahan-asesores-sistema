const API_URL = "http://127.0.0.1:5000/api";

document.addEventListener("DOMContentLoaded", () => {
  cargarDatosUsuario();
  cargarResumenUsuarios();
  cargarResumenClientes();
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

async function cargarResumenClientes() {
  try {
    const response = await fetch(`${API_URL}/clientes/resumen`);
    const data = await response.json();

    if (!response.ok) {
      console.error(data.error || "Error al cargar clientes");
      return;
    }

    const totalClientes = document.getElementById("totalClientes");
    const clientesActivos = document.getElementById("clientesActivos");
    const clientesInactivos = document.getElementById("clientesInactivos");

    if (totalClientes) totalClientes.textContent = data.total_clientes;
    if (clientesActivos) clientesActivos.textContent = data.clientes_activos;
    if (clientesInactivos) clientesInactivos.textContent = data.clientes_inactivos;

    cargarTablaClientes(data.ultimos_clientes || []);

  } catch (error) {
    console.error(error);
  }
}

function cargarTablaClientes(clientes) {
  const tabla = document.getElementById("tablaClientes");

  if (!tabla) return;

  tabla.innerHTML = "";

  if (clientes.length === 0) {
    tabla.innerHTML = `
      <tr>
        <td colspan="6">No hay clientes registrados.</td>
      </tr>
    `;
    return;
  }

  clientes.forEach(cliente => {
    const fila = document.createElement("tr");

    fila.innerHTML = `
      <td>${cliente.rut}</td>
      <td>${cliente.razon_social}</td>
      <td>${cliente.email || "Sin correo"}</td>
      <td>${cliente.telefono || "Sin teléfono"}</td>
      <td>
        <span class="badge ${cliente.estado.toLowerCase()}">
          ${cliente.estado}
        </span>
      </td>
      <td>
        <div class="dashboard-row-actions">
          <a href="../clientes/ficha_cliente.html?id=${cliente.id_cliente}">Ficha</a>
          <a href="../clientes/modificar_clientes.html?id=${cliente.id_cliente}">Editar</a>
          <a href="../clientes/cambiar_estado.html?id=${cliente.id_cliente}">Estado</a>
          <a href="../clientes/eliminar_cliente.html?id=${cliente.id_cliente}">Quitar</a>
        </div>
      </td>
    `;

    tabla.appendChild(fila);
  });
}
