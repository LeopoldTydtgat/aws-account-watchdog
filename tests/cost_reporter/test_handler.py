"""Runs the handler end to end against stubbed AWS clients. No network,
no credentials: every call is checked against what the code should send."""

import boto3
import pytest
from botocore.stub import ANY, Stubber

import handler


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    made = {}
    for name in ("ce", "dynamodb", "ssm", "ses", "cloudwatch"):
        c = boto3.client(name, region_name="us-east-1" if name == "ce" else "eu-north-1")
        made[name] = Stubber(c)
        handler._clients[name] = c
    for s in made.values():
        s.activate()
    yield made
    for s in made.values():
        s.assert_no_pending_responses()
        s.deactivate()
    handler._clients.clear()


def ce_response(day, amount):
    return {"ResultsByTime": [{
        "TimePeriod": {"Start": day, "End": "2026-11-16"},
        "Estimated": True,
        "Groups": [{"Keys": ["AWS Cost Explorer"],
                    "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}],
    }]}


def test_full_run_stores_reads_and_emails(stubs, monkeypatch):
    monkeypatch.setattr(handler, "datetime", FixedDatetime)

    stubs["ce"].add_response("get_cost_and_usage", ce_response("2026-11-15", "0.03"), {
        "TimePeriod": {"Start": "2026-11-15", "End": "2026-11-16"},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "Filter": {"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}},
    })
    stubs["dynamodb"].add_response("put_item", {}, {"TableName": "watchdog-data", "Item": ANY})
    stubs["dynamodb"].add_response("query", {"Items": [
        {"pk": {"S": "COST"}, "sk": {"S": "2026-11-14"}, "total": {"N": "0.02"}},
    ]}, {
        "TableName": "watchdog-data",
        "KeyConditionExpression": ANY,
        "ExpressionAttributeValues": {":pk": {"S": "COST"}, ":first": {"S": "2026-11-08"}, ":last": {"S": "2026-11-15"}},
    })
    stubs["ssm"].add_response("get_parameter",
                              {"Parameter": {"Name": "/watchdog/report-email", "Value": "me@example.com"}},
                              {"Name": "/watchdog/report-email"})
    stubs["ses"].add_response("send_email", {"MessageId": "abc"}, {
        "Source": "me@example.com", "Destination": {"ToAddresses": ["me@example.com"]}, "Message": ANY})
    stubs["cloudwatch"].add_response("put_metric_data", {}, {
        "Namespace": "Watchdog", "MetricData": [{"MetricName": "CostReportSuccess", "Value": 1, "Unit": "Count"}]})

    result = handler.lambda_handler({}, None)

    assert result == {"day": "2026-11-15", "total": "0.0300",
                      "status": "OK: on pace for $0.60/month against $1.50", "days_stored": 1}


def test_failure_publishes_failure_metric_and_raises(stubs, monkeypatch):
    monkeypatch.setattr(handler, "datetime", FixedDatetime)
    stubs["ce"].add_client_error("get_cost_and_usage", service_error_code="LimitExceededException")
    stubs["cloudwatch"].add_response("put_metric_data", {}, {
        "Namespace": "Watchdog", "MetricData": [{"MetricName": "CostReportFailure", "Value": 1, "Unit": "Count"}]})

    with pytest.raises(Exception):
        handler.lambda_handler({}, None)


class FixedDatetime:
    """Freezes 'now' at 16 Nov 2026 04:00 UTC (06:00 SAST)."""

    @staticmethod
    def now(tz=None):
        from datetime import datetime, timezone
        return datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)
