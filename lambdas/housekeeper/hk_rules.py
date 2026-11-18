"""Rules for the weekly housekeeping report.

No AWS calls in this file, only plain data in and plain data out, so every
rule can be tested without an account. housekeeper.py does the calls.
"""

import json
from datetime import datetime, timedelta, timezone

SAST = timezone(timedelta(hours=2))

# EC2 types the handler reads directly with Describe calls. Their entries
# in the tagging API are skipped so nothing is counted twice.
DESCRIBED_EC2_TYPES = {"instance", "volume", "snapshot", "elastic-ip", "vpc", "subnet", "security-group"}

# Order, heading, why it matters and what to do, for each kind of finding.
CATEGORIES = [
    (
        "unattached_volumes",
        "Unattached disks",
        "A disk attached to nothing is billed every hour and serves nothing.",
        "Snapshot it if the data matters, then delete it.",
    ),
    (
        "stopped_instances",
        "Stopped servers",
        "A stopped server still pays for its disks every hour.",
        "Start it if it is needed. If not, snapshot it and terminate it.",
    ),
    (
        "idle_addresses",
        "Idle public IPs",
        "A public IP address attached to nothing is charged every hour.",
        "Release it.",
    ),
    (
        "old_snapshots",
        "Old snapshots",
        "Old disk backups are billed every month and are easy to forget.",
        "Delete the ones nobody needs.",
    ),
    (
        "untagged",
        "Missing tags",
        "Nobody can tell who owns these or whether they are still needed.",
        "Add the missing tags, or delete the resource if nobody claims it.",
    ),
]


