from datetime import time

import pandas as pd
import pytest

from calculator import (
    MONTHLY_HOURS,
    OvertimeBreakdown,
    _base_hourly_rate,
    _reported_break_hours,
    _split_diurna_nocturna,
    classify_weekday_hours,
    compute_overtime,
    load_approved_days,
    parse_hours,
    parse_time,
    process_timesheet,
    summarize,
)


class TestSplitDiurnaNocturna:
    """Low-level split of an absolute-hour overtime window into day/night."""

    def test_pure_diurna_window(self):
        assert _split_diurna_nocturna(17.0, 21.0) == pytest.approx((4.0, 0.0))

    def test_pure_nocturna_window(self):
        assert _split_diurna_nocturna(21.0, 24.0) == pytest.approx((0.0, 3.0))

    def test_window_crossing_midnight(self):
        # 17:00 → 01:00 next day: 4 diurna (17–21) + 4 nocturna (21–01)
        assert _split_diurna_nocturna(17.0, 25.0) == pytest.approx((4.0, 4.0))

    def test_early_overtime_all_diurna(self):
        # 15:00 → 18:00 is all daytime
        assert _split_diurna_nocturna(15.0, 18.0) == pytest.approx((3.0, 0.0))

    def test_nocturna_ends_at_7am(self):
        # 21:00 → 07:00 is 10h of nighttime
        assert _split_diurna_nocturna(21.0, 31.0) == pytest.approx((0.0, 10.0))

    def test_empty_window(self):
        assert _split_diurna_nocturna(20.0, 20.0) == pytest.approx((0.0, 0.0))


class TestClassifyWeekdayHours:
    """Mon–Fri overtime is presence beyond 9h, classified by real clock time."""

    def test_no_overtime_under_threshold(self):
        # 8h presence (< 9h ordinary) → no overtime
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(16, 0))
        assert diurna == pytest.approx(0.0)
        assert nocturna == pytest.approx(0.0)

    def test_exactly_threshold_no_overtime(self):
        # 9h presence (08:00–17:00) → exactly ordinary, no overtime
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(17, 0))
        assert diurna == pytest.approx(0.0)
        assert nocturna == pytest.approx(0.0)

    def test_all_diurna(self):
        # 08:00–20:00 → 3h overtime, all diurna (17:00–20:00)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(20, 0))
        assert diurna == pytest.approx(3.0)
        assert nocturna == pytest.approx(0.0)

    def test_exit_at_nocturna_boundary(self):
        # 08:00–21:00 → 4h overtime, all diurna (window 17:00–21:00)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(21, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(0.0)

    def test_split_diurna_and_nocturna(self):
        # 08:00–22:00 → 5h overtime → 4 diurna + 1 nocturna
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(22, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(1.0)

    def test_nocturna_not_capped_at_midnight(self):
        # 08:00–01:00 → 8h overtime → 4 diurna + 4 nocturna (NOT capped at midnight)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(1, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(4.0)

    def test_nocturna_runs_until_7am(self):
        # 08:00–07:00 next day → 14h overtime → 4 diurna + 10 nocturna (full night)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(7, 0))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(10.0)

    def test_early_entry_more_than_four_diurna(self):
        # 06:00–22:00 → 7h overtime starting at 15:00 → 6 diurna (15–21) + 1 nocturna
        diurna, nocturna = classify_weekday_hours(time(6, 0), time(22, 0))
        assert diurna == pytest.approx(6.0)
        assert nocturna == pytest.approx(1.0)

    def test_fractional_hours(self):
        # 08:00–21:30 → 4.5h overtime → 4 diurna + 0.5 nocturna
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(21, 30))
        assert diurna == pytest.approx(4.0)
        assert nocturna == pytest.approx(0.5)

    def test_missing_time_returns_zero(self):
        assert classify_weekday_hours(time(8, 0), None) == pytest.approx((0.0, 0.0))
        assert classify_weekday_hours(None, time(20, 0)) == pytest.approx((0.0, 0.0))

    def test_break_under_1h_assumes_full_free_hour(self):
        # 08:00–17:30 with no/short break → 1h assumed → presence 9.5 − 9 = 0.5h diurna
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(17, 30), 0.0)
        assert diurna == pytest.approx(0.5)
        assert nocturna == pytest.approx(0.0)

    def test_extra_break_delays_overtime(self):
        # 08:00–20:00 with 2h break → overtime starts at 18:00 → 2h diurna (not 3h)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(20, 0), 2.0)
        assert diurna == pytest.approx(2.0)
        assert nocturna == pytest.approx(0.0)

    def test_extra_break_repaid_by_late_stay_is_not_overtime(self):
        # 2h break + 1h late: 08:00–18:00 with 2h break → worked 8h → 0 overtime
        # (the late hour just repays the extra break hour)
        diurna, nocturna = classify_weekday_hours(time(8, 0), time(18, 0), 2.0)
        assert diurna == pytest.approx(0.0)
        assert nocturna == pytest.approx(0.0)


