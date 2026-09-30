const API_URL = window.API_CONFIG.API_URL;

const formUsuario = document.getElementById("formUsuario");
const mensaje = document.getElementById("mensaje");
const selectorRol = document.getElementById("id_rol");
const selectorArea = document.getElementById("id_area");
const botonRegistrar = formUsuario.querySelector("button[type='submit']");
const tablaUsuarios = document.getElementById("tablaUsuarios");
const mensajeListadoUsuarios = document.getElementById("mensajeListadoUsuarios");
const filtroRol = document.getElementById("filtroRol");
const filtroArea = document.getElementById("filtroArea");
const filtroEstado = document.getElementById("filtroEstado");
const ordenUsuarios = document.getElementById("ordenUsuarios");

let catalogoUsuarios = [];
let opcionesUsuariosCargadas = false;
let solicitudListado = 0;

const AREA_POR_ROL = {
  1: 3,
  2: 1,
  3: 2
};

function sincronizarAreaConRol() {
  const idRol = Number(selectorRol.value);
  const idArea = AREA_POR_ROL[idRol];

  if (!idArea) {
    selectorArea.value = "";
    selectorArea.disabled = false;
    return;
  }

  selectorArea.value = String(idArea);
  selectorArea.disabled = true;
}

function agregarOpcionesDinamicas(selector, usuarios, campoId, campoNombre, etiquetaTodos) {
  const valorActual = selector.value;
  const opciones = new Map();

  usuarios.forEach(usuario => {
    const id = usuario[campoId];
    const nombre = usuario[campoNombre];
    if (id != null && nombre) opciones.set(String(id), String(nombre));
  });

  selector.replaceChildren(new Option(etiquetaTodos, ""));
  [...opciones.entries()]
    .sort(([, nombreA], [, nombreB]) => nombreA.localeCompare(nombreB, "es"))
    .forEach(([id, nombre]) => selector.add(new Option(nombre, id)));
  if ([...selector.options].some(opcion => opcion.value === valorActual)) selector.value = valorActual;
}

function crearCelda(texto) {
  const celda = document.createElement("td");
  celda.textContent = texto || "-";
  return celda;
}

function mostrarUsuarios(usuarios) {
  tablaUsuarios.replaceChildren();
  if (!usuarios.length) {
    const fila = document.createElement("tr");
    const celda = crearCelda("No hay usuarios que coincidan con los filtros.");
    celda.colSpan = 7;
    fila.appendChild(celda);
    tablaUsuarios.appendChild(fila);
    return;
  }

  usuarios.forEach(usuario => {
    const fila = document.createElement("tr");
    const inactivo = usuario.estado === "INACTIVO";
    if (inactivo) fila.classList.add("usuario-fila-inactiva");
    fila.append(
      crearCelda(usuario.nombres),
      crearCelda(usuario.email),
      crearCelda(usuario.nombre_rol),
      crearCelda(usuario.nombre_area || "Sin área")
    );

    const estado = document.createElement("span");
    estado.className = `usuario-estado ${inactivo ? "usuario-estado-inactivo" : "usuario-estado-activo"}`;
    estado.textContent = inactivo ? "Inactivo" : "Activo";
    const celdaEstado = document.createElement("td");
    celdaEstado.appendChild(estado);
    fila.append(celdaEstado, crearCelda(usuario.fecha_creacion));

    const enlace = document.createElement("a");
    enlace.className = "btn btn-secondary btn-small";
    enlace.href = `modificar_usuario.html?id=${encodeURIComponent(usuario.id_usuario)}`;
    enlace.textContent = "Ver perfil";
    const celdaPerfil = document.createElement("td");
    celdaPerfil.appendChild(enlace);
    fila.appendChild(celdaPerfil);
    tablaUsuarios.appendChild(fila);
  });
}

async function cargarListadoUsuarios() {
  const solicitud = ++solicitudListado;
  mensajeListadoUsuarios.textContent = "";
  mensajeListadoUsuarios.className = "mensaje";

  try {
    const parametros = new URLSearchParams();
    if (filtroRol.value) parametros.set("id_rol", filtroRol.value);
    if (filtroArea.value) parametros.set("id_area", filtroArea.value);
    if (filtroEstado.value) parametros.set("estado", filtroEstado.value);
    if (ordenUsuarios.value) {
      const [ordenarPor, direccion] = ordenUsuarios.value.split(":");
      parametros.set("ordenar_por", ordenarPor);
      parametros.set("direccion", direccion);
    }
    const query = parametros.toString();
    const response = await fetch(`${API_URL}/usuarios${query ? `?${query}` : ""}`, {
      credentials: window.API_CONFIG.credentials
    });
    const usuarios = await response.json();
    if (!response.ok) throw new Error(usuarios.error || "No se pudo cargar el listado");

    if (!opcionesUsuariosCargadas) {
      catalogoUsuarios = usuarios;
      agregarOpcionesDinamicas(filtroRol, catalogoUsuarios, "id_rol", "nombre_rol", "Todos los roles");
      agregarOpcionesDinamicas(filtroArea, catalogoUsuarios, "id_area", "nombre_area", "Todas las áreas");
      opcionesUsuariosCargadas = true;
    }
    if (solicitud === solicitudListado) mostrarUsuarios(usuarios);
  } catch (error) {
    if (solicitud !== solicitudListado) return;
    mensajeListadoUsuarios.textContent = error.message || "No se pudo cargar el listado de usuarios.";
    mensajeListadoUsuarios.className = "mensaje error";
    mostrarUsuarios([]);
  }
}

selectorRol.addEventListener("change", sincronizarAreaConRol);
filtroRol.addEventListener("change", cargarListadoUsuarios);
filtroArea.addEventListener("change", cargarListadoUsuarios);
filtroEstado.addEventListener("change", cargarListadoUsuarios);
ordenUsuarios.addEventListener("change", cargarListadoUsuarios);
cargarListadoUsuarios();

formUsuario.addEventListener("submit", async (event) => {
  event.preventDefault();
  sincronizarAreaConRol();

  const usuario = {
    id_rol: Number(document.getElementById("id_rol").value),
    id_area: Number(document.getElementById("id_area").value),
    nombres: document.getElementById("nombres").value.trim(),
    email: document.getElementById("email").value.trim(),
    password: document.getElementById("password").value
  };

  const confirmar = confirm("¿Desea registrar este nuevo usuario?");

  if (!confirmar) {
    return;
  }

  try {
    botonRegistrar.disabled = true;
    botonRegistrar.textContent = "Registrando...";

    const response = await fetch(`${API_URL}/usuarios`, {
      method: "POST",
      credentials: window.API_CONFIG.credentials,
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(usuario)
    });

    const data = await response.json();

    if (!response.ok) {
      mensaje.textContent = data.error || "Error al registrar usuario";
      mensaje.className = "mensaje error";
      return;
    }

    mensaje.textContent = data.message;
    mensaje.className = "mensaje success";
    formUsuario.reset();
    sincronizarAreaConRol();

  } catch (error) {
    mensaje.textContent = "No se pudo conectar con el servidor";
    mensaje.className = "mensaje error";
  } finally {
    botonRegistrar.disabled = false;
    botonRegistrar.textContent = "Registrar Usuario";
  }
});
