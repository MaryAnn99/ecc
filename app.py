from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from calculator import (
    load_approved_days,
    load_holidays,
    load_rates,
    process_timesheet,
    summarize,
)

st.set_page_config(page_title="Calculadora de Horas Extra ECC", layout="wide")
st.title("Calculadora de Horas Extra ECC")

# Nombres internos → encabezados en español para lo que se muestra y se descarga.
AUDIT_COLUMNS = {
    "Empleado": "Empleado",
    "Fecha": "Fecha",
    "Día": "Día",
    "Entrada": "Entrada",
    "Salida": "Salida",
    "Descanso": "Descanso",
    "h_extras": "Horas extra",
    "h_diurna": "H. diurna",
    "h_nocturna": "H. nocturna",
    "h_doble": "H. doble",
    "$ diurna": "$ Diurna",
    "$ nocturna": "$ Nocturna",
    "$ doble": "$ Doble",
    "Total": "Total $",
    "Aprobado": "Aprobado",
    "Incompleto": "Incompleto",
}

RESULT_COLUMNS = {
    "Empleado": "Empleado",
    "Total_h_diurna": "Horas diurnas",
    "Total_h_nocturna": "Horas nocturnas",
    "Total_h_doble": "Horas dobles",
    "Total_$_diurna": "$ Diurna",
    "Total_$_nocturna": "$ Nocturna",
    "Total_$_doble": "$ Doble",
    "Total_a_pagar": "Total a pagar",
}


