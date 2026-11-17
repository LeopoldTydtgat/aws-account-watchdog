from sg_rules import (
    ALERT_ONLY,
    NO_ACTION,
    REVOKE,
    WOULD_REVOKE,
    decide_action,
    find_exposures,
    format_email,
    is_excluded,
    parse_ports,
    revoke_payload,
)

PORTS = [22, 3389]


def group(*permissions, tags=None):
    return {"GroupId": "sg-1", "GroupName": "range-admin", "IpPermissions": list(permissions), "Tags": tags or []}


def tcp(low, high, v4=(), v6=()):
    return {
        "IpProtocol": "tcp", "FromPort": low, "ToPort": high,
        "IpRanges": [{"CidrIp": c} for c in v4],
        "Ipv6Ranges": [{"CidrIpv6": c} for c in v6],
    }


def test_parse_ports():
    assert parse_ports("3389, 22,22") == [22, 3389]


def test_ssh_open_to_world_is_exposed():
    exposures = find_exposures(group(tcp(22, 22, v4=["0.0.0.0/0"])), PORTS)
    assert exposures == [{"protocol": "tcp", "cidr": "0.0.0.0/0", "ports": [22], "from_port": 22, "to_port": 22}]


def test_ssh_from_vpc_only_is_fine():
    assert find_exposures(group(tcp(22, 22, v4=["10.20.0.0/16"])), PORTS) == []


def test_https_open_to_world_is_fine():
    assert find_exposures(group(tcp(443, 443, v4=["0.0.0.0/0"])), PORTS) == []


def test_wide_range_covering_both_ports():
    exposures = find_exposures(group(tcp(0, 65535, v4=["0.0.0.0/0"])), PORTS)
    assert exposures[0]["ports"] == [22, 3389]


def test_ipv6_world_is_exposed():
    exposures = find_exposures(group(tcp(3389, 3389, v6=["::/0"])), PORTS)
    assert exposures[0]["cidr"] == "::/0"


def test_all_traffic_rule_is_exposed():
    rule = {"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}], "Ipv6Ranges": []}
    exposures = find_exposures(group(rule), PORTS)
    assert exposures == [{"protocol": "-1", "cidr": "0.0.0.0/0", "ports": [22, 3389]}]


def test_udp_on_port_22_is_not_this_rule():
    rule = {"IpProtocol": "udp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
    assert find_exposures(group(rule), PORTS) == []


def test_mixed_rule_only_world_cidr_is_reported():
    exposures = find_exposures(group(tcp(22, 22, v4=["10.20.0.0/16", "0.0.0.0/0"])), PORTS)
    assert [e["cidr"] for e in exposures] == ["0.0.0.0/0"]


def test_revoke_payload_removes_only_the_exposed_cidrs():
    exposures = find_exposures(group(tcp(22, 22, v4=["10.20.0.0/16", "0.0.0.0/0"], v6=["::/0"])), PORTS)
    assert revoke_payload(exposures) == [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "Ipv6Ranges": [{"CidrIpv6": "::/0"}]},
    ]


def test_exclude_tag_is_case_insensitive():
    assert is_excluded(group(tags=[{"Key": "watchdog:exclude", "Value": "True"}]))
    assert not is_excluded(group(tags=[{"Key": "watchdog:exclude", "Value": "no"}]))
    assert not is_excluded(group())


def test_decide_action():
    exposed = [{"protocol": "tcp"}]
    assert decide_action([], False, True) == NO_ACTION
    assert decide_action(exposed, True, False) == ALERT_ONLY
    assert decide_action(exposed, False, True) == WOULD_REVOKE
    assert decide_action(exposed, False, False) == REVOKE


def incident(action, before, after=None):
    return {
        "sk": "2026-11-17T13:00:00.000Z#sg-1", "sg_id": "sg-1", "sg_name": "range-admin",
        "vpc_id": "vpc-1", "rule": "watchdog-restricted-admin-ports", "mode": "DRY RUN",
        "action": action, "detected_at": "2026-11-17T13:00:00.000Z",
        "before": before, "after": before if after is None else after,
    }


def test_dry_run_email():
    before = find_exposures(group(tcp(22, 22, v4=["0.0.0.0/0"])), PORTS)
    subject, body = format_email(incident(WOULD_REVOKE, before))
    assert subject == "[Watchdog] WOULD REVOKE: sg-1 (range-admin) port 22 open to the internet"
    assert "  tcp port 22 from 0.0.0.0/0" in body
    assert "Nothing was changed (dry run)." in body
    assert "tag the group watchdog:exclude=true" in body


def test_alert_only_email():
    before = find_exposures(group(tcp(3389, 3389, v4=["0.0.0.0/0"])), PORTS)
    subject, body = format_email(incident(ALERT_ONLY, before))
    assert subject.startswith("[Watchdog] ALERT ONLY (excluded): ")
    assert "left as is" in body


def test_revoke_email_reports_what_is_left():
    before = find_exposures(group(tcp(0, 65535, v4=["0.0.0.0/0"])), PORTS)
    subject, body = format_email(incident(REVOKE, before, after=[]))
    assert "ports 22, 3389 open to the internet" in subject
    assert "tcp ports 0-65535 from 0.0.0.0/0" in body
    assert "Still open after revoke: nothing" in body
