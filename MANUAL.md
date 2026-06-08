# Manual de uso — Calculadora de Horas Extra ECC

Herramienta para calcular automáticamente las horas extras de los empleados a partir del reporte mensual de Jibble.

---

## ¿Qué necesitas para empezar?

- Una computadora con macOS o Windows
- El archivo `.xlsx` que exporta Jibble cada mes (pestaña **Raw Timesheets**)
- La lista de **días aprobados** por empleado (en una hoja del mismo Excel o en un archivo aparte)
- El programa ya instalado (ver sección siguiente)

---

## Instalación — solo la primera vez

> Si alguien ya lo instaló por ti, ve directamente a **"Cómo abrir la aplicación"**.

### Paso 1 — Instalar Python

1. Abre el navegador y entra a **https://www.python.org/downloads/**
2. Haz clic en el botón amarillo grande que dice **"Download Python 3.x.x"**
3. Ejecuta el instalador
   - **Windows**: marca la casilla **"Add Python to PATH"** antes de hacer clic en Install
   - **macOS**: sigue los pasos normales del instalador

### Paso 2 — Instalar las dependencias

1. Abre la **Terminal** (macOS) o el **Símbolo del sistema / CMD** (Windows)
2. Navega hasta la carpeta `ecc-overtime`:
   ```
   cd ruta/a/ecc-overtime
   ```
3. Ejecuta estos dos comandos, uno por uno:
   ```
   pip install uv
   uv venv .venv
   uv pip install pandas openpyxl streamlit
   ```

Listo. Esto solo se hace una vez.

---

## Cómo abrir la aplicación

Cada vez que quieras usar la calculadora:

**macOS / Linux:**
```
cd ruta/a/ecc-overtime
source .venv/bin/activate
streamlit run app.py
```

**Windows:**
```
cd ruta\a\ecc-overtime
.venv\Scripts\activate
streamlit run app.py
```

El navegador se va a abrir solo con la aplicación. Si no se abre, copia la dirección que aparece en la terminal (algo como `http://localhost:8501`) y pégala en el navegador.

---

## Configurar los sueldos de los empleados

> Esto solo hay que hacerlo cuando alguien nuevo entra o cambia su sueldo.

En la parte izquierda de la pantalla (el panel lateral), bajo **"Sueldos de empleados"**, hay una **tabla** con dos columnas: *Empleado* y *Salario mensual*.

Para editar:
1. Haz clic en la celda **Salario mensual** del empleado y escribe su sueldo
2. Para **agregar** a alguien nuevo, escribe su nombre y sueldo en la **fila vacía del final**
3. Para **quitar** a alguien, selecciona su fila (casilla a la izquierda) y presiona la papelera / tecla suprimir
4. Los cambios se aplican automáticamente al calcular

> **Importante:** el nombre del empleado tiene que ser exactamente igual a como aparece en Jibble, incluyendo tildes y mayúsculas.

Los siguientes empleados tienen sueldo en **0** y hay que completarlo antes de que aparezcan sus montos:
- Enrique Lantigua
- Jose Alberto de Jesus
- Maudeza Honore
- Xavier Celedonio

---

## Agregar días feriados

En el panel lateral, debajo de **"Feriados"**, hay una caja de texto. Escribe una fecha por línea en formato **AAAA-MM-DD**:

```
2026-01-01
2026-04-14
2026-05-01
```

Las horas trabajadas en esos días se calculan automáticamente como **hora doble (× 2.00)**.

---

## Días aprobados

El **Resultado** final solo incluye los días que estén aprobados. Un día aprobado significa que **todas** las horas extra de ese día (de ese empleado) cuentan para el pago.

La lista de aprobados puede venir de dos formas:

1. **En el mismo Excel de Jibble** — agrega una hoja cuyo nombre contenga la palabra *Aprobados* (por ejemplo `Aprobados` o `Días aprobados`).
2. **En un archivo aparte** — un `.xlsx` que subes en el segundo recuadro de la aplicación.

En cualquiera de los dos casos, la hoja necesita **dos columnas**:

| Columna | Qué poner |
|---|---|
| **Empleado** | El nombre exactamente como aparece en Jibble (con tildes y mayúsculas) |
| **Fecha** | El día aprobado en formato **AAAA-MM-DD** |

Una fila por cada día aprobado de cada empleado. Si un empleado tiene tres días aprobados, pones tres filas.

> En la aplicación hay un botón **"📄 Descargar plantilla de días aprobados"** que te baja un Excel (hoja `Aprobados`) ya con los nombres de los empleados configurados. Ábrelo, escribe la fecha aprobada (AAAA-MM-DD) en cada fila, agrega una fila por cada día aprobado y borra los empleados que no apruebes.

