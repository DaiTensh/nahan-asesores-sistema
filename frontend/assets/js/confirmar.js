// RF67 — Mensajes de confirmación diferenciados según la criticidad de la acción.
//
//   const acepta = await confirmarAccion("¿Desea deshabilitar este usuario?", "critica");
//
// Niveles: "critica" (acción irreversible: rojo, el foco inicia en «Cancelar»), "advertencia"
// (cambia datos que otros usan: ámbar) y "normal" (crear o guardar: azul). Devuelve una promesa
// con true si la persona confirma y false si cancela (botón, Esc o clic fuera del cuadro). Una
// acción cancelada no debe hacer nada: quien llama solo sigue si el resultado es true.
(function () {
  const NIVELES = {
    critica: { titulo: "Acción irreversible", confirmar: "Sí, continuar", icono: "!" },
    advertencia: { titulo: "Confirmar cambio", confirmar: "Confirmar", icono: "?" },
    normal: { titulo: "Confirmar acción", confirmar: "Aceptar", icono: "?" }
  };
  const SELECTOR_FOCO =
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function antecesoresDe(elemento) {
    const antecesores = [];
    let actual = elemento && elemento !== document.body ? elemento.parentElement : null;
    while (actual && actual !== document.body) {
      antecesores.push(actual);
      actual = actual.parentElement;
    }
    return antecesores;
  }

  function restaurarFoco(elementoPrevio, antecesoresPrevios) {
    if (elementoPrevio && elementoPrevio !== document.body
        && elementoPrevio.isConnected !== false && !elementoPrevio.disabled) {
      elementoPrevio.focus({ preventScroll: true });
      return;
    }

    for (const antecesor of antecesoresPrevios) {
      if (antecesor.isConnected === false) continue;
      const alternativa = antecesor.querySelector(SELECTOR_FOCO);
      if (alternativa && alternativa !== elementoPrevio
          && alternativa.isConnected !== false && !alternativa.disabled) {
        alternativa.focus({ preventScroll: true });
        return;
      }
    }

    const encabezado = document.querySelector("main h1");
    if (encabezado && encabezado.isConnected !== false) {
      if (!encabezado.hasAttribute("tabindex")) encabezado.setAttribute("tabindex", "-1");
      encabezado.focus({ preventScroll: true });
    }
  }

  // La hoja de estilos se pide sola, junto a este archivo, para no editar cada página.
  const origen = document.currentScript && document.currentScript.src;
  if (origen && !document.querySelector("link[data-confirmacion]")) {
    const enlace = document.createElement("link");
    enlace.rel = "stylesheet";
    enlace.href = origen.replace(/js\/confirmar\.js.*$/, "css/confirmacion.css");
    enlace.setAttribute("data-confirmacion", "");
    document.head.appendChild(enlace);
  }

  window.confirmarAccion = function (mensaje, nivel = "normal") {
    const config = NIVELES[nivel] || NIVELES.normal;
    const nivelUsado = NIVELES[nivel] ? nivel : "normal";
    const elementoPrevio = document.activeElement;
    const antecesoresPrevios = antecesoresDe(elementoPrevio);

    return new Promise(resolve => {
      const fondo = document.createElement("div");
      fondo.className = "confirmacion-fondo";

      const cuadro = document.createElement("div");
      cuadro.className = `confirmacion-cuadro confirmacion-${nivelUsado}`;
      cuadro.setAttribute("role", "alertdialog");
      cuadro.setAttribute("aria-modal", "true");
      const idTitulo = `confirmacion-titulo-${Date.now()}`;
      const idMensaje = `confirmacion-mensaje-${Date.now()}`;
      cuadro.setAttribute("aria-labelledby", idTitulo);
      cuadro.setAttribute("aria-describedby", idMensaje);

      const cabecera = document.createElement("div");
      cabecera.className = "confirmacion-cabecera";
      const icono = document.createElement("span");
      icono.className = "confirmacion-icono";
      icono.setAttribute("aria-hidden", "true");
      icono.textContent = config.icono;
      const titulo = document.createElement("h2");
      titulo.id = idTitulo;
      titulo.className = "confirmacion-titulo";
      titulo.textContent = config.titulo;
      cabecera.append(icono, titulo);

      const texto = document.createElement("p");
      texto.id = idMensaje;
      texto.className = "confirmacion-mensaje";
      texto.textContent = mensaje;

      const acciones = document.createElement("div");
      acciones.className = "confirmacion-acciones";
      const cancelar = document.createElement("button");
      cancelar.type = "button";
      cancelar.className = "btn btn-secondary";
      cancelar.textContent = "Cancelar";
      const aceptar = document.createElement("button");
      aceptar.type = "button";
      aceptar.className = nivelUsado === "critica" ? "btn btn-danger" : "btn btn-primary";
      aceptar.textContent = config.confirmar;
      acciones.append(cancelar, aceptar);

      cuadro.append(cabecera, texto, acciones);
      fondo.appendChild(cuadro);

      function cerrar(resultado) {
        document.removeEventListener("keydown", alTeclear, true);
        fondo.remove();
        restaurarFoco(elementoPrevio, antecesoresPrevios);
        resolve(resultado);
      }

      function alTeclear(evento) {
        if (evento.key === "Escape") {
          evento.preventDefault();
          cerrar(false);
        } else if (evento.key === "Tab") {
          const botones = [cancelar, aceptar];
          const indice = botones.indexOf(document.activeElement);
          evento.preventDefault();
          botones[(indice + (evento.shiftKey ? -1 : 1) + botones.length) % botones.length].focus();
        }
      }

      cancelar.addEventListener("click", () => cerrar(false));
      aceptar.addEventListener("click", () => cerrar(true));
      fondo.addEventListener("mousedown", evento => { if (evento.target === fondo) cerrar(false); });
      document.addEventListener("keydown", alTeclear, true);

      document.body.appendChild(fondo);
      // En lo irreversible, Enter no debe confirmar por descuido: el foco empieza en «Cancelar».
      (nivelUsado === "critica" ? cancelar : aceptar).focus();
    });
  };

  // Aviso de un solo botón con el aspecto de las confirmaciones: reemplaza al alert() nativo.
  //
  //   avisarAccion("No se pudo asignar la tarea", "error");   // "error", "advertencia", "exito" o "info"
  //
  // Devuelve una promesa que se cumple al cerrarlo (botón, Esc o clic fuera del cuadro). No bloquea la
  // página: quien necesite esperar (por ejemplo antes de redirigir) debe usar await.
  const AVISOS = {
    error: { titulo: "No se pudo completar", icono: "!", clase: "confirmacion-critica" },
    advertencia: { titulo: "Revise la información", icono: "!", clase: "confirmacion-advertencia" },
    exito: { titulo: "Listo", icono: "✓", clase: "confirmacion-normal" },
    info: { titulo: "Aviso", icono: "i", clase: "confirmacion-normal" }
  };

  window.avisarAccion = function (mensaje, tipo = "info") {
    const config = AVISOS[tipo] || AVISOS.info;
    const elementoPrevio = document.activeElement;
    const antecesoresPrevios = antecesoresDe(elementoPrevio);

    return new Promise(resolve => {
      const fondo = document.createElement("div");
      fondo.className = "confirmacion-fondo";

      const cuadro = document.createElement("div");
      cuadro.className = `confirmacion-cuadro ${config.clase}`;
      cuadro.setAttribute("role", "alertdialog");
      cuadro.setAttribute("aria-modal", "true");
      const idTitulo = `aviso-titulo-${Date.now()}`;
      const idMensaje = `aviso-mensaje-${Date.now()}`;
      cuadro.setAttribute("aria-labelledby", idTitulo);
      cuadro.setAttribute("aria-describedby", idMensaje);

      const cabecera = document.createElement("div");
      cabecera.className = "confirmacion-cabecera";
      const icono = document.createElement("span");
      icono.className = "confirmacion-icono";
      icono.setAttribute("aria-hidden", "true");
      icono.textContent = config.icono;
      const titulo = document.createElement("h2");
      titulo.id = idTitulo;
      titulo.className = "confirmacion-titulo";
      titulo.textContent = config.titulo;
      cabecera.append(icono, titulo);

      const texto = document.createElement("p");
      texto.id = idMensaje;
      texto.className = "confirmacion-mensaje";
      texto.textContent = mensaje;

      const acciones = document.createElement("div");
      acciones.className = "confirmacion-acciones";
      const aceptar = document.createElement("button");
      aceptar.type = "button";
      aceptar.className = "btn btn-primary";
      aceptar.textContent = "Aceptar";
      acciones.appendChild(aceptar);

      cuadro.append(cabecera, texto, acciones);
      fondo.appendChild(cuadro);

      function cerrar() {
        document.removeEventListener("keydown", alTeclear, true);
        fondo.remove();
        restaurarFoco(elementoPrevio, antecesoresPrevios);
        resolve();
      }

      function alTeclear(evento) {
        if (evento.key === "Escape") {
          evento.preventDefault();
          cerrar();
        } else if (evento.key === "Tab") {
          evento.preventDefault();
          aceptar.focus();
        }
      }

      aceptar.addEventListener("click", cerrar);
      fondo.addEventListener("mousedown", evento => { if (evento.target === fondo) cerrar(); });
      document.addEventListener("keydown", alTeclear, true);

      document.body.appendChild(fondo);
      aceptar.focus();
    });
  };
})();
