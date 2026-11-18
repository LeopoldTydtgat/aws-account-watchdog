"""Housekeeping rules on plain data. No AWS, no credentials."""

from datetime import datetime, timezone

import hk_rules as r

NOW = datetime(2026, 11, 23, 4, 30, tzinfo=timezone.utc)
REQUIRED = ["project", "owner"]
GOOD_TAGS = [{"Key": "project", "Value": "watchdog"}, {"Key": "owner", "Value": "leopold"}]


def test_missing_tags_lists_absent_and_empty_keys():
    assert r.missing_tags(None, REQUIRED) == ["project", "owner"]
    assert r.missing_tags([{"Key": "project", "Value": ""}], REQUIRED) == ["project", "owner"]
    assert r.missing_tags(GOOD_TAGS, REQUIRED) == []


def test_parse_list_trims_and_drops_blanks():
    assert r.parse_list(" project, owner ,,") == ["project", "owner"]


def test_unattached_volume_is_flagged_and_attached_is_not():
    volumes = [
        {"VolumeId": "vol-loose", "State": "available", "Size": 1, "VolumeType": "gp3",
         "CreateTime": datetime(2026, 11, 18, tzinfo=timezone.utc)},
        {"VolumeId": "vol-used", "State": "in-use", "Size": 8, "VolumeType": "gp3",
         "CreateTime": datetime(2026, 11, 1, tzinfo=timezone.utc)},
    ]
    rows = r.find_unattached_volumes(volumes)
    assert [row["id"] for row in rows] == ["vol-loose"]
    assert rows[0]["detail"] == "1 GiB gp3, created 2026-11-18"


def test_only_stopped_instances_are_flagged():
    instances = [
        {"InstanceId": "i-stop", "State": {"Name": "stopped"}, "InstanceType": "t4g.nano",
         "StateTransitionReason": "User initiated (2026-11-20 10:00:00 GMT)"},
        {"InstanceId": "i-run", "State": {"Name": "running"}, "InstanceType": "t4g.nano"},
    ]
    rows = r.find_stopped_instances(instances)
    assert [row["id"] for row in rows] == ["i-stop"]
    assert "User initiated" in rows[0]["detail"]


def test_snapshot_older_than_limit_is_flagged():
    snaps = [
        {"SnapshotId": "snap-old", "StartTime": datetime(2026, 10, 1, tzinfo=timezone.utc), "VolumeSize": 1},
        {"SnapshotId": "snap-new", "StartTime": datetime(2026, 11, 20, tzinfo=timezone.utc), "VolumeSize": 1},
        {"SnapshotId": "snap-edge", "StartTime": datetime(2026, 10, 24, 4, 30, tzinfo=timezone.utc), "VolumeSize": 1},
    ]
    rows = r.find_old_snapshots(snaps, NOW, 30)
    assert [row["id"] for row in rows] == ["snap-old"]
    assert "53 days old" in rows[0]["detail"]


def test_idle_address_is_flagged_and_associated_is_not():
    addresses = [
        {"AllocationId": "eipalloc-idle", "PublicIp": "203.0.113.10"},
        {"AllocationId": "eipalloc-used", "PublicIp": "203.0.113.11", "AssociationId": "eipassoc-1"},
    ]
    assert [row["id"] for row in r.find_idle_addresses(addresses)] == ["eipalloc-idle"]