def _to_spanish(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename columns to Spanish headers and show booleans as Sí/No."""
    out = df.copy()
    for col in ("Aprobado", "Incompleto"):
        if col in out.columns:
            out[col] = out[col].map({True: "Sí", False: "No"})
    return out.rename(columns=mapping)


def _autofit_columns(ws, df: pd.DataFrame) -> None:
    """Widen each column to fit its header and values, so the .xlsx opens readable."""
    from openpyxl.utils import get_column_letter

    for idx, col in enumerate(df.columns, start=1):
        header_len = len(str(col))
        values = df[col].astype(str)
        body_len = int(values.map(len).max()) if not values.empty else 0
        width = min(max(header_len, body_len) + 2, 40)
        ws.column_dimensions[get_column_letter(idx)].width = width


def build_approvals_template(employees: list[str]) -> bytes:
    """Excel template (hoja 'Aprobados') with the configured employees, blank dates."""
    df = pd.DataFrame({"Empleado": sorted(employees), "Fecha": [""] * len(employees)})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Aprobados", index=False)
        ws = writer.sheets["Aprobados"]
        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 16
    buf.seek(0)
    return buf.getvalue()


# ── Barra lateral: sueldos de los empleados ───────────────────────────────────
st.sidebar.header("Sueldos de empleados")
st.sidebar.caption(
    "Cada empleado puede cargar **salario mensual** o **tarifa por hora**. Si pones "
    "tarifa por hora, esa manda (útil para personal de taller); si no, la hora se "
    "calcula a partir del salario. Para agregar a alguien nuevo usa la fila vacía del "
    "final; para quitarlo, selecciona la fila y bórrala. El nombre debe coincidir "
    "exactamente con el de Jibble. Toca **Guardar tarifas** para que los cambios "
    "queden guardados."
)

rates_path = Path("rates.json")
default_rates = load_rates(rates_path) if rates_path.exists() else {}

rates_df = pd.DataFrame(
    [
        {
            "Empleado": name,
            "Salario mensual": data.get("salario_mensual", 0),
            "Tarifa por hora": data.get("tarifa_hora", 0),
        }
        for name, data in default_rates.items()
    ],
    columns=["Empleado", "Salario mensual", "Tarifa por hora"],
)

edited_rates = st.sidebar.data_editor(
    rates_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Empleado": st.column_config.TextColumn("Empleado", required=True),
        "Salario mensual": st.column_config.NumberColumn(
            "Salario mensual", min_value=0, step=100, format="%.2f"
        ),
        "Tarifa por hora": st.column_config.NumberColumn(
            "Tarifa por hora", min_value=0, step=10, format="%.2f"
        ),
    },
    key="rates_editor",
)

rates = {}
for _, row in edited_rates.iterrows():
    name = str(row["Empleado"]).strip()
    if not name or name.lower() == "nan":
        continue
    entry: dict[str, float] = {}
    salary = row["Salario mensual"]
    tarifa = row["Tarifa por hora"]
    if not pd.isna(salary) and float(salary) > 0:
        entry["salario_mensual"] = float(salary)
    if not pd.isna(tarifa) and float(tarifa) > 0:
        entry["tarifa_hora"] = float(tarifa)
    rates[name] = entry

if st.sidebar.button("💾 Guardar tarifas"):
    note = ""
    if rates_path.exists():
        with open(rates_path, "r", encoding="utf-8") as f:
            note = json.load(f).get("_note", "")
    payload = {"_note": note, **rates} if note else dict(rates)
    with open(rates_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    st.sidebar.success("Tarifas guardadas en rates.json")

# ── Barra lateral: feriados ───────────────────────────────────────────────────
st.sidebar.header("Feriados")
holidays_path = Path("holidays.json")
default_holidays: list[str] = load_holidays(holidays_path) if holidays_path.exists() else []

holidays_input = st.sidebar.text_area(
    "Feriados — una fecha por línea (AAAA-MM-DD)",
    value="\n".join(default_holidays),
    height=150,
)
holidays = [d.strip() for d in holidays_input.splitlines() if d.strip()]

# ── Principal: carga de archivos y cálculo ────────────────────────────────────
uploaded = st.file_uploader("Sube el Excel de Jibble (.xlsx)", type=["xlsx"])

st.markdown(
    "Los **días aprobados** pueden venir en una hoja llamada *Aprobados* dentro "
    "del mismo Excel de Jibble, o en un archivo aparte. Debe tener una columna "
    "con el **nombre del empleado** y otra con la **fecha** aprobada (AAAA-MM-DD)."
)
st.download_button(
    label="📄 Descargar plantilla de días aprobados",
    data=build_approvals_template(list(rates.keys())),
    file_name="plantilla_dias_aprobados.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Plantilla con los empleados configurados. Llená la fecha aprobada (AAAA-MM-DD), "
         "una fila por cada día aprobado, y borrá los que no uses.",
)
approvals_file = st.file_uploader(
    "Días aprobados (Excel aparte) — opcional si ya vienen en el archivo principal",
    type=["xlsx"],
    key="approvals",
)

if not uploaded:
    st.info("Sube el reporte mensual de Jibble para empezar.")
    st.stop()

try:
    workbook = pd.ExcelFile(uploaded)
    df_raw = pd.read_excel(workbook, sheet_name="Raw Timesheets", header=1)
except Exception as exc:
    st.error(f"No se pudo leer la pestaña 'Raw Timesheets': {exc}")
    st.stop()

# ── Resolver los días aprobados ───────────────────────────────────────────────
df_approvals = None
approvals_source = ""

if approvals_file is not None:
    try:
        df_approvals = pd.read_excel(approvals_file)
        approvals_source = "archivo aparte"
    except Exception as exc:
        st.error(f"No se pudo leer el archivo de días aprobados: {exc}")
        st.stop()
else:
    approval_sheet = next(
        (s for s in workbook.sheet_names if "aprob" in s.lower()), None
    )
    if approval_sheet is not None:
        df_approvals = pd.read_excel(workbook, sheet_name=approval_sheet)
        approvals_source = f"hoja '{approval_sheet}' del archivo principal"

approved_days = load_approved_days(df_approvals)

if approved_days:
    st.success(
        f"{len(approved_days)} día(s) aprobado(s) cargado(s) desde {approvals_source}."
    )
else:
    st.warning(
        "No se encontraron días aprobados. La auditoría se calcula igual, pero la "
        "hoja **Resultado** saldrá vacía hasta que cargues las aprobaciones."
    )

if st.button("Calcular horas extra", type="primary"):
    if not rates:
        st.error("No hay sueldos configurados. Agrega al menos uno en el panel lateral.")
        st.stop()

    detail = process_timesheet(df_raw, rates, holidays, approved_days)
    summary = summarize(detail)

    # La auditoría solo muestra los días aprobados (los datos que se usaron para
    # el resultado). La columna "Aprobado" sería redundante aquí, así que se quita.
    audit = (
        detail[detail["Aprobado"]]
        .drop(columns=["Aprobado"])
        .reset_index(drop=True)
    )

    incomplete_rows = audit[audit["Incompleto"]]
    if not incomplete_rows.empty:
        st.warning(
            f"{len(incomplete_rows)} día(s) aprobado(s) con entrada o salida faltante — "
            "esas horas extra no se contaron. Revísalos manualmente."
        )
        st.dataframe(
            incomplete_rows[["Empleado", "Fecha", "Día", "Entrada", "Salida"]].rename(
            columns=AUDIT_COLUMNS
        ),
            use_container_width=True,
        )

    st.subheader("Auditoría (solo días aprobados)")
    st.dataframe(_to_spanish(audit, AUDIT_COLUMNS), use_container_width=True)

    st.subheader("Resultado (solo días aprobados)")
    if summary.empty:
        st.info("Sin días aprobados todavía — no hay resultado que mostrar.")
    st.dataframe(_to_spanish(summary, RESULT_COLUMNS), use_container_width=True)

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        audit_es = _to_spanish(audit, AUDIT_COLUMNS)
        summary_es = _to_spanish(summary, RESULT_COLUMNS)
        audit_es.to_excel(writer, sheet_name="Auditoría", index=False)
        summary_es.to_excel(writer, sheet_name="Resultado", index=False)
        _autofit_columns(writer.sheets["Auditoría"], audit_es)
        _autofit_columns(writer.sheets["Resultado"], summary_es)
    buf.seek(0)

    st.download_button(
        label="Descargar Excel",
        data=buf,
        file_name="reporte_horas_extra.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
