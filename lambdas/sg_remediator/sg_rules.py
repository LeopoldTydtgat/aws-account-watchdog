"""Decisions for the security-group remediator.

No AWS calls in this file, so every rule here is unit tested without
credentials. remediator.py does the talking to AWS.
"""

import json
from datetime import datetime

OPEN_V4 = "0.0.0.0/0"
OPEN_V6 = "::/0"
EXCLUDE_TAG = "watchdog:exclude"

NO_ACTION = "NO_ACTION"
ALERT_ONLY = "ALERT_ONLY"
WOULD_REVOKE = "WOULD_REVOKE"
REVOKE = "REVOKE"


def parse_ports(text):
    """'22,3389' -> [22, 3389]."""
    return sorted({int(part) for part in text.split(",") if part.strip()})


def covered_ports(permission, ports):
    """Which of the blocked ports one inbound rule lets through.
    Protocol -1 means all traffic, so it covers every port."""
    protocol = str(permission.get("IpProtocol"))
    if protocol == "-1":
        return list(ports)
    if protocol not in ("tcp", "6"):
        return []
    low = permission.get("FromPort", -1)
    high = permission.get("ToPort", -1)
    return [port for port in ports if low <= port <= high]


def find_exposures(group, ports):
    """Every inbound rule open to the whole internet on a blocked port."""
    exposures = []
    for permission in group.get("IpPermissions", []):
        hit = covered_ports(permission, ports)
        if not hit:
            continue
        open_cidrs = [r["CidrIp"] for r in permission.get("IpRanges", []) if r.get("CidrIp") == OPEN_V4]
        open_cidrs += [r["CidrIpv6"] for r in permission.get("Ipv6Ranges", []) if r.get("CidrIpv6") == OPEN_V6]
        for cidr in open_cidrs:
            exposure = {"protocol": str(permission["IpProtocol"]), "cidr": cidr, "ports": hit}
            if "FromPort" in permission:
                exposure["from_port"] = permission["FromPort"]
                exposure["to_port"] = permission["ToPort"]
            exposures.append(exposure)
    return exposures


def revoke_payload(exposures):
    """The IpPermissions to remove exactly the exposed rules and nothing else.
    Used in stage 2 only; stage 1 has no permission to revoke."""
    payload = []
    for exposure in exposures:
        permission = {"IpProtocol": exposure["protocol"]}
        if "from_port" in exposure:
            permission["FromPort"] = exposure["from_port"]
            permission["ToPort"] = exposure["to_port"]
        if exposure["cidr"] == OPEN_V6:
            permission["Ipv6Ranges"] = [{"CidrIpv6": OPEN_V6}]
        else:
            permission["IpRanges"] = [{"CidrIp": OPEN_V4}]
        payload.append(permission)
    return payload


def is_excluded(group):
    """Allow-list: a group tagged watchdog:exclude=true is open on purpose."""
    for tag in group.get("Tags", []):
        if tag.get("Key") == EXCLUDE_TAG and str(tag.get("Value", "")).strip().lower() == "true":
            return True
    return False


def decide_action(exposures, excluded, dry_run):
    if not exposures:
        return NO_ACTION
    if excluded:
        return ALERT_ONLY
    if dry_run:
        return WOULD_REVOKE
    return REVOKE


def parse_time(text):
    """Config timestamps end in Z, which fromisoformat only accepts from 3.11."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def describe_exposure(exposure):
    protocol = "all traffic" if exposure["protocol"] == "-1" else exposure["protocol"]
    if "from_port" in exposure and exposure["from_port"] != exposure["to_port"]:
        span = f"ports {exposure['from_port']}-{exposure['to_port']}"
    elif "from_port" in exposure:
        span = f"port {exposure['from_port']}"
    else:
        span = "all ports"
    return f"{protocol} {span} from {exposure['cidr']}"


def port_label(exposures):
    if any(e["protocol"] == "-1" for e in exposures):
        return "all ports"
    ports = sorted({port for e in exposures for port in e["ports"]})
    label = ", ".join(str(port) for port in ports)
    return f"port {label}" if len(ports) == 1 else f"ports {label}"


ACTION_LINES = {
    WOULD_REVOKE: "Action: WOULD REVOKE the rules above. Nothing was changed (dry run).",
    ALERT_ONLY: f"Action: ALERT ONLY. The group is tagged {EXCLUDE_TAG}=true, so it was left as is.",
    REVOKE: "Action: REVOKED the rules above.",
}

SUBJECT_WORDS = {
    WOULD_REVOKE: "WOULD REVOKE",
    ALERT_ONLY: "ALERT ONLY (excluded)",
    REVOKE: "REVOKED",
}


def format_email(incident):
    name = incident.get("sg_name") or "unnamed"
    subject = (
        f"[Watchdog] {SUBJECT_WORDS[incident['action']]}: {incident['sg_id']} ({name}) "
        f"{port_label(incident['before'])} open to the internet"
    )
    lines = [
        "Security group open to the internet",
        "",
        f"Group:     {incident['sg_id']} ({name})",
        f"VPC:       {incident.get('vpc_id') or 'unknown'}",
        f"Rule:      {incident['rule']}",
        f"Detected:  {incident['detected_at']} (Config evaluation)",
        f"Mode:      {incident['mode']}",
        "",
        "Open to the internet:",
    ]
    lines += [f"  {describe_exposure(e)}" for e in incident["before"]]
    lines += ["", ACTION_LINES[incident["action"]]]
    if incident["action"] == WOULD_REVOKE:
        lines.append(f"If this is on purpose, tag the group {EXCLUDE_TAG}=true.")
    if incident["action"] == REVOKE:
        remaining = incident.get("after") or []
        lines.append("Still open after revoke: " + (", ".join(describe_exposure(e) for e in remaining) or "nothing"))
    lines += ["", f"Incident: INC {incident['sk']}"]
    return subject, "\n".join(lines) + "\n"


def to_json(value):
    return json.dumps(value, sort_keys=True)
