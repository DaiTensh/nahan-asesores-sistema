// RF74 — Definiendo la tarifa por hora (solo administradores). La autorización
// real se valida en el backend.
(function () {
  const API_URL = window.API_CONFIG.API_URL;
  let moneda = "CLP";

  function mostrarMensaje(id, texto, tipo) {
    const mensaje = document.getElementById(id);
    mensaje.textContent = texto || "";
    mensaje.className = tipo ? `mensaje ${tipo}` : "mensaje";
  }

  function formatearMonto(valor) {
    if (valor === null || valor === undefined) return "-";
    return `${Number(valor).toLocaleString("es-CL", { maximumFractionDigits: 2 })} ${moneda}`;
  }

  function celda(texto) {
    const td = document.createElement("td");
    td.textContent = texto;
    return td;
  }

  async function pedir(ruta, opciones) {
    const response = await fetch(`${API_URL}${ruta}`, { credentials: window.API_CONFIG.credentials, ...opciones });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, data };
  }

  function enviarJson(metodo, cuerpo) {
    return { method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) };
  }

  function filaArea(area) {
    const fila = document.createElement("tr");
    fila.appendChild(celda(area.nombre_area));
    fila.appendChild(celda(area.valor_hora === null ? "Usa la tarifa general" : formatearMonto(area.valor_hora)));
    fila.appendChild(celda(formatearMonto(area.tarifa_aplicada)));

    const tdValor = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.className = "form-input tarifas-valor-nuevo";
    input.min = "1";
    input.max = "10000000";
    input.step = "0.01";
    input.id = `tarifaArea${area.id_area}`;
    input.setAttribute("aria-label", `Nuevo valor por hora del área ${area.nombre_area}`);
    tdValor.appendChild(input);
    fila.appendChild(tdValor);

    const tdAcciones = document.createElement("td");
    const guardar = document.createElement("button");
    guardar.type = "button";
    guardar.className = "btn btn-primary btn-sm";
    guardar.textContent = "Definir";
    guardar.addEventListener("click", () => definirArea(area, input));
    tdAcciones.appendChild(guardar);

    if (area.valor_hora !== null) {
      const quitar = document.createElement("button");
      quitar.type = "button";
      quitar.className = "btn btn-secondary btn-sm";
      quitar.textContent = "Usar la general";
      quitar.addEventListener("click", () => quitarArea(area));
      tdAcciones.appendChild(document.createTextNode(" "));
      tdAcciones.appendChild(quitar);
    }
    fila.appendChild(tdAcciones);
    return fila;
  }

  async function cargar() {
    try {
      const { ok, data } = await pedir("/tarifas");
      if (!ok) {
        mostrarMensaje("mensajeGeneral", data.error || "No fue posible cargar las tarifas.", "error");
        return;
      }
      moneda = data.general.moneda;
      document.getElementById("textoMoneda").textContent = moneda;
      document.getElementById("inputTarifaGeneral").value = data.general.valor_hora;
      const tabla = document.getElementById("tablaTarifasAreas");
      tabla.textContent = "";
      data.areas.forEach(area => tabla.appendChild(filaArea(area)));
    } catch (error) {
      console.error(error);
      mostrarMensaje("mensajeGeneral", "No fue posible conectar con el servidor.", "error");
    }
  }

  async function guardarGeneral(event) {
    event.preventDefault();
    const valor = Number(document.getElementById("inputTarifaGeneral").value);
    if (!await confirmarAccion(`¿Cambiar la tarifa general a ${formatearMonto(valor)} por hora?`, "advertencia")) return;
    const { ok, data } = await pedir("/tarifas/general", enviarJson("PUT", { valor_hora: valor }));
    mostrarMensaje("mensajeGeneral", ok ? "Tarifa general actualizada." : (data.error || "No se pudo guardar la tarifa."), ok ? "success" : "error");
    if (ok) await cargar();
  }

  async function definirArea(area, input) {
    const valor = Number(input.value);
    if (!input.value || !(valor > 0)) {
      mostrarMensaje("mensajeAreas", "Ingrese un valor por hora mayor que cero.", "error");
      return;
    }
    if (!await confirmarAccion(`¿Definir ${formatearMonto(valor)} por hora para el área ${area.nombre_area}?`, "advertencia")) return;
    const { ok, data } = await pedir(`/tarifas/areas/${area.id_area}`, enviarJson("PUT", { valor_hora: valor }));
    mostrarMensaje("mensajeAreas", ok ? `Tarifa del área ${area.nombre_area} actualizada.` : (data.error || "No se pudo guardar la tarifa."), ok ? "success" : "error");
    if (ok) await cargar();
  }

  async function quitarArea(area) {
    if (!await confirmarAccion(`¿Quitar la tarifa propia del área ${area.nombre_area}? Volverá a usar la tarifa general.`, "advertencia")) return;
    // Sin cuerpo no se declara Content-Type: el backend valida todo cuerpo JSON.
    const { ok, data } = await pedir(`/tarifas/areas/${area.id_area}`, { method: "DELETE" });
    mostrarMensaje("mensajeAreas", ok ? `El área ${area.nombre_area} usa la tarifa general.` : (data.error || "No se pudo quitar la tarifa."), ok ? "success" : "error");
    if (ok) await cargar();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("formTarifaGeneral").addEventListener("submit", guardarGeneral);
    cargar();
  });
})();