def parse_list(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def tag_map(tags):
    return {t["Key"]: t["Value"] for t in (tags or [])}


def missing_tags(tags, required):
    present = tag_map(tags)
    return [key for key in required if not present.get(key)]


def day(value):
    """A date as YYYY-MM-DD, from a datetime or an ISO string."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def as_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def ec2_inventory(instances, volumes, snapshots, addresses, vpcs, subnets, groups):
    """One flat list of the EC2 resources the handler read, with their tags.

    aws_default marks the pieces AWS creates by itself in every region and
    VPC: the default VPC, its default subnets and each VPC's security group
    named "default". Those are skipped by the tag check. Anything a person
    made inside the default VPC is still checked (Game Day finding: a rule
    that skipped the whole default VPC hid two hand-made security groups)."""
    rows = []

    def add(rid, kind, tags, aws_default=False):
        rows.append({"id": rid, "type": kind, "tags": tags, "aws_default": aws_default})

    for i in instances:
        if i.get("State", {}).get("Name") in ("terminated", "shutting-down"):
            continue
        add(i["InstanceId"], "instance", i.get("Tags"))
    for v in volumes:
        add(v["VolumeId"], "volume", v.get("Tags"))
    for s in snapshots:
        add(s["SnapshotId"], "snapshot", s.get("Tags"))
    for a in addresses:
        add(a.get("AllocationId") or a.get("PublicIp"), "elastic-ip", a.get("Tags"))
    for v in vpcs:
        add(v["VpcId"], "vpc", v.get("Tags"), bool(v.get("IsDefault")))
    for s in subnets:
        add(s["SubnetId"], "subnet", s.get("Tags"), bool(s.get("DefaultForAz")))
    for g in groups:
        add(g["GroupId"], "security-group", g.get("Tags"), g.get("GroupName") == "default")
    return rows


def arn_parts(arn):
    parts = arn.split(":", 5)
    service = parts[2] if len(parts) > 2 else ""
    resource = parts[5] if len(parts) > 5 else ""
    return service, resource


def arn_kind(arn):
    """A short label for a resource ARN, e.g. 'lambda function' or 's3'."""
    service, resource = arn_parts(arn)
    cuts = [i for i in (resource.find("/"), resource.find(":")) if i >= 0]
    if cuts:
        return f"{service} {resource[:min(cuts)]}"
    return service


def arn_name(arn):
    _, resource = arn_parts(arn)
    return resource or arn


def is_described_ec2(arn):
    service, resource = arn_parts(arn)
    return service == "ec2" and resource.split("/", 1)[0] in DESCRIBED_EC2_TYPES


def find_untagged(inventory, tagged_resources, required):
    """Resources missing any required tag key.

    EC2 resources come from the Describe calls, so even ones never tagged
    are seen. Everything else comes from the tagging API, which only lists
    resources that have (or once had) a tag. Never-tagged non-EC2
    resources are a known blind spot, recorded in D-021."""
    rows = []
    for r in inventory:
        if r["aws_default"]:
            continue
        miss = missing_tags(r["tags"], required)
        if miss:
            rows.append({"id": r["id"], "type": r["type"], "detail": "missing " + ", ".join(miss)})
    for res in tagged_resources:
        arn = res["ResourceARN"]
        if is_described_ec2(arn):
            continue
        miss = missing_tags(res.get("Tags"), required)
        if miss:
            rows.append({"id": arn_name(arn), "type": arn_kind(arn), "detail": "missing " + ", ".join(miss)})
    return sorted(rows, key=lambda row: (row["type"], row["id"]))


def skipped_defaults(inventory):
    return sum(1 for r in inventory if r["aws_default"])


def find_stopped_instances(instances):
    rows = []
    for i in instances:
        if i.get("State", {}).get("Name") == "stopped":
            reason = i.get("StateTransitionReason") or ""
            detail = i.get("InstanceType", "")
            if reason:
                detail = f"{detail}, {reason}"
            rows.append({"id": i["InstanceId"], "type": "instance", "detail": detail})
    return rows


def find_unattached_volumes(volumes):
    return [
        {
            "id": v["VolumeId"],
            "type": "volume",
            "detail": f"{v.get('Size')} GiB {v.get('VolumeType', '')}, created {day(v.get('CreateTime'))}",
        }
        for v in volumes
        if v.get("State") == "available"
    ]


def find_old_snapshots(snapshots, now, max_age_days):
    rows = []
    for s in snapshots:
        age = (now - as_datetime(s["StartTime"])).days
        if age > max_age_days:
            rows.append({
                "id": s["SnapshotId"],
                "type": "snapshot",
                "detail": f"{s.get('VolumeSize')} GiB, taken {day(s['StartTime'])}, {age} days old",
            })
    return rows


def find_idle_addresses(addresses):
    return [
        {"id": a.get("AllocationId") or a.get("PublicIp"), "type": "elastic-ip", "detail": a.get("PublicIp", "")}
        for a in addresses
        if not a.get("AssociationId")
    ]


def build_report(now, findings, required, skipped, region):
    counts = {key: len(findings.get(key, [])) for key, *_ in CATEGORIES}
    return {
        "run_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "run_date": now.astimezone(SAST).strftime("%Y-%m-%d"),
        "run_local": now.astimezone(SAST).strftime("%Y-%m-%d %H:%M SAST"),
        "region": region,
        "required_tags": list(required),
        "skipped_defaults": skipped,
        "counts": counts,
        "total": sum(counts.values()),
        "findings": {key: findings.get(key, []) for key, *_ in CATEGORIES},
    }


def subject_line(report):
    total = report["total"]
    if total == 0:
        return "Watchdog housekeeping: all clear"
    return f"Watchdog housekeeping: {total} finding{'s' if total != 1 else ''}"


def format_email(report):
    lines = [
        "Weekly housekeeping report",
        "",
        f"Run:     {report['run_local']}",
        f"Region:  {report['region']}",
        "",
        "Summary",
    ]
    for key, heading, *_ in CATEGORIES:
        lines.append(f"  {heading:<18} {report['counts'][key]}")
    lines.append("")

    if report["total"] == 0:
        lines.append("Nothing found. Every resource checked is tagged and in use.")
        lines.append("")

    for key, heading, why, action in CATEGORIES:
        rows = report["findings"][key]
        if not rows:
            continue
        lines.append(f"{heading} ({len(rows)})")
        for row in rows:
            lines.append(f"  {row['id']}  ({row['type']})  {row['detail']}")
        lines.append(f"  Why it matters: {why}")
        lines.append(f"  What to do: {action}")
        lines.append("")

    lines.append(f"Tags checked: {', '.join(report['required_tags'])}.")
    if report["skipped_defaults"]:
        lines.append(
            f"Skipped {report['skipped_defaults']} resources AWS creates by itself "
            "(default VPC, default subnets, default security groups)."
        )
    lines.append("This report only looks. It never stops, deletes or changes anything.")
    return subject_line(report), "\n".join(lines) + "\n"


def to_json(value):
    return json.dumps(value, sort_keys=True, default=str)
