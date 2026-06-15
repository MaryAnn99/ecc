from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import pandas as pd

NOCTURNA_START = 21.0              # 9:00 PM — nighttime overtime begins
NOCTURNA_END = 7.0                 # 7:00 AM — nighttime overtime ends (next day)

WEEKDAY_WORK_HOURS = 8.0           # ordinary work, excluding break (Mon–Fri)
SATURDAY_WORK_HOURS = 4.0          # ordinary work, excluding break (Saturday, 8AM–12PM)
FREE_BREAK_HOURS = 1.0             # daily free rest; assumed taken even if not reported

# These employees do not work Saturdays, so ANY Saturday hour is paid double.
SATURDAY_ALL_DAY_DOUBLE = {"Ashley Fernandez", "Keylin Rivas", "Libeth Valerio"}

DIURNA_MULTIPLIER = 1.35
NOCTURNA_MULTIPLIER = 1.54
DOBLE_MULTIPLIER = 2.00


@dataclass
class OvertimeBreakdown:
    diurna_hours: float = 0.0
    nocturna_hours: float = 0.0
    doble_hours: float = 0.0

    diurna_amount: float = 0.0
    nocturna_amount: float = 0.0
    doble_amount: float = 0.0

    reported_break: float = 0.0

    incomplete: bool = False

    @property
    def total_hours(self) -> float:
        return self.diurna_hours + self.nocturna_hours + self.doble_hours

    @property
    def total_amount(self) -> float:
        return self.diurna_amount + self.nocturna_amount + self.doble_amount


