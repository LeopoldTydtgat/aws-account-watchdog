# Game Day 01: Exposed SSH

| | |
|---|---|
| Date | 2026-11-17 |
| Type | Controlled drill (game day), change made by me on the test range |
| Target | `watchdog-range-admin` (sg-0d9ce1febc31da95f) in the test range VPC (vpc-0cbd5431e3edaa393). No instances, nothing reachable behind it |
| Mode | Remediator in DRY_RUN (stage 1) |
| Result | Detected and alerted 2 min 42 s after the change. Nothing was changed by the Watchdog, as designed |
| Related | D-019, D-020, PR #17, PR #18, PR #19 |

Times are SAST (UTC+2). AWS records UTC.

## Scenario

Someone opens SSH (TCP 22) on a security group to the whole internet, 0.0.0.0/0. This is the classic mistake behind brute-force attacks on cloud servers: bots scan the whole IPv4 range for open 22 within minutes.

Goal: prove the chain change, detect, alert works end to end, and measure each link.

## Steps

1. `aws ec2 authorize-security-group-ingress --group-id sg-0d9ce1febc31da95f --protocol tcp --port 22 --cidr 0.0.0.0/0` (rule sgr-0484a487258cdaefb)
2. Waited for the alert email
3. Read the function log: `aws logs tail /aws/lambda/watchdog-sg-remediator --since 30m`
4. Closed the rule by hand: `aws ec2 revoke-security-group-ingress` with the same arguments
5. Confirmed the Config rule returned to COMPLIANT: `aws configservice describe-compliance-by-config-rule`

## Timeline

| Time (SAST) | Event | Since change |
|---|---|---|
| 18:26:13 | Port 22 opened to 0.0.0.0/0 | 0 |
| 18:28:43.6 | Config evaluation recorded: NON_COMPLIANT | 2 min 30 s |
| 18:28:49.9 | Function started (first ever run, cold start) | 2 min 37 s |
| 18:28:55.0 | Incident logged and WOULD REVOKE email sent | 2 min 42 s |
| 18:34:23 | Rule revoked by hand | 8 min 10 s |
| 18:34 (approx.) | Config still NON_COMPLIANT, re-evaluation pending | |
| 18:39 | Config rule back to COMPLIANT | |

The inbox arrival time was not recorded. The send time comes from the function log.

## What the Watchdog produced

Email (plain text, from the verified SES identity):

```
Security group open to the internet

Group:     sg-0d9ce1febc31da95f (watchdog-range-admin)
VPC:       vpc-0cbd5431e3edaa393
Rule:      watchdog-restricted-admin-ports
Detected:  2026-11-17T16:28:43.637Z (Config evaluation)
Mode:      DRY RUN

Open to the internet:
  tcp port 22 from 0.0.0.0/0

Action: WOULD REVOKE the rules above. Nothing was changed (dry run).
If this is on purpose, tag the group watchdog:exclude=true.

Incident: INC 2026-11-17T16:28:43.637Z#sg-0d9ce1febc31da95f
```

Function log, summary line:

```
{"level": "INFO", "message": "sg remediation handled", "action": "WOULD_REVOKE",
 "sk": "2026-11-17T16:28:43.637Z#sg-0d9ce1febc31da95f", "sg_id": "sg-0d9ce1febc31da95f",
 "latency_seconds": 6.5}
REPORT Duration: 4870.30 ms  Billed Duration: 5134 ms  Memory Size: 128 MB
       Max Memory Used: 111 MB  Init Duration: 263.23 ms
```

## Findings

1. **The chain works end to end.** Change to alert in 2 min 42 s, well inside the 10-minute target for sensitive security groups.
2. **Config is the slow link.** 2 min 30 s of the 2 min 42 s was Config recording the change and evaluating the rule. Everything after the verdict (EventBridge delivery, cold start, the function's work) took 11.4 s.
3. **Memory is tight.** 111 MB used of 128 MB (87%). In Lambda, CPU scales with memory, so 128 MB also makes the cold start slow: 4.9 s of run time for a few API calls.
4. **Dry run means the door stays open until a human closes it.** It was open 8 min 10 s, all of it after the alert. In stage 2 the remediator would revoke within seconds of the verdict, so exposure would be roughly the detection time.
5. **Recovery is silent by design.** Config returned to COMPLIANT within 5 minutes of the revoke. No email is sent for that, because the EventBridge rule only forwards NON_COMPLIANT.
6. **The IAM-change alarm caught the remediator's own role being created** during the deploy (PutRolePolicy by the pipeline role through GitHub OIDC). Expected and benign, and proof the alarm covers new roles.

## Follow-up

- [ ] Raise remediator memory to 256 MB and compare cold-start duration (cost is still fractions of a cent)
- [ ] Alarm on dead-letter queue depth (Phase 4)
- [ ] Near-real-time CloudTrail alert on `AuthorizeSecurityGroupIngress`, so the change itself is seen before Config's verdict
- [ ] Stage 2 (live revoke) after two weeks of dry run with zero false positives (D-020)
- [x] Runbook written: `docs/runbooks/security-remediation-failed.md`

## Lessons

1. Measure each link, not just the total. The total looked fine, but the breakdown shows where any future speed-up has to come from (Config), and where it cannot (the function is already seconds).
2. The first run is the cold start. Any timing from a first run includes the environment set-up and should be repeated before it is quoted as typical.
