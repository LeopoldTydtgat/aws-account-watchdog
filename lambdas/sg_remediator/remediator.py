"""Security-group remediator.

AWS Config flags a security group as NON_COMPLIANT when it is open to the
internet on SSH (22) or RDP (3389). EventBridge passes that verdict here.

The function reads the group as it is now, works out exactly which rules
are exposed, logs an incident to the watchdog-data table and emails an
alert. What it does about the exposure depends on the mode:

  dry run (stage 1)   WOULD REVOKE: changes nothing
  allow-listed group  ALERT ONLY: tagged watchdog:exclude=true
  live (stage 2)      REVOKE: removes only the exposed rules

DRY_RUN is on unless it is set to exactly "false", so a missing or
mistyped setting fails safe. The stage 1 role also has no permission to
revoke anything.

The same Config verdict can arrive more than once (EventBridge and Lambda
both retry). The incident key is the evaluation time plus the group ID,
and a conditional write makes the second copy a no-op.
"""

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from sg_rules import (
    NO_ACTION,
    REVOKE,
    decide_action,
    find_exposures,
    format_email,
    is_excluded,
    parse_ports,
    parse_time,
    revoke_payload,
    to_json,
)

TABLE_NAME = os.environ.get("TABLE_NAME", "watchdog-data")
EMAIL_PARAM = os.environ.get("REPORT_EMAIL_PARAM", "/watchdog/report-email")
RULE_NAME = os.environ.get("CONFIG_RULE_NAME", "watchdog-restricted-admin-ports")
BLOCKED_PORTS = parse_ports(os.environ.get("BLOCKED_PORTS", "22,3389"))
METRIC_NAMESPACE = "Watchdog"
PK = "INC"

_clients = {}


def client(name):
    if name not in _clients:
        _clients[name] = boto3.client(name)
    return _clients[name]


def dry_run():
    return os.environ.get("DRY_RUN", "true").strip().lower() != "false"


def log(level, message, **fields):
    print(json.dumps({"level": level, "message": message, **fields}, default=str))


def put_metric(name):
    client("cloudwatch").put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[{"MetricName": name, "Value": 1, "Unit": "Count"}],
    )


def describe_group(sg_id):
    """The group as it is now, or None if it was deleted after Config looked."""
    try:
        groups = client("ec2").describe_security_groups(GroupIds=[sg_id])["SecurityGroups"]
    except ClientError as error:
        if error.response["Error"]["Code"] == "InvalidGroup.NotFound":
            return None
        raise
    return groups[0] if groups else None


def incident_item(incident, status):
    item = {
        "pk": {"S": PK},
        "sk": {"S": incident["sk"]},
        "status": {"S": status},
        "sg_id": {"S": incident["sg_id"]},
        "sg_name": {"S": incident.get("sg_name") or ""},
        "vpc_id": {"S": incident.get("vpc_id") or ""},
        "rule": {"S": incident["rule"]},
        "mode": {"S": incident["mode"]},
        "action": {"S": incident["action"]},
        "excluded": {"BOOL": incident["excluded"]},
        "before": {"S": to_json(incident["before"])},
        "after": {"S": to_json(incident["after"])},
        "detected_at": {"S": incident["detected_at"]},
        "processed_at": {"S": incident["processed_at"]},
        "latency_seconds": {"N": str(incident["latency_seconds"])},
        "event_id": {"S": incident["event_id"]},
    }
    if "notified_at" in incident:
        item["notified_at"] = {"S": incident["notified_at"]}
    return item


def claim(incident):
    """Write the incident as OPEN unless this exact one was already handled.
    An earlier attempt that died before emailing left it OPEN, so a retry
    may take it over; only NOTIFIED counts as done."""
    try:
        client("dynamodb").put_item(
            TableName=TABLE_NAME,
            Item=incident_item(incident, "OPEN"),
            ConditionExpression="attribute_not_exists(sk) OR #status <> :done",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":done": {"S": "NOTIFIED"}},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    return True


def finish(incident):
    client("dynamodb").put_item(TableName=TABLE_NAME, Item=incident_item(incident, "NOTIFIED"))


def send_alert(subject, body):
    address = client("ssm").get_parameter(Name=EMAIL_PARAM)["Parameter"]["Value"]
    client("ses").send_email(
        Source=address,
        Destination={"ToAddresses": [address]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )


def is_target(detail):
    return (
        detail.get("configRuleName") == RULE_NAME
        and detail.get("resourceType") == "AWS::EC2::SecurityGroup"
        and detail.get("newEvaluationResult", {}).get("complianceType") == "NON_COMPLIANT"
    )


def run(event, now):
    event = event or {}
    detail = event.get("detail", {})
    if not is_target(detail):
        log("INFO", "not a non-compliant result for this rule, ignored", event_id=event.get("id"))
        return {"action": "IGNORED"}

    sg_id = detail["resourceId"]
    detected_at = detail["newEvaluationResult"]["resultRecordedTime"]

    group = describe_group(sg_id)
    if group is None:
        log("INFO", "security group no longer exists", sg_id=sg_id)
        return {"action": "GONE", "sg_id": sg_id}

    before = find_exposures(group, BLOCKED_PORTS)
    excluded = is_excluded(group)
    is_dry_run = dry_run()
    action = decide_action(before, excluded, is_dry_run)

    if action == NO_ACTION:
        log("INFO", "already closed by the time it was checked", sg_id=sg_id)
        return {"action": NO_ACTION, "sg_id": sg_id}

    incident = {
        "sk": f"{detected_at}#{sg_id}",
        "sg_id": sg_id,
        "sg_name": group.get("GroupName"),
        "vpc_id": group.get("VpcId"),
        "rule": RULE_NAME,
        "mode": "DRY RUN" if is_dry_run else "LIVE",
        "action": action,
        "excluded": excluded,
        "before": before,
        "after": before,
        "detected_at": detected_at,
        "processed_at": now.isoformat(timespec="seconds"),
        "latency_seconds": round((now - parse_time(detected_at)).total_seconds(), 1),
        "event_id": event.get("id", ""),
    }

    if not claim(incident):
        log("INFO", "duplicate event, already handled", sk=incident["sk"])
        return {"action": "DUPLICATE", "sk": incident["sk"]}

    if action == REVOKE:
        client("ec2").revoke_security_group_ingress(GroupId=sg_id, IpPermissions=revoke_payload(before))
        after_group = describe_group(sg_id)
        incident["after"] = find_exposures(after_group, BLOCKED_PORTS) if after_group else []

    subject, body = format_email(incident)
    send_alert(subject, body)

    incident["notified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    finish(incident)

    return {
        "action": action,
        "sk": incident["sk"],
        "sg_id": sg_id,
        "latency_seconds": incident["latency_seconds"],
    }


def lambda_handler(event, context):
    try:
        result = run(event, datetime.now(timezone.utc))
    except Exception as error:
        log("ERROR", "sg remediation failed", error=repr(error), event_id=(event or {}).get("id"))
        try:
            put_metric("SgRemediatorFailure")
        except Exception as metric_error:
            log("ERROR", "could not publish failure metric", error=repr(metric_error))
        raise

    put_metric("SgRemediatorSuccess")
    log("INFO", "sg remediation handled", **result)
    return result
