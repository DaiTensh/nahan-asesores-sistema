---
name: soy-del-equipo
description: Prepara el entorno y arranca el trabajo de un integrante del Grupo 22 en el Incremento 2 de Nahan Asesores. Úsala cuando alguien se presente por su nombre ("hola, soy Renato", "soy Matías", "buenas, habla Elías") o pida empezar a trabajar en sus RF. Instala lo que falte, crea su rama e implementa los requerimientos que le tocan.
---

# Arranque de un integrante del Grupo 22

Alguien acaba de decir su nombre. Es un integrante del equipo que abre el
proyecto por primera vez o vuelve a trabajar en él. Tu tarea es dejarlo
programando, sin que tenga que saber nada del entorno.

Sigue los pasos en orden. No los saltes ni los reordenes.

## 1. Identifica a la persona

Lee `docs/incremento2/equipo.json` y busca el nombre en el campo `alias` de
cada integrante, sin distinguir mayúsculas ni tildes.

- Si coincide con uno: sigue.
- Si coincide con varios o con ninguno: **pregunta**, mostrando los siete
  nombres. No adivines y no inventes un integrante que no esté en el archivo.

Salúdalo por su nombre y dile en una línea qué módulo le toca y cuántos RF son.

## 2. Revisa el entorno

Ejecuta:

```bash
python scripts/doctor.py --json
```

Lee el campo `listo`.

- `true`: pasa al paso 4.
- `false`: dile en una frase qué falta —usando el campo `detalle` de los
  chequeos que fallaron— y pasa al paso 3.

Si `scripts/doctor.py` no existe o Python no está instalado, dile que instale
Python 3.10 o superior desde python.org y detente ahí.

## 3. Instala lo que falte

```bash
python scripts/setup.py
```

El instalador pregunta los datos de MySQL. **Deja que los conteste la persona**:
son de su máquina y tú no los sabes. Si te pide ayuda con MySQL:

- macOS: `brew install mysql && brew services start mysql`, usuario `root` sin contraseña.
- Windows: MySQL Community Server desde dev.mysql.com; la contraseña es la que puso en el instalador.
- Linux: `sudo apt install mysql-server && sudo systemctl start mysql`.

Cuando termine, vuelve a correr `python scripts/doctor.py` y confirma que quedó
en verde. Si sigue fallando, **muéstrale el error tal cual y detente**. No
inventes una solución ni sigas como si hubiera funcionado.

## 4. Deja la rama lista

```bash
git fetch origin
git checkout main
git pull origin main
```

Luego crea o retoma su rama, la del campo `rama` de su ficha:

```bash
git checkout -b <rama> origin/main    # si no existe
git checkout <rama>                    # si ya existe
```

Si `git status` muestra cambios sin commitear que no son suyos, **detente y
avísale** antes de tocar nada.

## 5. Carga su trabajo

Lee su ficha: `docs/incremento2/<slug>.md`. Ahí están sus RF con la descripción,
los archivos que toca, los criterios de aceptación y las dependencias con el
resto del equipo.

Lee también, completos, los archivos del módulo que va a modificar. Antes de
escribir una línea de código tienes que conocer el estilo que ya existe.

## 6. Propón el orden y empieza

Muéstrale sus RF en el orden en que conviene hacerlos —el de la ficha— y
pregúntale por cuál parte. Si te dice «el que quieras» o «empieza tú», toma el
primero.

Por cada RF:

1. Lee los archivos involucrados.
2. Explica en dos o tres líneas qué vas a cambiar y espera su visto bueno.
3. Implementa respetando las convenciones de `CLAUDE.md` y `docs/development.md`.
4. Pruébalo de verdad: levanta el sistema con `python scripts/dev.py` y ejercita
   la funcionalidad. **Nunca digas que algo funciona sin haberlo ejecutado.**
5. Commit con el código del RF al principio del mensaje:
   `git commit -m "RF63 Detalle completo de tarea"`.
6. Recuérdale la captura de pantalla: sin ella el RF no se puede documentar en
   el capítulo 10 del informe.

El commit lo hace **él**, con su propia cuenta de git. Es lo que acredita su
participación individual en la evaluación. No commitees en su nombre salvo que
te lo pida expresamente.

## 7. Al terminar cada RF

Dile que actualice su fila en `Bitacora Sprint 2 - Grupo 22.xlsx`, hoja
«Pila del Sprint», con la fecha real y las HH reales.

Cuando cierre todos sus RF, `git push -u origin <rama>` y Pull Request hacia
`main`.

## Reglas que no se negocian

- No cambies la arquitectura: Flask con blueprints, JavaScript sin frameworks, MySQL.
- SQL siempre parametrizado. Nunca concatenes valores en la consulta.
- Todo dato que venga de la base y se inserte en `innerHTML` pasa por
  `escapeHtml()`; las URL por `sanitizarUrl()`. Ambas ya existen en
  `frontend/clientes/ficha_cliente.js`.
- No toques los archivos de otro integrante sin avisarle. La sección
  «coordinación» de `equipo.json` dice quién define cada interfaz compartida.
- Si algo no está claro o falta información, dilo. No lo supongas.