def test_untagged_skips_default_vpc_and_dedupes_ec2_from_tagging_api():
    vpcs = [
        {"VpcId": "vpc-default", "IsDefault": True},
        {"VpcId": "vpc-range", "IsDefault": False, "Tags": GOOD_TAGS},
    ]
    subnets = [
        {"SubnetId": "subnet-default", "VpcId": "vpc-default"},
        {"SubnetId": "subnet-range", "VpcId": "vpc-range", "Tags": GOOD_TAGS},
    ]
    groups = [
        {"GroupId": "sg-default", "VpcId": "vpc-default"},
        {"GroupId": "sg-handmade", "VpcId": "vpc-range", "Tags": [{"Key": "project", "Value": "x"}]},
    ]
    volumes = [{"VolumeId": "vol-1", "State": "available"}]
    inventory = r.ec2_inventory([], volumes, [], [], vpcs, subnets, groups)
    tagged = [
        # EC2 types already read by Describe: must not be counted again.
        {"ResourceARN": "arn:aws:ec2:eu-north-1:111122223333:security-group/sg-handmade",
         "Tags": [{"Key": "project", "Value": "x"}]},
        # Non-EC2 resource that lost its owner tag.
        {"ResourceARN": "arn:aws:lambda:eu-north-1:111122223333:function:handmade",
         "Tags": [{"Key": "project", "Value": "x"}]},
        # Fully tagged: not reported.
        {"ResourceARN": "arn:aws:s3:::watchdog-config-111122223333", "Tags": GOOD_TAGS},
    ]
    skip = r.default_vpc_ids(vpcs)
    rows = r.find_untagged(inventory, tagged, REQUIRED, skip)

    assert [(row["type"], row["id"]) for row in rows] == [
        ("lambda function", "function:handmade"),
        ("security-group", "sg-handmade"),
        ("volume", "vol-1"),
    ]
    assert rows[1]["detail"] == "missing owner"
    assert r.skipped_defaults(inventory, skip) == 3


def test_terminated_instances_are_ignored():
    instances = [{"InstanceId": "i-gone", "State": {"Name": "terminated"}}]
    assert r.ec2_inventory(instances, [], [], [], [], [], []) == []


def test_arn_helpers():
    assert r.arn_kind("arn:aws:s3:::bucket") == "s3"
    assert r.arn_kind("arn:aws:sqs:eu-north-1:1:queue") == "sqs"
    assert r.arn_kind("arn:aws:logs:eu-north-1:1:log-group:/aws/lambda/x") == "logs log-group"
    assert r.is_described_ec2("arn:aws:ec2:eu-north-1:1:volume/vol-1")
    assert not r.is_described_ec2("arn:aws:ec2:eu-north-1:1:route-table/rtb-1")


def empty_findings():
    return {key: [] for key, *_ in r.CATEGORIES}


def test_all_clear_email():
    report = r.build_report(NOW, empty_findings(), REQUIRED, 3, "eu-north-1")
    subject, body = r.format_email(report)
    assert subject == "Watchdog housekeeping: all clear"
    assert "Nothing found." in body
    assert "Run:     2026-11-23 06:30 SAST" in body
    assert "Skipped 3 resources in the default VPC" in body
    assert "never stops, deletes or changes anything" in body
    assert report["run_date"] == "2026-11-23"


def test_findings_email_has_counts_reasons_and_actions():
    findings = empty_findings()
    findings["unattached_volumes"] = [{"id": "vol-1", "type": "volume", "detail": "1 GiB gp3, created 2026-11-18"}]
    findings["untagged"] = [{"id": "vol-1", "type": "volume", "detail": "missing project, owner"}]
    report = r.build_report(NOW, findings, REQUIRED, 0, "eu-north-1")
    subject, body = r.format_email(report)

    assert subject == "Watchdog housekeeping: 2 findings"
    assert report["counts"]["unattached_volumes"] == 1
    assert "Unattached disks (1)" in body
    assert "vol-1  (volume)  1 GiB gp3, created 2026-11-18" in body
    assert "Why it matters: A disk attached to nothing is billed every hour" in body
    assert "What to do: Snapshot it if the data matters, then delete it." in body
    assert "Skipped" not in body


def test_single_finding_subject_is_singular():
    findings = empty_findings()
    findings["idle_addresses"] = [{"id": "eipalloc-1", "type": "elastic-ip", "detail": "203.0.113.10"}]
    subject, _ = r.format_email(r.build_report(NOW, findings, REQUIRED, 0, "eu-north-1"))
    assert subject == "Watchdog housekeeping: 1 finding"
