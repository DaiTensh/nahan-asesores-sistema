// Formato único de fecha y hora de la interfaz: dd-mm-aaaa hh:mm, con reloj de 24 horas (H-20).
//
//   formatearFechaHora24("2026-11-05T13:01:05")                          → "05-11-2026 13:01"
//   formatearFechaHora24("Thu, 05 Nov 2026 01:25:10 GMT", { utc: true }) → "05-11-2026 01:25"
//
// `utc: true` es para las fechas que el servidor entrega como hora local rotulada «GMT»: se muestran
// en UTC para no desplazarlas. Si el valor no es una fecha, se devuelve tal cual.
(function () {
  if (window.formatearFechaHora24) return;

  window.formatearFechaHora24 = function (valor, { utc = false } = {}) {
    const fecha = valor instanceof Date ? valor : new Date(valor);
    if (Number.isNaN(fecha.getTime())) return String(valor ?? "");

    const partes = {};
    new Intl.DateTimeFormat("es-CL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      ...(utc ? { timeZone: "UTC" } : {})
    }).formatToParts(fecha).forEach(parte => { partes[parte.type] = parte.value; });

    return `${partes.day}-${partes.month}-${partes.year} ${partes.hour}:${partes.minute}`;
  };
})();
