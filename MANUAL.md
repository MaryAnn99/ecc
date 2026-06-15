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

En la parte izquierda de la pantalla (el panel lateral), bajo **"Sueldos de empleados"**, hay una **tabla** con tres columnas: *Empleado*, *Salario mensual* y *Tarifa por hora*.

Cada empleado se carga de **una de dos formas**:

- **Salario mensual** — para el personal con sueldo fijo. La calculadora obtiene la hora ordinaria dividiendo el salario (ver fórmula más abajo).
- **Tarifa por hora** — para el personal de taller que cobra por hora. Aquí pones directamente cuánto vale su hora ordinaria.

> **Si llenas las dos columnas, manda la *Tarifa por hora*.** El salario mensual se ignora en ese caso.

Para editar:
1. Haz clic en la celda del empleado (**Salario mensual** *o* **Tarifa por hora**) y escribe el valor
2. Para **agregar** a alguien nuevo, escribe su nombre y su salario o tarifa en la **fila vacía del final**
3. Para **quitar** a alguien, selecciona su fila (casilla a la izquierda) y presiona la papelera / tecla suprimir
4. Haz clic en **"💾 Guardar tarifas"** (debajo de la tabla) para que los cambios queden guardados

> **Importante:** el nombre del empleado tiene que ser exactamente igual a como aparece en Jibble, incluyendo tildes y mayúsculas. Si no coincide, el empleado no aparece en el cálculo (y no sale ningún error).

> **Botón "Guardar tarifas":** los cambios que hagas en la tabla sirven para el cálculo del momento, pero **se pierden al recargar** si no tocas este botón. Al guardarlo, las altas y cambios quedan escritos en el archivo `rates.json` y siguen ahí la próxima vez que abras la aplicación.

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
| `Descanso` | Horas de descanso reportadas ese día (suma de remunerado + no remunerado) |
| `Horas extra` | Total de horas extra del día |
| `H. diurna` | Horas extras diurnas (horario de día, hasta las 21:00) |
| `H. nocturna` | Horas extras nocturnas (21:00–07:00) |
| `H. doble` | Horas dobles (domingos, feriados y sábados) |
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
| **Diurna** | Lunes a viernes, horario de día hasta las 21:00 (normalmente desde las 17:00) | × 1.35 sobre la hora ordinaria |
| **Nocturna** | Lunes a viernes de 21:00 a 07:00 | × 1.55 sobre la hora ordinaria |
| **Doble** | Domingos, feriados y sábados | × 2.00 sobre la hora ordinaria |

> **Lunes a viernes:** la jornada es de 8h de trabajo + 1h de almuerzo libre. La hora
> extra se calcula desde el reloj (primera entrada / última salida), no desde la
> columna de Jibble. Cada hora extra se clasifica según la hora real del reloj: de día
> (hasta las 21:00) es **diurna**, de 21:00 a 07:00 es **nocturna**. Quien entra antes
> de las 8AM puede acumular más de 4h diurnas. Lo trabajado después de las 07:00 **no
> se cuenta** automáticamente; revísalo manualmente.

> **Descansos:** el descanso libre es de **1h por día**. Si la persona reporta **más**
> de 1h de descanso, el exceso **no se paga como extra** — esas horas reponen el
> descanso tomado de más. Si reporta **menos** de 1h (o nada), se asume igual que tomó
> su hora libre completa. El cálculo lee las columnas `Horas de descanso (remunerado)`
> y `Horas de descanso (no remunerado)` de Jibble (la suma de ambas). Ejemplo: si
> alguien toma 2h de descanso y se queda 1h de más, esa hora extra **no se le paga**.

> **Sábados:** el horario es de **8AM a 12PM** (4h de trabajo + 1h de descanso libre).
> La hora extra del sábado (lo trabajado por encima de esas horas) se paga **doble**,
> no diurna/nocturna. Se calcula desde el reloj y descontando los descansos igual que
> entre semana. **Ashley, Keylin y Libeth no trabajan los sábados**, así que cualquier
> hora que **trabajen** un sábado se paga doble (se descuenta solo su descanso real,
> sin asumir la hora libre).

La hora ordinaria depende de cómo cargaste al empleado:

- Si tiene **tarifa por hora**, esa **es** la hora ordinaria (se usa tal cual).
- Si tiene **salario mensual**, se calcula así:
  ```
  hora_ordinaria = salario_mensual ÷ (4.33 × 44)
  ```
  (4.33 semanas por mes × 44 horas por semana = 190.52 horas al mes.)

---

## Preguntas frecuentes

**¿Qué pasa si un empleado aparece con $0.00 aunque tiene horas extras?**
No tiene cargado ni salario mensual ni tarifa por hora (ambos en 0) en el panel lateral. Completa uno de los dos, toca **"Guardar tarifas"** y vuelve a calcular.

**¿Cuándo uso "Tarifa por hora" en vez de "Salario mensual"?**
Usa **tarifa por hora** para el personal de taller que cobra por hora; pones directamente el valor de su hora. Usa **salario mensual** para el personal con sueldo fijo. Si llenas ambas, manda la tarifa por hora.

**Agregué a alguien y al recargar desapareció. ¿Por qué?**
No tocaste **"💾 Guardar tarifas"**. Los cambios en la tabla solo quedan guardados al presionar ese botón.

**¿Por qué algunos empleados tienen valores muy grandes (15h, 23h)?**
Probablemente olvidaron registrar la salida en Jibble ese día. Esos registros hay que verificarlos manualmente antes de pagar.

**¿Puedo usar el reporte de cualquier mes?**
Sí, siempre que el archivo tenga la pestaña **"Raw Timesheets"** con el formato estándar de Jibble.

**¿Qué hago si el navegador no se abre?**
Abre manualmente tu navegador y escribe en la barra de direcciones: `http://localhost:8501`

**¿Cómo cierro la aplicación?**
Vuelve a la terminal y presiona `Ctrl + C`.
