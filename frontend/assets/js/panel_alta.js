const instanciasPanelAlta = new WeakMap();

function configurarPanelAlta({ botonId, panelId, primerCampoId, botonCerrarId, alAbrir } = {}) {
  const boton = document.getElementById(botonId);
  const panel = document.getElementById(panelId);
  if (!boton || !panel) return null;
  if (instanciasPanelAlta.has(boton)) return instanciasPanelAlta.get(boton);

  const primerCampo = primerCampoId ? document.getElementById(primerCampoId) : null;
  const botonCerrar = botonCerrarId ? document.getElementById(botonCerrarId) : null;

  if (!boton.getAttribute("aria-controls")) boton.setAttribute("aria-controls", panelId);
  panel.hidden = true;
  boton.setAttribute("aria-expanded", "false");

  const estaAbierto = () => !panel.hidden;
  const abrir = () => {
    panel.hidden = false;
    boton.setAttribute("aria-expanded", "true");
    if (typeof alAbrir === "function") alAbrir();
    if (primerCampo) primerCampo.focus({ preventScroll: true });
    if (typeof panel.scrollIntoView === "function") {
      panel.scrollIntoView({ block: "nearest" });
    }
  };
  const cerrar = () => {
    panel.hidden = true;
    boton.setAttribute("aria-expanded", "false");
    boton.focus();
  };

  boton.addEventListener("click", () => {
    if (estaAbierto()) cerrar();
    else abrir();
  });
  if (botonCerrar) botonCerrar.addEventListener("click", cerrar);

  const instancia = { abrir, cerrar, estaAbierto };
  instanciasPanelAlta.set(boton, instancia);
  return instancia;
}
