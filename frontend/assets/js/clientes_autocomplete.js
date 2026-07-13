const CLIENTES_API_URL = window.API_CONFIG.API_URL;

const ClientesAutocomplete = (() => {
  let clientesCache = null;

  function normalizarTexto(texto) {
    return String(texto || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function textoCliente(cliente) {
    return `${cliente.razon_social} - ${cliente.rut}`;
  }

  async function cargarClientes(opciones = {}) {
    if (!clientesCache) {
      const response = await fetch(`${CLIENTES_API_URL}/clientes/filtrar`, {
        credentials: window.API_CONFIG.credentials
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "No se pudieron cargar los clientes");
      }

      clientesCache = data;
    }

    if (opciones.soloActivos) {
      return clientesCache.filter(cliente => cliente.estado === "ACTIVO");
    }

    return clientesCache;
  }

  function llenarDatalist(datalist, clientes) {
    datalist.innerHTML = "";

    clientes.forEach(cliente => {
      const option = document.createElement("option");
      option.value = textoCliente(cliente);
      option.label = cliente.estado;
      datalist.appendChild(option);
    });
  }

  async function resolverClienteDesdeInput(input, opciones = {}) {
    const clientes = await cargarClientes(opciones);
    const valor = normalizarTexto(input.value);

    if (!valor) {
      return null;
    }

    const exacto = clientes.find(cliente =>
      normalizarTexto(textoCliente(cliente)) === valor ||
      normalizarTexto(cliente.rut) === valor
    );

    if (exacto) {
      return exacto;
    }

    if (opciones.permitirCoincidenciaUnica === false) {
      return null;
    }

    const coincidencias = clientes.filter(cliente =>
      normalizarTexto(cliente.razon_social).includes(valor) ||
      normalizarTexto(cliente.rut).includes(valor)
    );

    return coincidencias.length === 1 ? coincidencias[0] : null;
  }

  async function configurarSelectorCliente(config) {
    const input = document.getElementById(config.inputId);
    const hidden = document.getElementById(config.hiddenId);
    const datalist = document.getElementById(config.datalistId);

    if (!input || !hidden || !datalist) {
      return;
    }

    try {
      const clientes = await cargarClientes({ soloActivos: config.soloActivos });
      llenarDatalist(datalist, clientes);
    } catch (error) {
      console.error(error);
    }

    input.addEventListener("input", async () => {
      let cliente = null;

      try {
        cliente = await resolverClienteDesdeInput(input, {
          soloActivos: config.soloActivos,
          permitirCoincidenciaUnica: false
        });
      } catch (error) {
        console.error(error);
      }

      hidden.value = cliente ? cliente.id_cliente : "";
    });
  }

  async function obtenerClienteSeleccionado(inputId, opciones = {}) {
    const input = document.getElementById(inputId);

    if (!input) {
      return null;
    }

    try {
      return await resolverClienteDesdeInput(input, opciones);
    } catch (error) {
      console.error(error);
      return null;
    }
  }

  return {
    configurarSelectorCliente,
    obtenerClienteSeleccionado
  };
})();
