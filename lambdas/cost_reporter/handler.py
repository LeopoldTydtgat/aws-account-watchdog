"""Nightly cost reporter.

Runs at 06:00 SAST. Asks Cost Explorer what yesterday cost, stores it in
the watchdog-data table, reads the last week back for the trend, and
emails a short ops report. Publishes CostReportSuccess or
CostReportFailure so a missing report can raise an alarm.

Manual backfill: invoke with {"backfill_days": 7} to load the last 7 days
in one Cost Explorer request (still $0.01).
"""

import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

from cost_report import build_summary, format_email, parse_cost_response, report_dates

TABLE_NAME = os.environ.get("TABLE_NAME", "watchdog-data")
EMAIL_PARAM = os.environ.get("REPORT_EMAIL_PARAM", "/watchdog/report-email")
TARGET_MONTHLY_USD = os.environ.get("TARGET_MONTHLY_USD", "1.50")
METRIC_NAMESPACE = "Watchdog"
PK = "COST"
MAX_BACKFILL_DAYS = 30

_clients = {}


def client(name):
    """One client per service, reused across warm invocations.
    Cost Explorer only has an endpoint in us-east-1."""
    if name not in _clients:
        region = "us-east-1" if name == "ce" else None
        _clients[name] = boto3.client(name, region_name=region)
    return _clients[name]


def log(level, message, **fields):
    print(json.dumps({"level": level, "message": message, **fields}, default=str))


def put_metric(name):
    client("cloudwatch").put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[{"MetricName": name, "Value": 1, "Unit": "Count"}],
    )


def fetch_costs(start, end):
    """Daily cost by service, excluding credits and refunds, so the report
    shows real usage rather than a credit-adjusted zero."""
    request = {
        "TimePeriod": {"Start": start, "End": end},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "Filter": {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}},
    }
    results = []
    while True:
        response = client("ce").get_cost_and_usage(**request)
        results.extend(response.get("ResultsByTime", []))
        token = response.get("NextPageToken")
        if not token:
            return {"ResultsByTime": results}
        request["NextPageToken"] = token


def store_day(day, data, now_iso):
    """Same key every time, so re-running a day overwrites it. That makes
    retries and backfills safe, and picks up Cost Explorer's later revisions."""
    client("dynamodb").put_item(
        TableName=TABLE_NAME,
        Item={
            "pk": {"S": PK},
            "sk": {"S": day},
            "total": {"N": str(data["total"])},
            "services": {"M": {name: {"N": str(amount)} for name, amount in data["services"].items()}},
            "estimated": {"BOOL": data["estimated"]},
            "updated_at": {"S": now_iso},
        },
    )


def load_history(first_day, last_day):
    response = client("dynamodb").query(
        TableName=TABLE_NAME,
        KeyConditionExpression="pk = :pk AND sk BETWEEN :first AND :last",
        ExpressionAttributeValues={
            ":pk": {"S": PK},
            ":first": {"S": first_day},
            ":last": {"S": last_day},
        },
    )
    return {item["sk"]["S"]: Decimal(item["total"]["N"]) for item in response.get("Items", [])}


def send_report(subject, body):
    address = client("ssm").get_parameter(Name=EMAIL_PARAM)["Parameter"]["Value"]
    client("ses").send_email(
        Source=address,
        Destination={"ToAddresses": [address]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )


def run(event, today):
    days = int((event or {}).get("backfill_days", 1))
    days = max(1, min(days, MAX_BACKFILL_DAYS))

    start, end = report_dates(today, days)
    costs = parse_cost_response(fetch_costs(start, end))

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for day, data in sorted(costs.items()):
        store_day(day, data, now_iso)

    report_day = (today - timedelta(days=1)).isoformat()
    yesterday = costs.get(report_day, {"total": Decimal("0"), "services": {}, "estimated": True})

    first_day = (today - timedelta(days=8)).isoformat()
    history = load_history(first_day, report_day)
    history[report_day] = yesterday["total"]

    summary = build_summary(report_day, history, TARGET_MONTHLY_USD)
    subject, body = format_email(summary, yesterday["services"], yesterday["estimated"])
    send_report(subject, body)

    return {
        "day": report_day,
        "total": str(summary["total"]),
        "status": summary["status"],
        "days_stored": len(costs),
    }


def lambda_handler(event, context):
    try:
        result = run(event, datetime.now(timezone.utc).date())
    except Exception as error:
        log("ERROR", "cost report failed", error=repr(error))
        try:
            put_metric("CostReportFailure")
        except Exception as metric_error:
            log("ERROR", "could not publish failure metric", error=repr(metric_error))
        raise

    put_metric("CostReportSuccess")
    log("INFO", "cost report sent", **result)
    return result
