"""Weekly housekeeper.

Runs every Monday at 06:30 SAST. Reads the EC2 resources and resource
tags in this region, looks for things that cost money while doing nothing
(stopped servers, loose disks, old snapshots, idle public IPs) and for
resources missing the required tags, stores the result in the
watchdog-data table and emails a plain-English report.

It only looks. The role has no permission to stop, delete or tag
anything, so a bug can never remove a resource.

Publishes HousekeepingSuccess or HousekeepingFailure so a missing report
can raise an alarm (Phase 4).
"""

import json
import os
from datetime import datetime, timezone

import boto3

from hk_rules import (
    build_report,
    default_vpc_ids,
    ec2_inventory,
    find_idle_addresses,
    find_old_snapshots,
    find_stopped_instances,
    find_unattached_volumes,
    find_untagged,
    format_email,
    parse_list,
    skipped_defaults,
    to_json,
)

TABLE_NAME = os.environ.get("TABLE_NAME", "watchdog-data")
EMAIL_PARAM = os.environ.get("REPORT_EMAIL_PARAM", "/watchdog/report-email")
REQUIRED_TAGS = parse_list(os.environ.get("REQUIRED_TAGS", "project,owner"))
SNAPSHOT_MAX_AGE_DAYS = int(os.environ.get("SNAPSHOT_MAX_AGE_DAYS", "30"))
METRIC_NAMESPACE = "Watchdog"
PK = "HK"

_clients = {}


def client(name):
    if name not in _clients:
        _clients[name] = boto3.client(name)
    return _clients[name]


def log(level, message, **fields):
    print(json.dumps({"level": level, "message": message, **fields}, default=str))


def put_metric(name):
    client("cloudwatch").put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[{"MetricName": name, "Value": 1, "Unit": "Count"}],
    )


def pages(service, operation, key, **params):
    paginator = client(service).get_paginator(operation)
    return [item for page in paginator.paginate(**params) for item in page[key]]


def collect():
    reservations = pages("ec2", "describe_instances", "Reservations")
    return {
        "instances": [i for r in reservations for i in r["Instances"]],
        "volumes": pages("ec2", "describe_volumes", "Volumes"),
        "snapshots": pages("ec2", "describe_snapshots", "Snapshots", OwnerIds=["self"]),
        "addresses": client("ec2").describe_addresses()["Addresses"],
        "vpcs": pages("ec2", "describe_vpcs", "Vpcs"),
        "subnets": pages("ec2", "describe_subnets", "Subnets"),
        "groups": pages("ec2", "describe_security_groups", "SecurityGroups"),
        "tagged": pages("resourcegroupstaggingapi", "get_resources", "ResourceTagMappingList"),
    }


def analyse(data, now, region):
    inventory = ec2_inventory(
        data["instances"], data["volumes"], data["snapshots"], data["addresses"],
        data["vpcs"], data["subnets"], data["groups"],
    )
    skip = default_vpc_ids(data["vpcs"])
    findings = {
        "unattached_volumes": find_unattached_volumes(data["volumes"]),
        "stopped_instances": find_stopped_instances(data["instances"]),
        "idle_addresses": find_idle_addresses(data["addresses"]),
        "old_snapshots": find_old_snapshots(data["snapshots"], now, SNAPSHOT_MAX_AGE_DAYS),
        "untagged": find_untagged(inventory, data["tagged"], REQUIRED_TAGS, skip),
    }
    return build_report(now, findings, REQUIRED_TAGS, skipped_defaults(inventory, skip), region)


def store(report):
    """One item per run date. Running twice on the same day keeps the
    latest result, which is what a manual re-run should do."""
    item = {
        "pk": {"S": PK},
        "sk": {"S": report["run_date"]},
        "run_at": {"S": report["run_at"]},
        "region": {"S": report["region"]},
        "total": {"N": str(report["total"])},
        "required_tags": {"S": ",".join(report["required_tags"])},
        "skipped_defaults": {"N": str(report["skipped_defaults"])},
        "findings": {"S": to_json(report["findings"])},
    }
    for key, count in report["counts"].items():
        item[f"count_{key}"] = {"N": str(count)}
    client("dynamodb").put_item(TableName=TABLE_NAME, Item=item)


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


def run(now):
    region = client("ec2").meta.region_name
    report = analyse(collect(), now, region)
    store(report)
    subject, body = format_email(report)
    send_report(subject, body)
    put_metric("HousekeepingSuccess")
    log("INFO", "housekeeping report sent", total=report["total"], counts=report["counts"])
    return {"total": report["total"], "counts": report["counts"]}


def lambda_handler(event, context):
    try:
        return run(datetime.now(timezone.utc))
    except Exception as error:
        log("ERROR", "housekeeping failed", error=repr(error))
        try:
            put_metric("HousekeepingFailure")
        except Exception as metric_error:
            log("ERROR", "could not publish failure metric", error=repr(metric_error))
        raise
