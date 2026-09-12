# Incremento 2 — reparto del trabajo

**Entrega:** 2026-09-13 · **Desarrollo:** 2026-09-01 → 2026-09-11
**28 RF · 176 HH · avance acumulado 75,00 %**

El alcance sale de **Backlog.xlsx, hoja «Sprint Backlog-Incremento 2»**. Ese archivo manda: si cambia, hay
que volver a cuadrar el informe y estas fichas contra él.

## Cómo empezar

Consulta tu ficha en la tabla de responsabilidades y utiliza los scripts del proyecto:

```bash
bash scripts/doctor.sh     # qué falta y cómo se arregla
bash scripts/setup.sh      # arreglarlo todo
bash scripts/dev.sh        # levantar el sistema
bash scripts/test.sh       # ejecutar las pruebas
```

## Quién hace qué

| Integrante | Módulo | RF | HH | Requerimientos | Rama |
|---|---|---:|---:|---|---|
| [Matías Rodríguez](matias-rodriguez.md) | Ciclo de vida de la tarea | 6 | 30 | RF63, RF64, RF65, RF69, RF68, RF16 | `feature/inc2-tareas-ciclo-vida` |
| [Benjamín Contreras](benjamin-contreras.md) | Clientes y generación de reportes | 4 | 28 | RF05, RF61, RF31, RF32 | `feature/inc2-clientes-reportes` |
| [Renato Villalobos](renato-villalobos.md) | Seguridad y exportación a PDF | 3 | 26 | RF26, RF38, RF34 | `feature/inc2-seguridad-export` |
| [Elías Alarcón](elias-alarcon.md) | Dashboard y exportación a Excel | 5 | 26 | RF42, RF43, RF48, RF50, RF35 | `feature/inc2-dashboard-export` |
| [Vicente Barahona](vicente-barahona.md) | Notificaciones y productividad | 4 | 26 | RF52, RF51, RF53, RF39 | `feature/inc2-notificaciones` |
| [Carlos Castro](carlos-castro.md) | Documentos y observaciones de cliente | 3 | 20 | RF07, RF08, RF09 | `feature/inc2-documental-cliente` |
| [Iván Gómez](ivan-gomez.md) | Adjuntos de tarea y redistribución | 3 | 20 | RF54, RF55, RF19 | `feature/inc2-adjuntos-tarea` |

## Interfaces compartidas

Son los puntos donde el trabajo de uno bloquea al de otro. Resuélvanlos el
primer día; el módulo de reportes está repartido entre cuatro personas y es el
que más coordinación exige.

| Interfaz | La define | La consumen |
|---|---|---|
| Función que genera una notificación | Vicente Barahona | Matías Rodríguez, Renato Villalobos |
| Formato de respuesta del módulo de reportes | Benjamín Contreras | Renato Villalobos, Elías Alarcón |
| Capa de consulta compartida para exportar | renato-villalobos y elias-alarcon en conjunto | — |
| Endpoints sobre la tabla DOCUMENTO | carlos-castro e ivan-gomez en conjunto | — |
| Estructura de la vista frontend/reportes/ | quien llegue primero | Benjamín Contreras, Renato Villalobos, Elías Alarcón, Vicente Barahona |

## Orden obligado del módulo de reportes

1. **Benjamín** cierra la generación (RF31, RF32) y publica el formato de la respuesta.
2. **Renato** añade el filtro por rango de fechas (RF38) sobre ese endpoint.
3. **Renato** (PDF, RF34) y **Elías** (Excel, RF35) construyen la exportación sobre
   la misma capa de consulta, para que los dos archivos no puedan divergir.
4. **Vicente** (RF39) hace su propia agregación; no depende de los anteriores,
   pero comparte la vista `frontend/reportes/`.

## Definición de terminado

Un RF está listo cuando cumple las cinco condiciones:

1. Funciona en local contra MySQL.
2. Hay un commit **propio**, en la rama propia, con el código del RF en el mensaje.
3. Hay una **captura de pantalla** de la prueba funcional, con el nombre del RF.
4. La fila está actualizada en la hoja «Pila del Sprint» de la bitácora.
5. Hay un Pull Request abierto hacia `main`.

Sin el punto 3 el RF no se puede documentar en el capítulo 10 del informe, y sin
el punto 2 no acredita participación individual en la evaluación.
