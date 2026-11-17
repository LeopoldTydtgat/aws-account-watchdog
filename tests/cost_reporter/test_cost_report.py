from datetime import date
from decimal import Decimal

from cost_report import (
    build_summary,
    format_email,
    parse_cost_response,
    pct_change,
    report_dates,
    status_line,
)


def ce_period(day, groups, estimated=False):
    return {
        "TimePeriod": {"Start": day, "End": "x"},
        "Estimated": estimated,
        "Groups": [
            {"Keys": [name], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}
            for name, amount in groups
        ],
    }


def test_report_dates_cover_yesterday_end_exclusive():
    assert report_dates(date(2026, 11, 16)) == ("2026-11-15", "2026-11-16")


def test_report_dates_backfill_crosses_month():
    assert report_dates(date(2026, 11, 3), days=7) == ("2026-10-27", "2026-11-03")


def test_parse_sums_services_and_drops_zero_rows():
    response = {"ResultsByTime": [ce_period("2026-11-15", [
        ("AWS Cost Explorer", "0.03"),
        ("Amazon Simple Storage Service", "0.0000012"),
        ("AWS Lambda", "0"),
    ], estimated=True)]}
    day = parse_cost_response(response)["2026-11-15"]
    assert day["total"] == Decimal("0.0300")
    assert day["services"] == {"AWS Cost Explorer": Decimal("0.0300")}
    assert day["estimated"] is True


def test_parse_empty_day_is_zero():
    day = parse_cost_response({"ResultsByTime": [ce_period("2026-11-15", [])]})["2026-11-15"]
    assert day["total"] == Decimal("0")
    assert day["services"] == {}


def test_pct_change():
    assert pct_change(Decimal("0.06"), Decimal("0.04")) == Decimal("50.0")
    assert pct_change(Decimal("0.02"), Decimal("0.04")) == Decimal("-50.0")
    assert pct_change(Decimal("0.02"), Decimal("0")) is None
    assert pct_change(Decimal("0.02"), None) is None


def test_summary_with_full_week():
    history = {f"2026-11-{d:02d}": Decimal("0.02") for d in range(8, 15)}
    history["2026-11-15"] = Decimal("0.03")
    s = build_summary("2026-11-15", history, "1.50")
    assert s["seven_day_avg"] == Decimal("0.0200")
    assert s["history_days"] == 7
    assert s["change_pct"] == Decimal("50.0")
    assert s["projected_month"] == Decimal("0.60")
    assert s["status"].startswith("OK")


def test_summary_first_ever_day_uses_own_total_for_projection():
    s = build_summary("2026-11-15", {"2026-11-15": Decimal("0.04")}, "1.50")
    assert s["seven_day_avg"] is None
    assert s["history_days"] == 0
    assert s["prior_total"] is None
    assert s["projected_month"] == Decimal("1.20")


def test_spike_needs_double_average_and_floor():
    assert status_line(Decimal("0.03"), Decimal("0.01"), Decimal("0.30"), Decimal("1.50")).startswith("OK")
    assert status_line(Decimal("0.10"), Decimal("0.02"), Decimal("0.60"), Decimal("1.50")).startswith("SPIKE")


def test_over_target():
    assert status_line(Decimal("0.06"), Decimal("0.06"), Decimal("1.80"), Decimal("1.50")).startswith("OVER TARGET")


def test_email_subject_and_top_five():
    services = {f"Service {i}": Decimal(i) / 100 for i in range(1, 8)}
    s = build_summary("2026-11-15", {"2026-11-15": Decimal("0.28")}, "1.50")
    subject, body = format_email(s, services, estimated=False)
    assert subject.startswith("Watchdog cost report 2026-11-15: $0.2800")
    assert "1. Service 7: $0.0700" in body
    assert "5. Service 3" in body
    assert "Service 2" not in body
    assert "building history: 0 of 7 days" in body


def test_email_no_usage():
    s = build_summary("2026-11-15", {"2026-11-15": Decimal("0")}, "1.50")
    _, body = format_email(s, {}, estimated=True)
    assert "No chargeable usage." in body
    assert "estimated" in body
