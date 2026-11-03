// Validación del RUT chileno (módulo 11). Es la misma regla que aplica el
// servidor (backend/utils/validaciones_cliente.py); aquí solo sirve para avisar
// antes de enviar el formulario. El servidor siempre vuelve a validar.
(function () {
  const FORMATO = /^([0-9]{1,2})\.?([0-9]{3})\.?([0-9]{3})-?([0-9kK])$/;
  const RUT_MINIMO = 1000000;

  function calcularDigito(cuerpo) {
    let suma = 0;
    let factor = 2;
    for (const cifra of String(Number(cuerpo)).split("").reverse()) {
      suma += Number(cifra) * factor;
      factor = factor === 7 ? 2 : factor + 1;
    }
    const resto = 11 - (suma % 11);
    return resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  }

  // Devuelve { valido, canonico, mensaje }; canonico tiene la forma «12.345.678-5».
  function validar(texto) {
    const coincidencia = FORMATO.exec(String(texto || "").trim());
    if (!coincidencia) {
      return { valido: false, canonico: null, mensaje: "El RUT no tiene un formato válido (ejemplo: 12.345.678-5)." };
    }
    const [, uno, dos, tres, digito] = coincidencia;
    const cuerpo = `${uno}${dos}${tres}`;
    const canonico = `${Number(uno)}.${dos}.${tres}-${digito.toUpperCase()}`;
    if (Number(cuerpo) < RUT_MINIMO || calcularDigito(cuerpo) !== digito.toUpperCase()) {
      return { valido: false, canonico: null, mensaje: "El RUT no es válido: revise el número y el dígito verificador." };
    }
    return { valido: true, canonico, mensaje: "" };
  }

  window.Rut = { validar, calcularDigito };
})();
