// RF18 — Agrupa el listado de tareas pendientes por cliente, prioridad o responsable.
// Es una función pura sobre la lista que la pantalla ya cargó: no hace consultas nuevas.
(function () {
  const ORDEN_PRIORIDAD = ["URGENTE", "ALTA", "MEDIA", "BAJA"];
  const ETIQUETAS_PRIORIDAD = { URGENTE: "Urgente", ALTA: "Alta", MEDIA: "Media", BAJA: "Baja" };

  const CRITERIOS = {
    cliente: {
      nombre: "Cliente",
      clave: tarea => String(tarea.id_cliente ?? tarea.cliente),
      etiqueta: tarea => tarea.cliente
    },
    prioridad: {
      nombre: "Prioridad",
      clave: tarea => String(tarea.prioridad),
      etiqueta: tarea => ETIQUETAS_PRIORIDAD[tarea.prioridad] || String(tarea.prioridad)
    },
    responsable: {
      nombre: "Responsable",
      clave: tarea => String(tarea.id_responsable ?? tarea.responsable),
      etiqueta: tarea => tarea.responsable
    }
  };

  function compararTexto(a, b) {
    return String(a).localeCompare(String(b), "es", { sensitivity: "base" });
  }

  // Devuelve [{ clave, etiqueta, tareas }]. Las tareas conservan el orden con que llegaron;
  // los grupos van por orden alfabético, salvo la prioridad (de más a menos urgente).
  // Sin un criterio válido devuelve un único grupo con todas las tareas.
  function agrupar(tareas, criterio) {
    const definicion = CRITERIOS[criterio];
    if (!definicion) return [{ clave: "todas", etiqueta: "", tareas: [...tareas] }];

    const grupos = new Map();
    tareas.forEach(tarea => {
      const clave = definicion.clave(tarea);
      if (!grupos.has(clave)) grupos.set(clave, { clave, etiqueta: definicion.etiqueta(tarea), tareas: [] });
      grupos.get(clave).tareas.push(tarea);
    });

    const lista = [...grupos.values()];
    if (criterio === "prioridad") {
      const posicion = clave => {
        const indice = ORDEN_PRIORIDAD.indexOf(clave);
        return indice === -1 ? ORDEN_PRIORIDAD.length : indice;
      };
      return lista.sort((a, b) => posicion(a.clave) - posicion(b.clave));
    }
    return lista.sort((a, b) => compararTexto(a.etiqueta, b.etiqueta));
  }

  window.AgruparTareas = { CRITERIOS: Object.keys(CRITERIOS), nombreCriterio: criterio => (CRITERIOS[criterio] || {}).nombre || "", agrupar };
})();
