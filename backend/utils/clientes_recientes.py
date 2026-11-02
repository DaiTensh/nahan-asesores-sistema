PARAMETRO_CLIENTES_RECIENTES = "CLIENTES_RECIENTES_LIMITE"
CLIENTES_RECIENTES_DEFECTO = 5
CLIENTES_RECIENTES_RANGO = (1, 20)


def validar_limite_clientes_recientes(valor):
    if isinstance(valor, bool):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    if str(numero) != str(valor).strip():
        return None
    minimo, maximo = CLIENTES_RECIENTES_RANGO
    return numero if minimo <= numero <= maximo else None


def leer_limite_clientes_recientes(cursor):
    cursor.execute(
        "SELECT valor_parametro FROM parametros_sistema WHERE nombre_parametro = %s",
        (PARAMETRO_CLIENTES_RECIENTES,),
    )
    fila = cursor.fetchone()
    valor = fila.get("valor_parametro") if fila else None
    return validar_limite_clientes_recientes(valor) or CLIENTES_RECIENTES_DEFECTO