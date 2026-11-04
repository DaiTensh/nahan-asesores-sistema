// Nombres legibles de las acciones que registra AUDITORIA. El código interno
// (CLIENTE_CREADO) sigue siendo el valor de los filtros y de la API: esto solo
// cambia lo que ve la persona en pantalla.
(function () {
  const ETIQUETAS = {
    LOGIN: "Inicio de sesión",
    LOGOUT: "Cierre de sesión",
    CIERRE_INACTIVIDAD: "Sesión cerrada por inactividad",
    CONTRASENA_RESTABLECIDA: "Contraseña restablecida",
    USUARIO_CREADO: "Usuario creado",
    USUARIO_MODIFICADO: "Usuario modificado",
    USUARIO_DESACTIVADO: "Usuario desactivado",
    ROL_USUARIO_MODIFICADO: "Rol de usuario modificado",
    CONFIGURAR_SESION: "Configuración de sesión modificada",
    CONFIGURAR_CLIENTES_RECIENTES: "Configuración de clientes recientes modificada",
    CLIENTE_CREADO: "Cliente creado",
    CLIENTE_MODIFICADO: "Datos del cliente modificados",
    CAMBIO_ESTADO: "Cambio de estado del cliente",
    DESHABILITAR: "Cliente deshabilitado",
    ELIMINACION_DEFINITIVA: "Cliente eliminado definitivamente",
    OBSERVACION_CREADA: "Observación registrada",
    TAREA_CREADA: "Tarea creada",
    EDICION: "Tarea editada",
    CAMBIO_ESTADO_TAREA: "Cambio de estado de la tarea",
    REASIGNACION: "Tarea reasignada",
    REASIGNACION_MASIVA: "Tarea reasignada (masivo)",
    ENVIO_REVISION: "Tarea enviada a revisión",
    APROBAR_REVISION: "Revisión aprobada",
    RECHAZAR_REVISION: "Revisión rechazada",
    COMPLETAR_TAREA: "Tarea completada",
    CANCELAR_TAREA: "Tarea cancelada",
    DOCUMENTO_REFERENCIADO: "Documento referenciado",
    DOCUMENTO_ADJUNTADO: "Documento adjuntado",
    DESCARGA: "Documento descargado",
    TEMPORIZADOR_INICIADO: "Temporizador iniciado",
    TEMPORIZADOR_DETENIDO: "Temporizador detenido",
    CONFIGURAR_TARIFA_GENERAL: "Tarifa general modificada",
    TARIFA_AREA_DEFINIDA: "Tarifa de área definida",
    TARIFA_AREA_ELIMINADA: "Tarifa de área eliminada",
    RESPALDO_MANUAL: "Respaldo manual realizado",
    RESPALDO_MANUAL_FALLIDO: "Respaldo manual fallido",
    RESTAURACION_RESPALDO: "Restauración de respaldo realizada",
    RESTAURACION_FALLIDA: "Restauración de respaldo fallida",
    RESTAURACION_RECHAZADA: "Restauración rechazada (contraseña incorrecta)"
  };

  window.etiquetaAccionAuditoria = function (codigo) {
    if (ETIQUETAS[codigo]) return ETIQUETAS[codigo];
    const texto = String(codigo || "").replace(/_/g, " ").toLowerCase();
    return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "-";
  };
})();
