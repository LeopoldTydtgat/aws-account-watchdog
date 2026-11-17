"""Pure report logic for the cost reporter. No AWS calls here, so it is
easy to test: dates, Cost Explorer parsing, trend maths and the email."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

FOUR_PLACES = Decimal("0.0001")
TOP_SERVICES = 5

# A day is flagged only if it is both well above normal and big enough to
# matter. Doubling from $0.01 to $0.02 is noise, not an incident.
SPIKE_MULTIPLIER = Decimal("2")
SPIKE_FLOOR_USD = Decimal("0.05")


def report_dates(today, days=1):
    """Cost Explorer periods are start-inclusive, end-exclusive.
    Returns (start, end) covering the `days` complete days before today."""
    end = today
    start = today - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def parse_cost_response(response):
    """Turns a GetCostAndUsage response (DAILY, grouped by SERVICE) into
    {"YYYY-MM-DD": {"total": Decimal, "services": {name: Decimal},
    "estimated": bool}}. Services that round to zero are dropped."""
    days = {}
    for period in response.get("ResultsByTime", []):
        day = period["TimePeriod"]["Start"]
        services = {}
        for group in period.get("Groups", []):
            amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
            amount = amount.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            if amount != 0:
                services[group["Keys"][0]] = amount
        days[day] = {
            "total": sum(services.values(), Decimal("0")),
            "services": services,
            "estimated": bool(period.get("Estimated", False)),
        }
    return days


def pct_change(current, previous):
    """Percentage change, or None when there is nothing to compare with."""
    if previous is None or previous == 0:
        return None
    return ((current - previous) / previous * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )


def build_summary(day, history, target_monthly_usd):
    """day: the report date (YYYY-MM-DD).
    history: {date: Decimal total} for the report day and the days before it.
    Returns the numbers the email and the status line are made from."""
    today_total = history[day]
    report_date = date.fromisoformat(day)

    prior_day = (report_date - timedelta(days=1)).isoformat()
    prior_total = history.get(prior_day)

    window = [
        history[d]
        for d in (
            (report_date - timedelta(days=n)).isoformat() for n in range(1, 8)
        )
        if d in history
    ]
    seven_day_avg = (
        (sum(window, Decimal("0")) / len(window)).quantize(
            FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        if window
        else None
    )

    basis = seven_day_avg if seven_day_avg is not None else today_total
    projected_month = (basis * 30).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "day": day,
        "total": today_total,
        "prior_total": prior_total,
        "change_pct": pct_change(today_total, prior_total),
        "seven_day_avg": seven_day_avg,
        "history_days": len(window),
        "projected_month": projected_month,
        "target_month": Decimal(target_monthly_usd),
        "status": status_line(today_total, seven_day_avg, projected_month,
                              Decimal(target_monthly_usd)),
    }


def status_line(total, seven_day_avg, projected_month, target_month):
    if (
        seven_day_avg is not None
        and total >= SPIKE_FLOOR_USD
        and total > seven_day_avg * SPIKE_MULTIPLIER
    ):
        return "SPIKE: yesterday was more than double the 7-day average"
    if projected_month > target_month:
        return f"OVER TARGET: on pace for ${projected_month}/month against ${target_month}"
    return f"OK: on pace for ${projected_month}/month against ${target_month}"


def money(value):
    return "n/a" if value is None else f"${value:.4f}"


def format_email(summary, services, estimated):
    """Returns (subject, body). Subject keeps 'Watchdog' first because the
    mail filter that stops these landing in spam matches on it."""
    status_word = summary["status"].split(":")[0]
    subject = f"Watchdog cost report {summary['day']}: {money(summary['total'])} ({status_word})"

    change = summary["change_pct"]
    change_text = "n/a" if change is None else f"{change:+}%"

    if summary["history_days"] < 7:
        avg_text = f"{money(summary['seven_day_avg'])} (building history: {summary['history_days']} of 7 days)"
    else:
        avg_text = money(summary["seven_day_avg"])

    top = sorted(services.items(), key=lambda kv: kv[1], reverse=True)[:TOP_SERVICES]
    if top:
        top_lines = "\n".join(f"  {i}. {name}: {money(amount)}"
                              for i, (name, amount) in enumerate(top, 1))
    else:
        top_lines = "  No chargeable usage."

    lines = [
        f"Day (UTC):      {summary['day']}{'  (estimated, AWS may still revise it)' if estimated else ''}",
        f"Total:          {money(summary['total'])}",
        f"Prior day:      {money(summary['prior_total'])}  (change {change_text})",
        f"7-day average:  {avg_text}",
        "",
        "Top services:",
        top_lines,
        "",
        f"Status: {summary['status']}",
        "",
        "Figures are usage before credits and refunds.",
        "This report cost about $0.01 (one Cost Explorer request).",
    ]
    return subject, "\n".join(lines) + "\n"
