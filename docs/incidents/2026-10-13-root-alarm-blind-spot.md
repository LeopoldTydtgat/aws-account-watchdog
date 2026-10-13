# INC-001: Root sign-in alarm was blind to a us-west-2 sign-in

| | |
|---|---|
| Date | 2026-10-13 |
| Type | Controlled drill (game day), my own sign-in |
| Severity | Medium: detection gap on the highest-privilege identity; no unauthorised access |
| Status | Resolved, fix verified live |
| Related | D-016, PR #8, PR #9 |

Times are SAST (UTC+2). CloudTrail records UTC.

## Summary

The root activity alert (EventBridge rule `watchdog-root-activity`, us-east-1, management account) did not fire for a real root sign-in. AWS recorded that sign-in in us-west-2, where no rule existed. The alert was rebuilt as a CloudWatch Logs metric filter and alarm on the organisation trail, which collects every region in one place. Verified with a second root sign-in: alarm email 2 minutes 59 seconds later.

## Timeline

| Time (SAST) | Event |
|---|---|
| 16:21:05 | Root `ConsoleLogin` to the management account (MFA used), recorded in **us-west-2** because the sign-in went through `us-west-2.signin.aws.amazon.com` |
| 16:21 onwards | Root console activity in us-east-1, all read-only calls. No alert |
| After 16:21 | No email arrived. CloudTrail showed the `ConsoleLogin` in us-west-2, not us-east-1 |
| Before 18:06 | Fix written, filter pattern tested against the real event, `terraform/org` applied locally |
| 18:06:39 | Verification root `ConsoleLogin`, this time via the global endpoint `signin.aws.amazon.com`, recorded in **us-east-1** |
| 18:09:38 | `watchdog-root-activity` alarm email received |
| 18:38 | PR #9 merged |

## Root cause

Two facts combined:

1. **The sign-in region is not fixed.** A `ConsoleLogin` is recorded in the region of the sign-in endpoint used. At 16:21 the browser was sent to `us-west-2.signin.aws.amazon.com`, so the event landed in us-west-2. At 18:06 the global endpoint was used, so it landed in us-east-1. I do not control which one AWS picks.
2. **EventBridge does not receive read-only management events.** Every root call in us-east-1 after the sign-in was read-only, so the rule had nothing to match there either.

EventBridge rules are regional, so a us-east-1 rule only ever sees us-east-1 events.

Contributing factor: the rule was built on the assumption that root sign-ins always land in us-east-1, and it had not yet been tested with a real root sign-in.

## Impact

No unauthorised access: it was my own sign-in, with MFA. The real impact was the gap itself: until the fix, any root sign-in routed outside us-east-1 would have produced no alert on the most powerful identity in the organisation.

## Fix (PR #9, D-016)

- The org trail (multi-region) also delivers to CloudWatch Logs group `/watchdog/org-trail`, 30-day retention.
- Delivery role `watchdog-cloudtrail-to-cloudwatch` can only `CreateLogStream` and `PutLogEvents` into that one group.
- Metric filter using the CIS root-usage pattern counts root activity from every region.
- Alarm `watchdog-root-activity`: Sum over 60 seconds, threshold 1, missing data treated as not breaching, notifying an eu-north-1 SNS topic.
- The us-east-1 EventBridge rule stays as a faster path when it does fire. The alarm is the guarantee.

## Verification

- **Before applying:** `aws logs test-metric-filter` against the real us-west-2 event (match) and a non-root `CreateUser` event (no match).
- **Cost check:** log volume measured at about 1 GB/month, inside the 5 GB CloudWatch Logs free tier.
- **Live test:** root sign-in at 18:06:39, alarm email at 18:09:38.

## Lessons

1. An alarm that has never fired on the real event is not proven. Every alert gets a live test.
2. Do not build detection on where AWS happens to record an event. Collect everywhere (multi-region trail), then detect in one place.
3. Know what the event bus does not carry: read-only calls never reach EventBridge.

## Follow-up

- [x] Decision recorded (D-016)
- [ ] Runbook `docs/runbooks/suspected-account-compromise.md` (Phase 4) to start from this alarm

## Evidence

CloudTrail event records from the management account's Event history. Trimmed to the relevant fields; source IP and user agent removed.

**The missed sign-in (us-west-2):**

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "Root",
    "arn": "arn:aws:iam::815915547314:root",
    "accountId": "815915547314"
  },
  "eventTime": "2026-10-13T14:21:05Z",
  "eventSource": "signin.amazonaws.com",
  "eventName": "ConsoleLogin",
  "awsRegion": "us-west-2",
  "responseElements": { "ConsoleLogin": "Success" },
  "additionalEventData": { "MFAUsed": "Yes" },
  "eventID": "311e4f2e-bed6-4693-a1da-310a852e6b51",
  "readOnly": false,
  "eventType": "AwsConsoleSignIn",
  "tlsDetails": { "clientProvidedHostHeader": "us-west-2.signin.aws.amazon.com" }
}
```

**The caught sign-in (us-east-1):**

```json
{
  "eventVersion": "1.11",
  "userIdentity": {
    "type": "Root",
    "arn": "arn:aws:iam::815915547314:root",
    "accountId": "815915547314"
  },
  "eventTime": "2026-10-13T16:06:39Z",
  "eventSource": "signin.amazonaws.com",
  "eventName": "ConsoleLogin",
  "awsRegion": "us-east-1",
  "responseElements": { "ConsoleLogin": "Success" },
  "additionalEventData": { "MFAUsed": "Yes" },
  "eventID": "95595193-1219-4027-ae58-fc40d745a2af",
  "readOnly": false,
  "eventType": "AwsConsoleSignIn",
  "tlsDetails": { "clientProvidedHostHeader": "signin.aws.amazon.com" }
}
```

Same browser, same identity, same day: only the sign-in host differed, and with it the region.

Event history also shows five earlier root sign-ins that afternoon (16:14 to 16:17), all recorded in us-west-2.