class TestSaturdayDouble:
    """Saturday schedule is 8AM–12PM (5h presence incl. break). Overtime past 5h is
    paid DOUBLE — never diurna/nocturna. Ashley, Keylin and Libeth do not work
    Saturdays, so ANY Saturday hour they log is double. Computed from clock time
    (Jibble's Saturday daily-OT column is unreliable).
    """

    RATES = {
        "Ana García": {"salario_mensual": 30000.0},
        "Keylin Rivas": {"salario_mensual": 30000.0},
    }
    HOLIDAYS: list = []

    def _row(self, salida, entrada="08:00", empleado="Ana García", extras=99.0, descanso=0.0):
        # extras is intentionally large/wrong: Saturday must IGNORE Jibble's column.
        return pd.Series({
            "Nombre y apellidos": empleado,
            "Fecha": "2026-03-14",
            "Día": "Sábado",
            "Primera entrada": entrada,
            "Última salida": salida,
            "Horas extras diarias": extras,
            "Horas extras en día de descanso": 0.0,
            "Horas extras en festivo": 0.0,
            "Horas de descanso (remunerado)": 0.0,
            "Horas de descanso (no remunerado)": descanso,
        })

    def test_exit_at_noon_no_overtime(self):
        # 4h presence (< 5h threshold) → no overtime
        b = compute_overtime(self._row("12:00"), self.RATES, self.HOLIDAYS)
        assert b.total_hours == pytest.approx(0.0)

    def test_exit_at_threshold_no_overtime(self):
        # 08:00–13:00 = 5h presence (= threshold) → no overtime
        b = compute_overtime(self._row("13:00"), self.RATES, self.HOLIDAYS)
        assert b.total_hours == pytest.approx(0.0)

    def test_overtime_is_double(self):
        # 08:00–15:00 = 7h presence → 2h double (not diurna/nocturna)
        b = compute_overtime(self._row("15:00"), self.RATES, self.HOLIDAYS)
        assert b.doble_hours == pytest.approx(2.0)
        assert b.diurna_hours == pytest.approx(0.0)
        assert b.nocturna_hours == pytest.approx(0.0)
        assert b.doble_amount == pytest.approx(2.0 * 30000.0 / (4.33 * 44) * 2.0)

    def test_overtime_past_midnight_all_double(self):
        # 08:00–01:00 = 17h presence → 12h double (no nocturna split on Saturday)
        b = compute_overtime(self._row("01:00"), self.RATES, self.HOLIDAYS)
        assert b.doble_hours == pytest.approx(12.0)
        assert b.diurna_hours == pytest.approx(0.0)
        assert b.nocturna_hours == pytest.approx(0.0)

    def test_ignores_jibble_daily_overtime_column(self):
        # Jibble reports 99h (wrong Saturday schedule); we must use clock time only.
        b = compute_overtime(self._row("16:00", extras=99.0), self.RATES, self.HOLIDAYS)
        assert b.total_hours == pytest.approx(3.0)

    def test_all_day_double_employee_no_threshold(self):
        # Keylin does not work Saturdays → all 4h presence is double (no 5h subtraction)
        b = compute_overtime(self._row("12:00", empleado="Keylin Rivas"), self.RATES, self.HOLIDAYS)
        assert b.doble_hours == pytest.approx(4.0)
        assert b.diurna_hours == pytest.approx(0.0)
        assert b.doble_amount == pytest.approx(4.0 * 30000.0 / (4.33 * 44) * 2.0)

    def test_extra_break_reduces_double(self):
        # 08:00–16:00 = 8h presence with 2h break → 8 − 4 − 2 = 2h double
        b = compute_overtime(self._row("16:00", descanso=2.0), self.RATES, self.HOLIDAYS)
        assert b.doble_hours == pytest.approx(2.0)

    def test_all_day_double_employee_subtracts_real_break(self):
        # Keylin with a 1h break → 4h presence − 1h real break = 3h double (no free hour)
        b = compute_overtime(
            self._row("12:00", empleado="Keylin Rivas", descanso=1.0), self.RATES, self.HOLIDAYS
        )
        assert b.doble_hours == pytest.approx(3.0)


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


class TestReportedBreakHours:
    def test_sums_paid_and_unpaid(self):
        row = pd.Series({
            "Horas de descanso (remunerado)": "0h 30m",
            "Horas de descanso (no remunerado)": "1h 00m",
        })
        assert _reported_break_hours(row) == pytest.approx(1.5)

    def test_jibble_format(self):
        row = pd.Series({
            "Horas de descanso (remunerado)": "0h 00m",
            "Horas de descanso (no remunerado)": "0h 45m",
        })
        assert _reported_break_hours(row) == pytest.approx(0.75)

    def test_missing_columns_return_zero(self):
        assert _reported_break_hours(pd.Series({})) == pytest.approx(0.0)

    def test_nan_returns_zero(self):
        row = pd.Series({
            "Horas de descanso (remunerado)": float("nan"),
            "Horas de descanso (no remunerado)": pd.NaT,
        })
        assert _reported_break_hours(row) == pytest.approx(0.0)


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
        # 8AM entry, 1AM exit on the same row → 17h presence, 8h overtime
        # → 4 diurna (17–21) + 4 nocturna (21–01); nocturna runs past midnight
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
        assert row["h_nocturna"] == pytest.approx(4.0)
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


class TestBaseHourlyRate:
    """Resolve the ordinary hourly rate: tarifa_hora wins, else derive from salary."""

    def test_tarifa_hora_takes_precedence(self):
        # Both present: the explicit hourly rate is used, salary is ignored.
        entry = {"salario_mensual": 30000.0, "tarifa_hora": 200.0}
        assert _base_hourly_rate(entry) == pytest.approx(200.0)

    def test_tarifa_hora_only(self):
        assert _base_hourly_rate({"tarifa_hora": 95.0}) == pytest.approx(95.0)

    def test_salary_only_is_derived(self):
        entry = {"salario_mensual": 30000.0}
        assert _base_hourly_rate(entry) == pytest.approx(30000.0 / MONTHLY_HOURS)

    def test_neither_field_is_zero(self):
        assert _base_hourly_rate({}) == pytest.approx(0.0)

    def test_zero_tarifa_falls_back_to_salary(self):
        entry = {"salario_mensual": 30000.0, "tarifa_hora": 0}
        assert _base_hourly_rate(entry) == pytest.approx(30000.0 / MONTHLY_HOURS)
