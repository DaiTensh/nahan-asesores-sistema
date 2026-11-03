"""Escritura de hojas de cálculo (openpyxl) para las exportaciones a Excel."""


def escribir_filas(hoja, filas, fila_inicial=1):
    """Escribe `filas` en `hoja` desde `fila_inicial` y devuelve la fila siguiente a la última escrita.

    Los textos del usuario son datos, nunca fórmulas ejecutables: una celda que openpyxl tomaría por
    fórmula (empieza con «=») se deja como texto.

    No usa `hoja.append` seguido de `hoja[hoja.max_row]`: `max_row` y `max_column` recorren todas las
    celdas en cada llamada y el tiempo de la exportación crecía con el cuadrado de las filas (con 5.000
    clientes, más de 5 s solo en armar el libro).
    """
    numero = fila_inicial
    for valores in filas:
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=numero, column=columna, value=valor)
            if celda.data_type == "f":
                celda.data_type = "s"
        numero += 1
    return numero
