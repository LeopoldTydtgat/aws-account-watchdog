"""Runs the housekeeper end to end against stubbed AWS clients. No network,
no credentials: every call is checked against what the code should send,
and a call the code should not make fails the test."""

from datetime import datetime, timezone

import boto3
import pytest
from botocore.stub import ANY, Stubber

import housekeeper

NOW = datetime(2026, 11, 23, 4, 30, tzinfo=timezone.utc)
SERVICES = ("ec2", "resourcegroupstaggingapi", "dynamodb", "ssm", "ses", "cloudwatch")


@pytest.fixture
def stubs(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-north-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    made = {}
    for name in SERVICES:
        c = boto3.client(name, region_name="eu-north-1")
        made[name] = Stubber(c)
        housekeeper._clients[name] = c
    for s in made.values():
        s.activate()
    yield made
    for s in made.values():
        s.assert_no_pending_responses()
        s.deactivate()
    housekeeper._clients.clear()


def stub_inventory(stubs, volumes):
    ec2 = stubs["ec2"]
    ec2.add_response("describe_instances", {"Reservations": []}, {})
    ec2.add_response("describe_volumes", {"Volumes": volumes}, {})
    ec2.add_response("describe_snapshots", {"Snapshots": []}, {"OwnerIds": ["self"]})
    ec2.add_response("describe_addresses", {"Addresses": []}, {})
    ec2.add_response("describe_vpcs", {"Vpcs": [{"VpcId": "vpc-default", "IsDefault": True}]}, {})
    ec2.add_response("describe_subnets", {"Subnets": [{"SubnetId": "subnet-d", "VpcId": "vpc-default"}]}, {})
    ec2.add_response("describe_security_groups", {"SecurityGroups": [
        {"GroupId": "sg-d", "GroupName": "default", "VpcId": "vpc-default", "OwnerId": "1", "Description": "d"}
    ]}, {})
    stubs["resourcegroupstaggingapi"].add_response("get_resources", {"ResourceTagMappingList": []}, {})


def stub_outputs(stubs, subject):
    stubs["dynamodb"].add_response("put_item", {}, {
        "TableName": "watchdog-data",
        "Item": ANY,
    })
    stubs["ssm"].add_response(
        "get_parameter",
        {"Parameter": {"Name": "/watchdog/report-email", "Value": "me@example.com"}},
        {"Name": "/watchdog/report-email"},
    )
    stubs["ses"].add_response("send_email", {"MessageId": "m-1"}, {
        "Source": "me@example.com",
        "Destination": {"ToAddresses": ["me@example.com"]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": ANY, "Charset": "UTF-8"}},
        },
    })
    stubs["cloudwatch"].add_response("put_metric_data", {}, {
        "Namespace": "Watchdog",
        "MetricData": [{"MetricName": "HousekeepingSuccess", "Value": 1, "Unit": "Count"}],
    })


def test_clean_account_sends_all_clear(stubs):
    stub_inventory(stubs, volumes=[])
    stub_outputs(stubs, "Watchdog housekeeping: all clear")
    result = housekeeper.run(NOW)
    assert result["total"] == 0


def test_loose_untagged_disk_is_reported_twice(stubs):
    loose = {"VolumeId": "vol-1", "State": "available", "Size": 1, "VolumeType": "gp3",
             "CreateTime": datetime(2026, 11, 18, tzinfo=timezone.utc)}
    stub_inventory(stubs, volumes=[loose])
    stub_outputs(stubs, "Watchdog housekeeping: 2 findings")
    result = housekeeper.run(NOW)
    assert result["counts"]["unattached_volumes"] == 1
    assert result["counts"]["untagged"] == 1


def test_stored_item_uses_hk_partition_and_run_date(stubs):
    stub_inventory(stubs, volumes=[])
    stubs["dynamodb"].add_response("put_item", {}, {
        "TableName": "watchdog-data",
        "Item": {
            "pk": {"S": "HK"},
            "sk": {"S": "2026-11-23"},
            "run_at": {"S": "2026-11-23T04:30:00+00:00"},
            "region": {"S": "eu-north-1"},
            "total": {"N": "0"},
            "required_tags": {"S": "project,owner"},
            "skipped_defaults": {"N": "3"},
            "findings": ANY,
            "count_unattached_volumes": {"N": "0"},
            "count_stopped_instances": {"N": "0"},
            "count_idle_addresses": {"N": "0"},
            "count_old_snapshots": {"N": "0"},
            "count_untagged": {"N": "0"},
        },
    })
    stubs["ssm"].add_response("get_parameter",
                              {"Parameter": {"Name": "/watchdog/report-email", "Value": "me@example.com"}},
                              {"Name": "/watchdog/report-email"})
    stubs["ses"].add_response("send_email", {"MessageId": "m-1"}, None)
    stubs["cloudwatch"].add_response("put_metric_data", {}, None)
    housekeeper.run(NOW)


def test_failure_publishes_failure_metric_and_raises(stubs):
    stubs["ec2"].add_client_error("describe_instances", "UnauthorizedOperation")
    stubs["cloudwatch"].add_response("put_metric_data", {}, {
        "Namespace": "Watchdog",
        "MetricData": [{"MetricName": "HousekeepingFailure", "Value": 1, "Unit": "Count"}],
    })
    with pytest.raises(Exception):
        housekeeper.lambda_handler({}, None)
