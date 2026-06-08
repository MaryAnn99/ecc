from datetime import time

import pandas as pd
import pytest

from calculator import (
    OvertimeBreakdown,
    classify_weekday_hours,
    compute_overtime,
    load_approved_days,
    parse_hours,
    parse_time,
    process_timesheet,
    summarize,
)


class TestClassifyWeekdayHours:
    def test_all_within_diurna_window(self):
        diurna, nocturna = classify_weekday_hours(2.0, time(19, 0))
        assert diurna == pytest.approx(2.0)
        assert nocturna == pytest.approx(0.0)

    def test_exit_at_diurna_boundary(self):
        # Exactly 4h extra, exits exactly at 21:00 — all diurna
        diurna, nocturna = classify_weekday_hours(4.0, time(21, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(0.0)

    def test_split_diurna_and_nocturna(self):
        # 5h extra, exits at 22:00 → 4 diurna + 1 nocturna
        diurna, nocturna = classify_weekday_hours(5.0, time(22, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(1.0)

    def test_small_hours_late_exit_still_diurna_first(self):
        # 2h extra but exits at 22:00 → hours fill forward from 17:00, so all diurna
        diurna, nocturna = classify_weekday_hours(2.0, time(22, 0))
        assert diurna == pytest.approx(2.0)
        assert nocturna == pytest.approx(0.0)

    def test_pure_nocturna_not_possible_with_forward_fill(self):
        # 1h extra, exits at 22:00 → fills from 17:00, so diurna
        diurna, nocturna = classify_weekday_hours(1.0, time(22, 0))
        assert diurna == pytest.approx(1.0)
        assert nocturna == pytest.approx(0.0)

    def test_only_nocturna_hours_when_full_diurna_used(self):
        # 6h extra, exits at 23:00 → 4 diurna + 2 nocturna
        diurna, nocturna = classify_weekday_hours(6.0, time(23, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(2.0)

    def test_zero_hours_returns_zero(self):
        diurna, nocturna = classify_weekday_hours(0.0, time(21, 0))
        assert diurna == 0.0
        assert nocturna == 0.0

    def test_negative_hours_returns_zero(self):
        diurna, nocturna = classify_weekday_hours(-1.0, time(21, 0))
        assert diurna == 0.0
        assert nocturna == 0.0

    def test_nocturna_capped_at_midnight(self):
        # 8h extra, exits at 01:00 → nocturna caps at midnight (3h), the hour past
        # midnight is NOT counted: 4 diurna + 3 nocturna (total 7, not 8)
        diurna, nocturna = classify_weekday_hours(8.0, time(1, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(3.0)

    def test_nocturna_never_exceeds_three_hours(self):
        # Even a huge extra with a very late exit can't push nocturna past 3h
        diurna, nocturna = classify_weekday_hours(12.0, time(4, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(3.0)

    def test_exit_exactly_midnight(self):
        # 7h extra, exits at 00:00 → 4 diurna + 3 nocturna (full window)
        diurna, nocturna = classify_weekday_hours(7.0, time(0, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(3.0)

    def test_fractional_hours(self):
        # 4.5h extra, exits at 21:30 → 4 diurna + 0.5 nocturna
        diurna, nocturna = classify_weekday_hours(4.5, time(21, 30))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(0.5)


class TestSaturdayNormalOvertime:
    """Saturday is a normal workday (8am-5pm workshop schedule), same as L-V.

    Overtime starts at 17:00 and is classified diurna/nocturna — NEVER double.
    Jibble has the Saturday schedule wrong, so overtime is computed from clock
    times (work after 17:00), not from Jibble's daily-OT column.
    """

    RATES = {"Ana García": {"salario_mensual": 30000.0}}
    HOLIDAYS: list = []

    def _row(self, salida, extras=99.0):
        # extras is intentionally large/wrong: Saturday must IGNORE Jibble's column.
        return pd.Series({
            "Nombre y apellidos": "Ana García",
            "Fecha": "2026-03-14",
            "Día": "Sábado",
            "Primera entrada": "08:00",
            "Última salida": salida,
            "Horas extras diarias": extras,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        })

    def test_exit_at_5pm_no_overtime(self):
        b = compute_overtime(self._row("17:00"), self.RATES, self.HOLIDAYS)
        assert b.total_hours == pytest.approx(0.0)

    def test_exit_8pm_all_diurna_not_double(self):
        b = compute_overtime(self._row("20:00"), self.RATES, self.HOLIDAYS)
        assert b.diurna_hours == pytest.approx(3.0)
        assert b.nocturna_hours == pytest.approx(0.0)
        assert b.doble_hours == pytest.approx(0.0)
        assert b.diurna_amount == pytest.approx(b.diurna_hours * 30000.0 / (4.33 * 44) * 1.35)
        assert b.doble_amount == pytest.approx(0.0)

    def test_exit_10pm_splits_diurna_and_nocturna(self):
        b = compute_overtime(self._row("22:00"), self.RATES, self.HOLIDAYS)
        assert b.diurna_hours == pytest.approx(4.0)
        assert b.nocturna_hours == pytest.approx(1.0)
        assert b.doble_hours == pytest.approx(0.0)

    def test_exit_past_midnight_caps_nocturna(self):
        # 8am→01:00: nocturna caps at midnight → 4 diurna + 3 nocturna, doble 0
        b = compute_overtime(self._row("01:00"), self.RATES, self.HOLIDAYS)
        assert b.diurna_hours == pytest.approx(4.0)
        assert b.nocturna_hours == pytest.approx(3.0)
        assert b.doble_hours == pytest.approx(0.0)

    def test_ignores_jibble_daily_overtime_column(self):
        # Jibble reports 99h (wrong Saturday schedule); we must use clock time only.
        b = compute_overtime(self._row("19:00", extras=99.0), self.RATES, self.HOLIDAYS)
        assert b.total_hours == pytest.approx(2.0)


class TestParseTime:
    def test_string_hhmm(self):
        assert parse_time("14:30") == time(14, 30)

    def test_string_hh_mm_ss(self):
        assert parse_time("09:15:00") == time(9, 15)

    def test_none_returns_none(self):
        assert parse_time(None) is None

    def test_nan_returns_none(self):
        import math
        assert parse_time(float("nan")) is None

    def test_time_object_passthrough(self):
        t = time(10, 0)
        assert parse_time(t) == t

    def test_empty_string_returns_none(self):
        assert parse_time("") is None


class TestParseHours:
    def test_float_string(self):
        assert parse_hours("1.5") == pytest.approx(1.5)

    def test_comma_decimal(self):
        assert parse_hours("1,5") == pytest.approx(1.5)

    def test_integer(self):
        assert parse_hours(2) == pytest.approx(2.0)

    def test_none_returns_zero(self):
        assert parse_hours(None) == 0.0

    def test_nan_returns_zero(self):
        assert parse_hours(float("nan")) == 0.0

    def test_zero_string(self):
        assert parse_hours("0") == 0.0

    # Jibble "Xh Ym" format
    def test_jibble_format_zero(self):
        assert parse_hours("0h 00m") == pytest.approx(0.0)

    def test_jibble_format_minutes_only(self):
        assert parse_hours("0h 33m") == pytest.approx(33 / 60)

    def test_jibble_format_hours_and_minutes(self):
        assert parse_hours("1h 05m") == pytest.approx(1 + 5 / 60)

    def test_jibble_format_large(self):
        assert parse_hours("7h 39m") == pytest.approx(7 + 39 / 60)

    def test_nat_returns_zero(self):
        assert parse_hours(pd.NaT) == 0.0


class TestComputeOvertimeIncompleteRecords:
    RATES = {"Ana García": {"salario_mensual": 30000.0}}
    HOLIDAYS = ["2026-04-03"]

    def _row(self, **overrides):
        defaults = {
            "Nombre y apellidos": "Ana García",
            "Fecha": "2026-03-10",
            "Día": "Martes",
            "Primera entrada": "08:00",
            "Última salida": "18:30",
            "Horas extras diarias": 1.5,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_weekday_missing_exit_is_incomplete(self):
        row = self._row(**{"Última salida": None, "Horas extras diarias": 2.0})
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_weekday_missing_entry_is_incomplete(self):
        row = self._row(**{"Primera entrada": None, "Horas extras diarias": 2.0})
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_saturday_missing_exit_is_incomplete(self):
        row = self._row(**{
            "Fecha": "2026-03-14",
            "Día": "Sábado",
            "Última salida": None,
            "Horas extras diarias": 0.0,
        })
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_sunday_missing_exit_is_incomplete(self):
        row = self._row(**{
            "Fecha": "2026-03-15",
            "Día": "Domingo",
            "Última salida": None,
            "Horas extras diarias": 0.0,
            "Horas extras en día de descanso": 3.0,
        })
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_holiday_missing_exit_is_incomplete(self):
        row = self._row(**{
            "Fecha": "2026-04-03",
            "Día": "Viernes",
            "Última salida": None,
            "Horas extras diarias": 0.0,
            "Horas extras en festivo": 4.0,
        })
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_complete_record_is_not_incomplete(self):
        row = self._row()
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is False
        assert b.total_hours > 0.0

    def test_both_times_missing_no_extras_is_not_incomplete(self):
        row = self._row(**{"Primera entrada": None, "Última salida": None, "Horas extras diarias": 0.0})
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is False

    def test_both_times_missing_with_weekday_extras_is_incomplete(self):
        # Jibble carry-over from previous day's missed clock-out
        row = self._row(**{"Primera entrada": None, "Última salida": None, "Horas extras diarias": 2.0})
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_both_times_missing_with_sunday_extras_is_incomplete(self):
        row = self._row(**{
            "Fecha": "2026-03-15",
            "Día": "Domingo",
            "Primera entrada": None,
            "Última salida": None,
            "Horas extras diarias": 0.0,
            "Horas extras en día de descanso": 3.0,
        })
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)

    def test_both_times_missing_with_holiday_extras_is_incomplete(self):
        row = self._row(**{
            "Fecha": "2026-04-03",
            "Día": "Viernes",
            "Primera entrada": None,
            "Última salida": None,
            "Horas extras diarias": 0.0,
            "Horas extras en festivo": 4.0,
        })
        b = compute_overtime(row, self.RATES, self.HOLIDAYS)
        assert b.incomplete is True
        assert b.total_hours == pytest.approx(0.0)


class TestProcessTimesheetIncompleteColumn:
    RATES = {"Ana García": {"salario_mensual": 30000.0}}
    HOLIDAYS: list = []

    def test_incomplete_column_present_and_true(self):
        df = pd.DataFrame([{
            "Nombre y apellidos": "Ana García",
            "Fecha": "2026-03-10",
            "Día": "Martes",
            "Primera entrada": "08:00",
            "Última salida": None,
            "Horas extras diarias": 2.0,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        }])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert "Incompleto" in result.columns
        assert result.iloc[0]["Incompleto"]

    def test_complete_record_not_flagged(self):
        df = pd.DataFrame([{
            "Nombre y apellidos": "Ana García",
            "Fecha": "2026-03-10",
            "Día": "Martes",
            "Primera entrada": "08:00",
            "Última salida": "18:30",
            "Horas extras diarias": 1.5,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        }])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert not result.iloc[0]["Incompleto"]


class TestSameRowMidnightExit:
    """New Jibble format: a shift ending after midnight stays on one row with an AM exit."""

    RATES = {"Ana García": {"salario_mensual": 30000.0}}
    HOLIDAYS: list = []

    def test_weekday_am_exit_same_row_splits_diurna_nocturna(self):
        # 8AM entry, 1AM exit on the same row, 8h reported → 4 diurna + 3 nocturna
        # (nocturna caps at midnight; the hour past 12AM is not counted)
        df = pd.DataFrame([{
            "Nombre y apellidos": "Ana García",
            "Fecha": "2026-03-10",
            "Día": "Martes",
            "Primera entrada": "08:00",
            "Última salida": "01:00",
            "Horas extras diarias": 8.0,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        }])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        row = result.iloc[0]
        assert not row["Incompleto"]
        assert row["h_diurna"] == pytest.approx(4.0)
        assert row["h_nocturna"] == pytest.approx(3.0)
        assert row["h_doble"] == pytest.approx(0.0)


class TestLoadApprovedDays:
    def test_builds_employee_date_set(self):
        df = pd.DataFrame([
            {"Empleado": "Ana García", "Fecha": "2026-03-10"},
            {"Empleado": "Carlos López", "Fecha": "2026-03-11"},
        ])
        approved = load_approved_days(df)
        assert ("Ana García", "2026-03-10") in approved
        assert ("Carlos López", "2026-03-11") in approved
        assert len(approved) == 2

    def test_normalizes_timestamp_dates(self):
        df = pd.DataFrame([
            {"Empleado": "Ana García", "Fecha": pd.Timestamp("2026-03-10 00:00:00")},
        ])
        approved = load_approved_days(df)
        assert ("Ana García", "2026-03-10") in approved

    def test_strips_whitespace_in_names(self):
        df = pd.DataFrame([{"Empleado": "  Ana García ", "Fecha": "2026-03-10"}])
        approved = load_approved_days(df)
        assert ("Ana García", "2026-03-10") in approved

    def test_alternate_column_names(self):
        df = pd.DataFrame([{"Nombre": "Ana García", "Día": "2026-03-10"}])
        approved = load_approved_days(df)
        assert ("Ana García", "2026-03-10") in approved

    def test_empty_or_none_returns_empty_set(self):
        assert load_approved_days(None) == set()
        assert load_approved_days(pd.DataFrame()) == set()

    def test_skips_rows_with_missing_values(self):
        df = pd.DataFrame([
            {"Empleado": "Ana García", "Fecha": None},
            {"Empleado": "", "Fecha": "2026-03-10"},
        ])
        assert load_approved_days(df) == set()


class TestApprovalFiltering:
    RATES = {"Ana García": {"salario_mensual": 30000.0}}
    HOLIDAYS: list = []

    def _df(self):
        return pd.DataFrame([
            {
                "Nombre y apellidos": "Ana García",
                "Fecha": "2026-03-10",
                "Día": "Martes",
                "Primera entrada": "08:00",
                "Última salida": "19:00",
                "Horas extras diarias": 2.0,
                "Horas extras en día de descanso": 0.0,
                "Horas extras en festivo": 0.0,
            },
            {
                "Nombre y apellidos": "Ana García",
                "Fecha": "2026-03-11",
                "Día": "Miércoles",
                "Primera entrada": "08:00",
                "Última salida": "20:00",
                "Horas extras diarias": 3.0,
                "Horas extras en día de descanso": 0.0,
                "Horas extras en festivo": 0.0,
            },
        ])

    def test_aprobado_column_reflects_approved_days(self):
        approved = {("Ana García", "2026-03-10")}
        result = process_timesheet(self._df(), self.RATES, self.HOLIDAYS, approved)
        d10 = result[result["Fecha"] == "2026-03-10"].iloc[0]
        d11 = result[result["Fecha"] == "2026-03-11"].iloc[0]
        assert d10["Aprobado"]
        assert not d11["Aprobado"]

    def test_detail_keeps_hours_even_when_not_approved(self):
        # Approval gates the summary, NOT the audit detail
        result = process_timesheet(self._df(), self.RATES, self.HOLIDAYS, approved_days=set())
        assert result["h_diurna"].sum() == pytest.approx(5.0)

    def test_no_approvals_means_all_false(self):
        result = process_timesheet(self._df(), self.RATES, self.HOLIDAYS)
        assert not result["Aprobado"].any()

    def test_summarize_only_sums_approved_days(self):
        approved = {("Ana García", "2026-03-10")}
        detail = process_timesheet(self._df(), self.RATES, self.HOLIDAYS, approved)
        summary = summarize(detail)
        row = summary[summary["Empleado"] == "Ana García"].iloc[0]
        # only the approved 2h day counts, not the 3h day
        assert row["Total_h_diurna"] == pytest.approx(2.0)

    def test_summarize_includes_amount_columns(self):
        approved = {("Ana García", "2026-03-10")}
        detail = process_timesheet(self._df(), self.RATES, self.HOLIDAYS, approved)
        summary = summarize(detail)
        for col in ("Total_h_diurna", "Total_h_nocturna", "Total_h_doble", "Total_a_pagar"):
            assert col in summary.columns

    def test_summarize_empty_when_nothing_approved(self):
        detail = process_timesheet(self._df(), self.RATES, self.HOLIDAYS, approved_days=set())
        summary = summarize(detail)
        assert summary.empty


class TestProcessTimesheetAuditColumns:
    RATES = {
        "Ana García": {"salario_mensual": 30000.0},
        "Carlos López": {"salario_mensual": 25000.0},
    }
    HOLIDAYS: list = []

    def _row(self, employee="Ana García", fecha="2026-03-10", dia="Martes",
             entrada="08:00", salida="18:30", extras=1.5):
        return {
            "Nombre y apellidos": employee,
            "Fecha": fecha,
            "Día": dia,
            "Primera entrada": entrada,
            "Última salida": salida,
            "Horas extras diarias": extras,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
        }

    def test_entrada_salida_columns_present(self):
        df = pd.DataFrame([self._row()])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert "Entrada" in result.columns
        assert "Salida" in result.columns

    def test_h_extras_column_present_and_correct(self):
        df = pd.DataFrame([self._row(extras=1.5)])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert "h_extras" in result.columns
        row = result.iloc[0]
        assert row["h_extras"] == pytest.approx(row["h_diurna"] + row["h_nocturna"] + row["h_doble"])
        assert row["h_extras"] == pytest.approx(1.5)

    def test_h_extras_zero_for_incomplete_row(self):
        df = pd.DataFrame([self._row(**{"salida": None, "extras": 2.0})])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert result.iloc[0]["h_extras"] == pytest.approx(0.0)

    def test_entrada_salida_formatted_as_hhmm(self):
        df = pd.DataFrame([self._row(entrada="08:30", salida="18:45")])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert result.iloc[0]["Entrada"] == "08:30"
        assert result.iloc[0]["Salida"] == "18:45"

    def test_entrada_salida_empty_string_when_none(self):
        df = pd.DataFrame([self._row(**{"entrada": None, "salida": None, "extras": 0.0})])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        assert result.iloc[0]["Entrada"] == ""
        assert result.iloc[0]["Salida"] == ""

    def test_output_sorted_by_employee_then_date(self):
        df = pd.DataFrame([
            self._row(employee="Carlos López", fecha="2026-03-10"),
            self._row(employee="Ana García", fecha="2026-03-12"),
            self._row(employee="Ana García", fecha="2026-03-10"),
        ])
        result = process_timesheet(df, self.RATES, self.HOLIDAYS)
        employees = result["Empleado"].tolist()
        fechas_ana = result[result["Empleado"] == "Ana García"]["Fecha"].tolist()
        assert employees[0] == "Ana García"
        assert employees[-1] == "Carlos López"
        assert fechas_ana == sorted(fechas_ana)