> Si no cargas ninguna lista de aprobados, tanto la **Auditoría** como el **Resultado** salen vacíos: el programa solo trabaja con los días aprobados.

---

## Calcular las horas extras — paso a paso

### Paso 1 — Exportar el reporte desde Jibble

1. Entra a Jibble
2. Genera el reporte mensual del equipo
3. Expórtalo como **.xlsx** (Excel)
4. Guárdalo en tu computadora

### Paso 2 — Subir los archivos

1. En la aplicación, haz clic en **"Sube el Excel de Jibble"** (o arrastra el archivo)
2. Selecciona el `.xlsx` que exportaste de Jibble
3. Si los días aprobados están en un archivo aparte, súbelo en el segundo recuadro (**"Días aprobados"**). Si ya vienen en una hoja del mismo Excel, no hace falta
4. La aplicación muestra cuántos días aprobados encontró

### Paso 3 — Calcular

1. Haz clic en el botón azul **"Calcular horas extra"**
2. Espera unos segundos

### Paso 4 — Revisar los resultados

Aparecen dos tablas:

**Auditoría (solo días aprobados)** — una fila por cada empleado y fecha **aprobada**, con los datos usados para el cálculo:

| Columna | Qué significa |
|---|---|
| `Entrada` / `Salida` | Hora de reloj registrada (la salida de madrugada sale como AM en la misma fila) |
| `Horas extra` | Total de horas extra del día |
| `H. diurna` | Horas extras diurnas (17:00–21:00) |
| `H. nocturna` | Horas extras nocturnas (21:00–24:00, máximo 3h) |
| `H. doble` | Horas dobles (solo domingos y feriados) |
| `$ Diurna` / `$ Nocturna` / `$ Doble` | Monto a pagar por cada tipo |
| `Total $` | Total a pagar ese día |

**Resultado (solo días aprobados)** — una fila por empleado con los totales del mes, **solo de los días aprobados**. Las horas van en formato decimal (estilo adm cloud): `1.5` = 1 hora 30 minutos, `2.25` = 2 horas 15 minutos, `8.00` = 8 horas. Incluye además, como extra, el monto que se pagaría por hora diurna, nocturna y doble.

### Paso 5 — Exportar

1. Haz clic en **"Descargar Excel"**
2. Se descarga un archivo `reporte_horas_extra.xlsx` con dos pestañas:
   - **Auditoría** — el detalle día por día (todo lo usado para calcular)
   - **Resultado** — los totales por empleado, solo de los días aprobados

---

## Tarifas que aplica la calculadora

Según el Código de Trabajo de la República Dominicana:

| Tipo | Cuándo aplica | Multiplicador |
|---|---|---|
| **Diurna** | Lunes a sábado de 17:00 a 21:00 (máx 4h) | × 1.35 sobre la hora ordinaria |
| **Nocturna** | Lunes a sábado de 21:00 a 24:00 (máx 3h) | × 1.54 sobre la hora ordinaria |
| **Doble** | Domingos y feriados | × 2.00 sobre la hora ordinaria |

> La hora extra clasificable termina a **medianoche**: como máximo 4h diurnas + 3h
> nocturnas = 7h por día. Lo que se trabaje después de las 12AM **no se cuenta**
> automáticamente; revísalo manualmente.

> **Sábados:** el horario de taller es de 8AM a 5PM, igual que entre semana, así que
> las horas extra del sábado son **normales** (diurna/nocturna), **no dobles**. La
> extra cuenta a partir de las 5PM. Como Jibble tiene mal el horario del sábado, esas
> horas se calculan desde la hora de salida registrada, no desde la columna de Jibble.

La hora ordinaria se calcula así:
```
hora_ordinaria = salario_mensual ÷ (4.33 × 44)
```

---

## Preguntas frecuentes

**¿Qué pasa si un empleado aparece con $0.00 aunque tiene horas extras?**
Su `salario_mensual` en el panel lateral está en 0. Complétalo y vuelve a calcular.

**¿Por qué algunos empleados tienen valores muy grandes (15h, 23h)?**
Probablemente olvidaron registrar la salida en Jibble ese día. Esos registros hay que verificarlos manualmente antes de pagar.

**¿Puedo usar el reporte de cualquier mes?**
Sí, siempre que el archivo tenga la pestaña **"Raw Timesheets"** con el formato estándar de Jibble.

**¿Qué hago si el navegador no se abre?**
Abre manualmente tu navegador y escribe en la barra de direcciones: `http://localhost:8501`

**¿Cómo cierro la aplicación?**
Vuelve a la terminal y presiona `Ctrl + C`.
