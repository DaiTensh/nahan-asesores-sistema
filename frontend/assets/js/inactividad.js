// RF59 — Cerrando Automático por Inactividad.
//
// Se monta desde topbar.js en todas las pantallas autenticadas. Consulta el
// tiempo restante de la sesión con la cabecera `X-Actividad: pasiva` (esas
// consultas no renuevan el plazo), renueva la sesión cuando el usuario
// interactúa con la página y, antes del cierre, muestra un aviso con cuenta
// regresiva desde el que se puede seguir conectado.
(function () {
  if (window.__inactividadMontada) return;
  window.__inactividadMontada = true;

  const API_URL = window.API_CONFIG.API_URL;
  const CREDENCIALES = window.API_CONFIG.credentials;
  const INTERVALO_CONSULTA_MS = 15000;
  const MINIMO_ENTRE_RENOVACIONES_MS = 60000;

  let huboInteraccion = false;
  let ultimaRenovacion = Date.now();
  let avisoVisible = false;
  let cuentaRegresiva = null;
  let segundosAviso = 60;
  let modal = null;

  function cargarEstilos() {
    if (document.querySelector('link[data-modulo="inactividad"]')) return;
    const enlace = document.createElement("link");
    enlace.rel = "stylesheet";
    enlace.href = "../assets/css/inactividad.css";
    enlace.dataset.modulo = "inactividad";
    document.head.appendChild(enlace);
  }

  function irAlLogin() {
    window.location.href = "../auth/login.html?motivo=inactividad";
  }

  function crearModal() {
    modal = document.createElement("div");
    modal.className = "inactividad-fondo";
    modal.hidden = true;
    modal.setAttribute("role", "alertdialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "inactividadTitulo");

    const caja = document.createElement("div");
    caja.className = "inactividad-caja";

    const titulo = document.createElement("h2");
    titulo.id = "inactividadTitulo";
    titulo.textContent = "Tu sesión está por cerrarse";

    const texto = document.createElement("p");
    texto.append("Por seguridad, la sesión se cerrará por inactividad en ");
    const contador = document.createElement("strong");
    contador.id = "inactividadContador";
    contador.textContent = "--";
    texto.append(contador, " segundos.");

    const acciones = document.createElement("div");
    acciones.className = "inactividad-acciones";

    const seguir = document.createElement("button");
    seguir.type = "button";
    seguir.className = "btn btn-primary";
    seguir.textContent = "Seguir conectado";
    seguir.addEventListener("click", seguirConectado);

    const salir = document.createElement("button");
    salir.type = "button";
    salir.className = "btn btn-secondary";
    salir.textContent = "Cerrar sesión";
    salir.addEventListener("click", () => {
      if (typeof cerrarSesion === "function") cerrarSesion();
      else irAlLogin();
    });

    acciones.append(seguir, salir);
    caja.append(titulo, texto, acciones);
    modal.appendChild(caja);
    document.body.appendChild(modal);
  }

  function mostrarAviso(segundos) {
    if (!modal) crearModal();
    let restantes = segundos;
    document.getElementById("inactividadContador").textContent = restantes;

    if (!avisoVisible) {
      avisoVisible = true;
      modal.hidden = false;
      modal.querySelector(".btn-primary").focus();
    }

    clearInterval(cuentaRegresiva);
    cuentaRegresiva = setInterval(() => {
      restantes -= 1;
      document.getElementById("inactividadContador").textContent = Math.max(restantes, 0);
      if (restantes <= 0) {
        clearInterval(cuentaRegresiva);
        cerrarPorInactividad();
      }
    }, 1000);
  }

  // Al llegar a cero se consulta una vez más al servidor, que es quien
  // invalida la sesión y deja constancia del cierre en la auditoría.
  function cerrarPorInactividad() {
    setTimeout(async () => {
      try {
        await fetch(`${API_URL}/auth/sesion`, {
          credentials: CREDENCIALES,
          headers: { "X-Actividad": "pasiva" }
        });
      } catch (error) {
        console.error(error);
      }
      irAlLogin();
    }, 2000);
  }

  function ocultarAviso() {
    avisoVisible = false;
    clearInterval(cuentaRegresiva);
    if (modal) modal.hidden = true;
  }

  async function renovar() {
    ultimaRenovacion = Date.now();
    huboInteraccion = false;
    const response = await fetch(`${API_URL}/auth/sesion/extender`, {
      method: "POST",
      credentials: CREDENCIALES
    });
    if (response.status === 401) {
      irAlLogin();
      return null;
    }
    return response.ok ? response.json() : null;
  }

  async function seguirConectado() {
    try {
      const estado = await renovar();
      if (estado) ocultarAviso();
    } catch (error) {
      console.error(error);
    }
  }

  async function consultarEstado() {
    try {
      if (!avisoVisible && huboInteraccion && Date.now() - ultimaRenovacion >= MINIMO_ENTRE_RENOVACIONES_MS) {
        await renovar();
      }

      const response = await fetch(`${API_URL}/auth/sesion`, {
        credentials: CREDENCIALES,
        headers: { "X-Actividad": "pasiva" }
      });

      if (response.status === 401) {
        irAlLogin();
        return;
      }
      if (!response.ok) return;

      const estado = await response.json();
      segundosAviso = estado.aviso_segundos;

      if (estado.segundos_restantes <= segundosAviso) {
        if (!avisoVisible) mostrarAviso(estado.segundos_restantes);
      } else if (avisoVisible) {
        ocultarAviso();
      }
    } catch (error) {
      console.error(error);
    }
  }

  function registrarInteraccion() {
    if (!avisoVisible) huboInteraccion = true;
  }

  ["click", "keydown", "scroll", "touchstart", "mousemove"].forEach(evento => {
    window.addEventListener(evento, registrarInteraccion, { passive: true });
  });

  cargarEstilos();
  consultarEstado();
  setInterval(consultarEstado, INTERVALO_CONSULTA_MS);
})();
