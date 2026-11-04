const USUARIOS_API_URL = window.API_CONFIG.API_URL;

const UsuariosAutocomplete = (() => {
  let usuariosCache = null;

  function normalizarTexto(texto) {
    return String(texto || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  // El administrador recibe el correo de cada persona; los usuarios operativos
  // solo reciben nombre y área (GET /api/usuarios). Dos personas con el mismo
  // texto se distinguen con su número.
  const NOMBRES_AREA = { JURIDICA: "Jurídica", CONTABLE: "Contable", ADMINISTRACION: "Administración" };

  function nombreArea(usuario) {
    return NOMBRES_AREA[usuario.nombre_area] || usuario.nombre_area;
  }

  function textoUsuario(usuario) {
    if (usuario.textoLista) return usuario.textoLista;
    const detalle = usuario.email || nombreArea(usuario);
    return detalle ? `${usuario.nombres} - ${detalle}` : usuario.nombres;
  }

  function asignarTextosUnicos(usuarios) {
    const repeticiones = new Map();
    usuarios.forEach(usuario => {
      delete usuario.textoLista;
      const base = textoUsuario(usuario);
      repeticiones.set(base, (repeticiones.get(base) || 0) + 1);
    });
    usuarios.forEach(usuario => {
      const base = textoUsuario(usuario);
      usuario.textoLista = repeticiones.get(base) > 1 ? `${base} (n.º ${usuario.id_usuario})` : base;
    });
  }

  async function cargarUsuarios(opciones = {}) {
    if (!usuariosCache) {
      const response = await fetch(`${USUARIOS_API_URL}/usuarios`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "No se pudieron cargar los usuarios");
      }

      usuariosCache = data;
      asignarTextosUnicos(usuariosCache);
    }

    if (opciones.soloActivos) {
      return usuariosCache.filter(usuario => usuario.estado === "ACTIVO");
    }

    return usuariosCache;
  }

  function llenarDatalist(datalist, usuarios) {
    datalist.innerHTML = "";

    usuarios.forEach(usuario => {
      const option = document.createElement("option");
      option.value = textoUsuario(usuario);
      option.label = [usuario.nombre_rol, nombreArea(usuario), usuario.estado].filter(Boolean).join(" - ");
      datalist.appendChild(option);
    });
  }

  async function resolverUsuarioDesdeInput(input, opciones = {}) {
    const usuarios = await cargarUsuarios(opciones);
    const valor = normalizarTexto(input.value);

    if (!valor) {
      return null;
    }

    const exacto = usuarios.find(usuario =>
      normalizarTexto(textoUsuario(usuario)) === valor ||
      normalizarTexto(usuario.email) === valor
    );

    if (exacto) {
      return exacto;
    }

    if (opciones.permitirCoincidenciaUnica === false) {
      return null;
    }

    const coincidencias = usuarios.filter(usuario =>
      normalizarTexto(usuario.nombres).includes(valor) ||
      normalizarTexto(usuario.email).includes(valor) ||
      normalizarTexto(usuario.nombre_rol).includes(valor) ||
      normalizarTexto(usuario.nombre_area).includes(valor)
    );

    return coincidencias.length === 1 ? coincidencias[0] : null;
  }

  async function configurarSelectorUsuario(config) {
    const input = document.getElementById(config.inputId);
    const hidden = document.getElementById(config.hiddenId);
    const datalist = document.getElementById(config.datalistId);

    if (!input || !hidden || !datalist) {
      return;
    }

    try {
      const usuarios = await cargarUsuarios({ soloActivos: config.soloActivos });
      llenarDatalist(datalist, usuarios);
    } catch (error) {
      console.error(error);
    }

    input.addEventListener("input", async () => {
      let usuario = null;

      try {
        usuario = await resolverUsuarioDesdeInput(input, {
          soloActivos: config.soloActivos,
          permitirCoincidenciaUnica: false
        });
      } catch (error) {
        console.error(error);
      }

      hidden.value = usuario ? usuario.id_usuario : "";

      if (usuario && typeof config.onSelect === "function") {
        Promise.resolve(config.onSelect(usuario)).catch(error => {
          console.error(error);
        });
      }
    });
  }

  async function obtenerUsuarioSeleccionado(inputId, opciones = {}) {
    const input = document.getElementById(inputId);

    if (!input) {
      return null;
    }

    try {
      return await resolverUsuarioDesdeInput(input, opciones);
    } catch (error) {
      console.error(error);
      return null;
    }
  }

  function mostrarUsuarioEnInput(inputId, hiddenId, usuario) {
    const input = document.getElementById(inputId);
    const hidden = document.getElementById(hiddenId);

    if (input) {
      input.value = textoUsuario(usuario);
    }

    if (hidden) {
      hidden.value = usuario.id_usuario;
    }
  }

  return {
    configurarSelectorUsuario,
    obtenerUsuarioSeleccionado,
    mostrarUsuarioEnInput
  };
})();
