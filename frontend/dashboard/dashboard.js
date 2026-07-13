const API_URL = window.API_CONFIG.API_URL;

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
    CONTABLE: "Contable",
    1: "Jurídica",
    2: "Contable",
    3: "Ambas áreas"
  };

  return areas[area] || area;
}

async function cargarDatosUsuario() {
  const usuario = await obtenerUsuarioActual();

  if (!usuario) {
    window.location.href = "../auth/login.html";
    return;
  }

  document.getElementById("nombreUsuario").textContent = usuario.nombres;
  document.getElementById("rolUsuario").textContent = formatearRol(usuario.nombre_rol);
  document.getElementById("areaUsuario").textContent = formatearArea(usuario.nombre_area || usuario.id_area);
}

async function cargarResumenUsuarios() {
  try {
    const response = await fetch(`${API_URL}/usuarios`, {
      credentials: window.API_CONFIG.credentials
    });
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
    const response = await fetch(`${API_URL}/clientes/resumen`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      await cargarClientesDesdeListado();
      return;
    }

    document.getElementById("totalClientes").textContent = data.total_clientes;
    document.getElementById("clientesActivos").textContent = data.clientes_activos;
    document.getElementById("clientesInactivos").textContent = data.clientes_inactivos;

    cargarTablaClientes(data.ultimos_clientes || []);
  } catch (error) {
    console.error(error);
    await cargarClientesDesdeListado();
  }
}

async function cargarClientesDesdeListado() {
  try {
    const response = await fetch(`${API_URL}/clientes/listado?pagina=1&limite=5`, {
      credentials: window.API_CONFIG.credentials
    });
    const data = await leerRespuestaJson(response);

    if (!response.ok) {
      console.error(data.error || "Error al cargar clientes");
      return;
    }

    const clientes = Array.isArray(data) ? data : data.clientes || [];

    document.getElementById("totalClientes").textContent = clientes.length;
    document.getElementById("clientesActivos").textContent =
      clientes.filter(cliente => normalizarEstado(cliente.estado) === "ACTIVO").length;
    document.getElementById("clientesInactivos").textContent =
      clientes.filter(cliente => normalizarEstado(cliente.estado) === "INACTIVO").length;

    cargarTablaClientes(clientes);
  } catch (error) {
    console.error(error);
  }
}

function cargarTablaClientes(clientes) {
  const tabla = document.getElementById("tablaClientes");
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
        <span class="badge ${normalizarEstado(cliente.estado).toLowerCase()}">
          ${normalizarEstado(cliente.estado)}
        </span>
      </td>
      <td>
        <div class="dashboard-row-actions">
          <a href="../clientes/ficha_cliente.html?id=${cliente.id_cliente}">Ficha</a>
          <a href="../clientes/modificar_clientes.html?id=${cliente.id_cliente}">Editar</a>
        </div>
      </td>
    `;

    tabla.appendChild(fila);
  });
}

async function leerRespuestaJson(response) {
  const texto = await response.text();

  if (!texto) return {};

  try {
    return JSON.parse(texto);
  } catch (error) {
    console.error("Respuesta no válida del servidor:", texto);
    return { error: "Respuesta no válida del servidor." };
  }
}

function normalizarEstado(estado) {
  return estado || "ACTIVO";
}
