function configurarPanelAlta({ botonId, panelId, primerCampoId, botonCerrarId } = {}) {
  const boton = document.getElementById(botonId);
  const panel = document.getElementById(panelId);
  if (!boton || !panel) return null;

  const primerCampo = primerCampoId ? document.getElementById(primerCampoId) : null;
  const botonCerrar = botonCerrarId ? document.getElementById(botonCerrarId) : null;

  if (!boton.getAttribute("aria-controls")) boton.setAttribute("aria-controls", panelId);
  panel.hidden = true;
  boton.setAttribute("aria-expanded", "false");

  const estaAbierto = () => !panel.hidden;
  const abrir = () => {
    panel.hidden = false;
    boton.setAttribute("aria-expanded", "true");
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

  return { abrir, cerrar, estaAbierto };
}