def load_rates(path: str | Path = "rates.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # Normalize keys: strip whitespace so they match cleaned employee names from Jibble
    return {k.strip(): v for k, v in raw.items() if not k.startswith("_")}


def load_holidays(path: str | Path = "holidays.json") -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_date(value) -> str:
    """Normalize any date-ish cell to 'YYYY-MM-DD' (empty string if missing)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()[:10]


def _find_col(columns: list[str], candidates: list[str]) -> Optional[str]:
    """Find the first column whose lowercased name contains any candidate keyword."""
    for col in columns:
        low = str(col).lower().strip()
        if any(c in low for c in candidates):
            return col
    return None


def load_approved_days(df: Optional[pd.DataFrame]) -> set[tuple[str, str]]:
    """
    Build the set of approved (empleado, 'YYYY-MM-DD') pairs from an approvals sheet.

    The sheet needs one column with the employee name and one with the approved
    date. Column names are matched loosely (e.g. 'Empleado'/'Nombre',
    'Fecha'/'Día'). A day present in this set means ALL of that day's overtime is
    approved for that employee.
    """
    if df is None or df.empty:
        return set()

    columns = list(df.columns)
    emp_col = _find_col(columns, ["empleado", "nombre", "colaborador"])
    date_col = _find_col(columns, ["fecha", "día", "dia"])
    if emp_col is None or date_col is None:
        return set()

    approved: set[tuple[str, str]] = set()
    for _, row in df.iterrows():
        emp = str(row.get(emp_col, "")).strip()
        fecha = _normalize_date(row.get(date_col))
        if emp and fecha:
            approved.add((emp, fecha))
    return approved


def parse_time(value) -> Optional[time]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    text = str(value).strip()
    if not text or text.lower() in ("nan", "nat", "none", ""):
        return None
    parts = text.split(":")
    if len(parts) >= 2:
        try:
            hour = int(parts[0]) % 24
            minute = int(parts[1])
            return time(hour, minute)
        except ValueError:
            return None
    return None


def parse_hours(value) -> float:
    """Parse hours from Jibble's 'Xh Ym' format or a plain decimal number."""
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    import re
    m = re.fullmatch(r"(\d+)h\s*(\d+)m", text)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    try:
        return float(text.replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _presence_hours(first_entry: Optional[time], last_exit: Optional[time]) -> float:
    """
    Clock presence in decimal hours, handling shifts that cross midnight.

    If the exit is at or before the entry, the shift ran into the next day, so 24h
    is added. Returns 0 if either time is missing.
    """
    if first_entry is None or last_exit is None:
        return 0.0
    entry_h = first_entry.hour + first_entry.minute / 60.0
    exit_h = last_exit.hour + last_exit.minute / 60.0
    if exit_h <= entry_h:
        exit_h += 24.0
    return exit_h - entry_h


def _split_diurna_nocturna(start_h: float, end_h: float) -> tuple[float, float]:
    """
    Split the overtime window [start_h, end_h] (absolute decimal hours, may cross
    midnight) into daytime and nighttime hours by actual clock time.

    Nighttime is 21:00–07:00, modeled as the repeating intervals [21+24k, 31+24k).
    Daytime (07:00–21:00) is everything else. Neither side has a cap.
    """
    if end_h <= start_h:
        return 0.0, 0.0

    nocturna = 0.0
    k = int((start_h - NOCTURNA_END) // 24) - 1
    while NOCTURNA_START + 24 * k < end_h:
        lo = NOCTURNA_START + 24 * k          # 21:00 of day k
        hi = NOCTURNA_END + 24 + 24 * k       # 07:00 of day k+1
        nocturna += max(0.0, min(end_h, hi) - max(start_h, lo))
        k += 1
    diurna = (end_h - start_h) - nocturna
    return diurna, nocturna


def _reported_break_hours(row: pd.Series) -> float:
    """Total break time reported for the day (paid + unpaid), in decimal hours.

    Jibble aggregates all of a day's breaks into these two totals, so we never need
    to walk the per-break 'Descanso 1', 'Descanso 2'… columns.
    """
    return (
        parse_hours(row.get("Horas de descanso (remunerado)", 0))
        + parse_hours(row.get("Horas de descanso (no remunerado)", 0))
    )


def classify_weekday_hours(
    first_entry: Optional[time],
    last_exit: Optional[time],
    reported_break: float = 0.0,
    work_hours: float = WEEKDAY_WORK_HOURS,
) -> tuple[float, float]:
    """
    Returns (diurna_hours, nocturna_hours) for a Mon–Fri day, computed from clock.

    Overtime is presence beyond the ordinary workday (8h work) plus the effective
    break. The free rest is 1h; if more break is reported, the excess must be "repaid"
    by working later, so it does NOT count as overtime — it delays when overtime starts:
        effective_break = max(reported_break, 1h)
        overtime window = [entry + 8h + effective_break, exit]
    Each hour of that window is classified by real clock time:
    - daytime (07:00–21:00) → diurna (no cap)
    - night (21:00–07:00)   → nocturna

    For an 8AM entry with the free 1h break the window starts at 17:00 (classic split).
    An earlier entry pushes overtime before 17:00, where those hours still count diurna.
    """
    presence = _presence_hours(first_entry, last_exit)
    effective_break = max(reported_break, FREE_BREAK_HOURS)
    ot_hours = presence - work_hours - effective_break
    if ot_hours <= 0:
        return 0.0, 0.0

    entry_h = first_entry.hour + first_entry.minute / 60.0
    ot_start = entry_h + work_hours + effective_break
    ot_end = ot_start + ot_hours
    return _split_diurna_nocturna(ot_start, ot_end)


def _is_incomplete_record(first_entry: Optional[time], last_exit: Optional[time]) -> bool:
    return (first_entry is None) != (last_exit is None)


def _has_any_reported_extras(row: pd.Series) -> bool:
    return (
        parse_hours(row.get("Horas extras diarias", 0)) > 0
        or parse_hours(row.get("Horas extras en día de descanso", 0)) > 0
        or parse_hours(row.get("Horas extras en festivo", 0)) > 0
    )


def _hourly_rates(salario_mensual: float) -> tuple[float, float, float]:
    hora_ordinaria = salario_mensual / (4.33 * 44)
    return (
        hora_ordinaria * DIURNA_MULTIPLIER,
        hora_ordinaria * NOCTURNA_MULTIPLIER,
        hora_ordinaria * DOBLE_MULTIPLIER,
    )


def compute_overtime(
    row: pd.Series,
    rates: dict,
    holidays: list[str],
) -> OvertimeBreakdown:
    breakdown = OvertimeBreakdown()

    employee = str(row.get("Nombre y apellidos", "")).strip()
    if employee not in rates:
        return breakdown

    r_diurna, r_nocturna, r_doble = _hourly_rates(rates[employee]["salario_mensual"])

    fecha_str = str(row.get("Fecha", ""))[:10]
    is_holiday = fecha_str in holidays

    day_name = str(row.get("Día", "")).lower()
    is_sunday = "domingo" in day_name
    is_saturday = "sábado" in day_name or "sabado" in day_name

    first_entry = parse_time(row.get("Primera entrada"))
    last_exit = parse_time(row.get("Última salida"))
    reported_break = _reported_break_hours(row)
    breakdown.reported_break = reported_break

    if _is_incomplete_record(first_entry, last_exit):
        breakdown.incomplete = True
        return breakdown

    if first_entry is None and last_exit is None and _has_any_reported_extras(row):
        breakdown.incomplete = True
        return breakdown

    if is_holiday:
        hours = parse_hours(row.get("Horas extras en festivo", 0))
        breakdown.doble_hours = hours
        breakdown.doble_amount = hours * r_doble

    elif is_sunday:
        hours = parse_hours(row.get("Horas extras en día de descanso", 0))
        breakdown.doble_hours = hours
        breakdown.doble_amount = hours * r_doble

    elif is_saturday:
        # Saturday schedule is 8AM–12PM (4h work + 1h break). Overtime past those
        # worked hours is paid DOUBLE. Ashley, Keylin and Libeth do not work
        # Saturdays, so ANY hour they actually work is double (no schedule, no free
        # break assumed — only their reported break is subtracted). Computed from
        # clock time because Jibble's Saturday daily-OT column is unreliable.
        presence = _presence_hours(first_entry, last_exit)
        if employee in SATURDAY_ALL_DAY_DOUBLE:
            hours = max(0.0, presence - reported_break)
        else:
            effective_break = max(reported_break, FREE_BREAK_HOURS)
            hours = max(0.0, presence - SATURDAY_WORK_HOURS - effective_break)
        breakdown.doble_hours = hours
        breakdown.doble_amount = hours * r_doble

    else:
        # Mon–Fri: overtime is presence beyond 8h work + the effective break (free 1h
        # or more if reported), classified diurna/nocturna by clock time. Jibble's
        # daily-OT column is not used.
        diurna_h, nocturna_h = classify_weekday_hours(first_entry, last_exit, reported_break)
        breakdown.diurna_hours = diurna_h
        breakdown.nocturna_hours = nocturna_h
        breakdown.diurna_amount = diurna_h * r_diurna
        breakdown.nocturna_amount = nocturna_h * r_nocturna

    return breakdown


def _fmt_time(value) -> str:
    t = parse_time(value)
    return f"{t.hour:02d}:{t.minute:02d}" if t is not None else ""


def process_timesheet(
    df: pd.DataFrame,
    rates: dict,
    holidays: list[str],
    approved_days: Optional[set[tuple[str, str]]] = None,
) -> pd.DataFrame:
    approved_days = approved_days or set()
    rows = []
    for _, row in df.iterrows():
        b = compute_overtime(row, rates, holidays)
        employee = str(row.get("Nombre y apellidos", "")).strip()
        fecha = str(row.get("Fecha", ""))[:10]
        rows.append(
            {
                "Empleado": employee,
                "Fecha": fecha,
                "Día": row.get("Día", ""),
                "Entrada": _fmt_time(row.get("Primera entrada")),
                "Salida": _fmt_time(row.get("Última salida")),
                "Descanso": round(b.reported_break, 2),
                "h_extras": round(b.total_hours, 2),
                "h_diurna": round(b.diurna_hours, 2),
                "h_nocturna": round(b.nocturna_hours, 2),
                "h_doble": round(b.doble_hours, 2),
                "$ diurna": round(b.diurna_amount, 2),
                "$ nocturna": round(b.nocturna_amount, 2),
                "$ doble": round(b.doble_amount, 2),
                "Total": round(b.total_amount, 2),
                "Aprobado": (employee, fecha) in approved_days,
                "Incompleto": b.incomplete,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["Empleado", "Fecha"])
        .reset_index(drop=True)
    )


def summarize(detail_df: pd.DataFrame) -> pd.DataFrame:
    """Per-employee totals of APPROVED overtime only (in decimal hours)."""
    approved = (
        detail_df[detail_df["Aprobado"]] if "Aprobado" in detail_df.columns else detail_df
    )
    if approved.empty:
        return pd.DataFrame(
            columns=[
                "Empleado",
                "Total_h_diurna",
                "Total_h_nocturna",
                "Total_h_doble",
                "Total_$_diurna",
                "Total_$_nocturna",
                "Total_$_doble",
                "Total_a_pagar",
            ]
        )
    return (
        approved.groupby("Empleado")
        .agg(
            Total_h_diurna=("h_diurna", "sum"),
            Total_h_nocturna=("h_nocturna", "sum"),
            Total_h_doble=("h_doble", "sum"),
            Total_dollar_diurna=("$ diurna", "sum"),
            Total_dollar_nocturna=("$ nocturna", "sum"),
            Total_dollar_doble=("$ doble", "sum"),
            Total_a_pagar=("Total", "sum"),
        )
        .round(2)
        .reset_index()
        .rename(
            columns={
                "Total_dollar_diurna": "Total_$_diurna",
                "Total_dollar_nocturna": "Total_$_nocturna",
                "Total_dollar_doble": "Total_$_doble",
            }
        )
    )
