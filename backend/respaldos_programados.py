"""RF60 — Respaldos programados y operación desde consola.

Proceso programado (ver `deploy/systemd/nahan-respaldo.service|.timer`) que
hace el respaldo diario. Como el temporizador de systemd lanza un único
proceso por vez y el bloqueo de archivo impide que se solape con un respaldo
manual del administrador, no hay planificadores dentro de Gunicorn ni
dependencia de que alguien tenga abierta la página.

Se puede ejecutar a mano, sin depender del temporizador:

    python -m backend.respaldos_programados                     # respaldo programado
    python -m backend.respaldos_programados estado              # almacenamiento y último respaldo
    python -m backend.respaldos_programados verificar --id 12   # integridad, sin restaurar
    RESTAURACION_HABILITADA=true python -m backend.respaldos_programados restaurar \\
        --id 12 --confirmo-base nahan_asesores
    RESTAURACION_HABILITADA=true python -m backend.respaldos_programados restaurar \\
        --archivo nahan-respaldo-20261102T050000Z-1a2b3c4d.zip --confirmo-base nahan_asesores

La segunda forma de `restaurar` (`--archivo`) sirve cuando se perdió la base y
ya no hay historial: el paquete se verifica con el archivo .sha256 que queda a
su lado.

Códigos de salida: 0 correcto, 1 falló, 75 había otra operación en curso.
"""
import argparse
import logging
import sys

from backend.utils import respaldos as servicio

logger = logging.getLogger("backend.respaldos_programados")

SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_OCUPADO = 75


def _respaldar(tipo):
    try:
        resultado = servicio.ejecutar_respaldo(tipo)
    except servicio.OperacionEnCurso as error:
        logger.warning("Respaldo omitido: %s", error.mensaje)
        return SALIDA_OCUPADO
    except servicio.ErrorRespaldo as error:
        logger.error("El respaldo %s falló: %s", tipo, error.mensaje)
        return SALIDA_ERROR
    logger.info("Respaldo %s completado: %s (%s)", resultado["id_respaldo"], resultado["nombre_archivo"],
                resultado["detalle"])
    return SALIDA_OK


def _estado():
    estado = servicio.estado_del_sistema()
    almacenamiento = estado["almacenamiento"]
    print(f"Directorio: {almacenamiento['directorio'] or '(sin configurar)'}")
    for verificacion in almacenamiento["verificaciones"]:
        print(f"  [{verificacion['nivel']:<6}] {verificacion['mensaje']}")
    ultimo = estado["ultimo_exitoso"]
    print("Último respaldo exitoso:", f"#{ultimo['id_respaldo']} ({ultimo['tipo']}, {ultimo['fecha_fin']})"
          if ultimo else "ninguno")
    print("Restauración habilitada:", "sí" if estado["restauracion_habilitada"] else "no")
    return SALIDA_OK if almacenamiento["apto"] else SALIDA_ERROR


def _verificar(id_respaldo):
    try:
        resumen = servicio.verificar_respaldo(id_respaldo)
    except servicio.ErrorRespaldo as error:
        logger.error("Verificación fallida: %s", error.mensaje)
        return SALIDA_ERROR
    print(f"Respaldo {id_respaldo} íntegro: {resumen['tablas']} tablas, {resumen['filas']} filas, "
          f"{resumen['adjuntos']} adjuntos.")
    return SALIDA_OK


def _restaurar(args):
    config = servicio.ConfigRespaldo()
    if args.confirmo_base != config.restauracion_db_nombre:
        logger.error("La base de destino es «%s»; debe repetirla en --confirmo-base para continuar.",
                     config.restauracion_db_nombre)
        return SALIDA_ERROR
    try:
        resultado = servicio.ejecutar_restauracion(
            args.id, config=config, registro=servicio.RegistroMySQL(tolerante=True),
            nombre_archivo=args.archivo)
    except servicio.OperacionEnCurso as error:
        logger.warning("Restauración omitida: %s", error.mensaje)
        return SALIDA_OCUPADO
    except servicio.ErrorRespaldo as error:
        logger.error("La restauración falló: %s %s", error.mensaje, getattr(error, "recuperacion", ""))
        return SALIDA_ERROR
    print(f"Restauración completada: {resultado['detalle']}")
    for advertencia in resultado["advertencias"]:
        print(f"Aviso: {advertencia}")
    return SALIDA_OK


def crear_parser():
    parser = argparse.ArgumentParser(prog="python -m backend.respaldos_programados", description=__doc__.split("\n")[0])
    subcomandos = parser.add_subparsers(dest="comando")
    respaldar = subcomandos.add_parser("respaldar", help="hace un respaldo (por defecto: programado)")
    respaldar.add_argument("--tipo", choices=("programado", "manual"), default="programado")
    subcomandos.add_parser("estado", help="muestra el almacenamiento y el último respaldo")
    verificar = subcomandos.add_parser("verificar", help="comprueba la integridad de un respaldo")
    verificar.add_argument("--id", type=int, required=True)
    restaurar = subcomandos.add_parser("restaurar", help="restaura un respaldo (requiere RESTAURACION_HABILITADA)")
    origen = restaurar.add_mutually_exclusive_group(required=True)
    origen.add_argument("--id", type=int, help="id del respaldo en el historial")
    origen.add_argument("--archivo", help="nombre del paquete en RESPALDO_DIR (sin historial)")
    restaurar.add_argument("--confirmo-base", required=True,
                           help="nombre de la base que se sobrescribirá, escrito de nuevo")
    return parser


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = crear_parser().parse_args(argv)

    if args.comando in (None, "respaldar"):
        tipo = getattr(args, "tipo", "programado")
        return _respaldar(servicio.TIPO_PROGRAMADO if tipo == "programado" else servicio.TIPO_MANUAL)
    if args.comando == "estado":
        return _estado()
    if args.comando == "verificar":
        return _verificar(args.id)
    return _restaurar(args)


if __name__ == "__main__":
    sys.exit(main())
