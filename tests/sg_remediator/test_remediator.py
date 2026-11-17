"""Runs the remediator end to end against stubbed AWS clients. No network,
no credentials: every call is checked against what the code should send,
and a call the code should not make fails the test."""

from datetime import datetime, timezone

import boto3
import pytest
from botocore.stub import ANY, Stubber

import remediator

NOW = datetime(2026, 11, 17, 13, 1, 30, tzinfo=timezone.utc)
RECORDED = "2026-11-17T13:00:00.000Z"


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("DRY_RUN", raising=False)
    made = {}
    for name in ("ec2", "dynamodb", "ssm", "ses", "cloudwatch"):
        c = boto3.client(name, region_name="eu-north-1")
        made[name] = Stubber(c)
        remediator._clients[name] = c
    for s in made.values():
        s.activate()
    yield made
    for s in made.values():
        s.assert_no_pending_responses()
        s.deactivate()
    remediator._clients.clear()


def config_event(sg_id="sg-0d9ce1febc31da95f", compliance="NON_COMPLIANT", rule="watchdog-restricted-admin-ports"):
    return {
        "id": "evt-1",
        "detail-type": "Config Rules Compliance Change",
        "source": "aws.config",
        "detail": {
            "resourceId": sg_id,
            "resourceType": "AWS::EC2::SecurityGroup",
            "configRuleName": rule,
            "messageType": "ComplianceChangeNotification",
            "newEvaluationResult": {"complianceType": compliance, "resultRecordedTime": RECORDED},
        },
    }


def sg(sg_id="sg-0d9ce1febc31da95f", cidr="0.0.0.0/0", tags=None):
    return {"SecurityGroups": [{
        "GroupId": sg_id, "GroupName": "watchdog-range-admin", "VpcId": "vpc-1",
        "OwnerId": "895196059907", "Description": "x",
        "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                           "IpRanges": [{"CidrIp": cidr}], "Ipv6Ranges": []}],
        "Tags": tags or [],
    }]}


def expect_describe(stubs, response, sg_id="sg-0d9ce1febc31da95f"):
    stubs["ec2"].add_response("describe_security_groups", response, {"GroupIds": [sg_id]})


def expect_claim(stubs):
    stubs["dynamodb"].add_response("put_item", {}, {
        "TableName": "watchdog-data",
        "Item": ANY,
        "ConditionExpression": "attribute_not_exists(sk) OR #status <> :done",
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {":done": {"S": "NOTIFIED"}},
    })


def expect_email_and_finish(stubs, captured):
    stubs["ssm"].add_response("get_parameter", {"Parameter": {"Value": "me@example.com"}},
                              {"Name": "/watchdog/report-email"})
    stubs["ses"].add_response("send_email", {"MessageId": "m-1"}, {
        "Source": "me@example.com",
        "Destination": {"ToAddresses": ["me@example.com"]},
        "Message": ANY,
    })
    stubs["dynamodb"].add_response("put_item", {}, {"TableName": "watchdog-data", "Item": ANY})

    original = remediator.send_alert

    def spy(subject, body):
        captured["subject"], captured["body"] = subject, body
        original(subject, body)

    return spy


def test_dry_run_alerts_and_changes_nothing(stubs, monkeypatch):
    captured = {}
    expect_describe(stubs, sg())
    expect_claim(stubs)
    monkeypatch.setattr(remediator, "send_alert", expect_email_and_finish(stubs, captured))

    result = remediator.run(config_event(), NOW)

    assert result["action"] == "WOULD_REVOKE"
    assert result["sk"] == f"{RECORDED}#sg-0d9ce1febc31da95f"
    assert result["latency_seconds"] == 90.0
    assert captured["subject"].startswith("[Watchdog] WOULD REVOKE: sg-0d9ce1febc31da95f")
    # No revoke_security_group_ingress was stubbed, so any attempt would have failed the test.


def test_mistyped_dry_run_setting_still_dry_runs(stubs, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "flase")
    expect_describe(stubs, sg())
    expect_claim(stubs)
    monkeypatch.setattr(remediator, "send_alert", expect_email_and_finish(stubs, {}))
    assert remediator.run(config_event(), NOW)["action"] == "WOULD_REVOKE"


def test_excluded_group_is_alert_only_even_when_live(stubs, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    expect_describe(stubs, sg(tags=[{"Key": "watchdog:exclude", "Value": "true"}]))
    expect_claim(stubs)
    monkeypatch.setattr(remediator, "send_alert", expect_email_and_finish(stubs, {}))
    assert remediator.run(config_event(), NOW)["action"] == "ALERT_ONLY"


def test_live_mode_revokes_only_the_exposed_rule(stubs, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    expect_describe(stubs, sg())
    expect_claim(stubs)
    stubs["ec2"].add_response("revoke_security_group_ingress", {"Return": True}, {
        "GroupId": "sg-0d9ce1febc31da95f",
        "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                           "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    })
    expect_describe(stubs, sg(cidr="10.20.0.0/16"))
    captured = {}
    monkeypatch.setattr(remediator, "send_alert", expect_email_and_finish(stubs, captured))

    assert remediator.run(config_event(), NOW)["action"] == "REVOKE"
    assert "Still open after revoke: nothing" in captured["body"]


def test_duplicate_event_is_skipped(stubs):
    expect_describe(stubs, sg())
    stubs["dynamodb"].add_client_error("put_item", service_error_code="ConditionalCheckFailedException")
    assert remediator.run(config_event(), NOW)["action"] == "DUPLICATE"


def test_already_closed_group_does_nothing(stubs):
    expect_describe(stubs, sg(cidr="10.20.0.0/16"))
    assert remediator.run(config_event(), NOW)["action"] == "NO_ACTION"


def test_deleted_group_does_nothing(stubs):
    stubs["ec2"].add_client_error("describe_security_groups", service_error_code="InvalidGroup.NotFound")
    assert remediator.run(config_event(), NOW)["action"] == "GONE"


@pytest.mark.parametrize("event", [
    config_event(compliance="COMPLIANT"),
    config_event(rule="some-other-rule"),
    {},
    None,
])
def test_other_events_are_ignored(stubs, event):
    assert remediator.run(event, NOW)["action"] == "IGNORED"


def test_failure_publishes_metric_and_raises(stubs):
    expect_describe(stubs, sg())
    stubs["dynamodb"].add_client_error("put_item", service_error_code="ProvisionedThroughputExceededException")
    stubs["cloudwatch"].add_response("put_metric_data", {}, {
        "Namespace": "Watchdog",
        "MetricData": [{"MetricName": "SgRemediatorFailure", "Value": 1, "Unit": "Count"}],
    })
    with pytest.raises(Exception):
        remediator.lambda_handler(config_event(), None)
