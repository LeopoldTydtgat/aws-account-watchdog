# Game Day 04: Console change (drift)

| | |
|---|---|
| Date | 2026-11-18 |
| Type | Controlled drill (game day), change made by me outside Terraform |
| Target | `watchdog-range-web` (sg-0e27cf9f9b289a45d) in the test range VPC (vpc-0cbd5431e3edaa393). No instances, nothing reachable behind it |
| Mode | Drift check started by hand (workflow_dispatch) instead of waiting for the 03:00 schedule |
| Result | Caught 1 min 31 s after the change, put back through the pipeline 5 min 0 s after the change, drift issue closed itself. Nothing was fixed by hand in the console |
| Related | D-022, PR #27, PR #28, issue #29 |

Times are SAST (UTC+2). GitHub and AWS record UTC.

## Scenario

Someone opens a port by hand to "quickly test something" and forgets about it. The account no longer matches the code: nobody reviewed the change, nothing in git records it, and the next deploy will either undo it without warning or be surprised by it.

Port 8080 was chosen on purpose. It is not 22 or 3389, so the security patrol (D-019) ignores it, and opening a port is not an IAM change, so no alarm email goes out either. The drift check is the only thing that can catch it.

Goal: prove the chain change, detect, report, put back, confirm.

## Steps

1. `aws ec2 authorize-security-group-ingress --group-id sg-0e27cf9f9b289a45d --protocol tcp --port 8080 --cidr 0.0.0.0/0 --region eu-north-1` (rule sgr-00eafa4ac2a891675)
2. Started the Drift check by hand: Actions > Drift check > Run workflow
3. Read issue #29
4. Put the account back: re-ran the latest Deploy run (Deploy #18, all jobs). Read the plan in the job's raw log: 0 to add, 1 to change, 0 to destroy, and the only change was removing the 8080 rule. Approved the production deployment.
5. Started the Drift check by hand again

## Timeline

| Time (SAST) | Event | Since change |
|---|---|---|
| 14:47:34 | Port 8080 opened to 0.0.0.0/0 | 0 |
| 14:48:26 | Drift check #2 started | 52 s |
| 14:49:05 | Issue #29 "Drift detected" opened | 1 min 31 s |
| 14:49:09 | Drift check #2 finished, failed | 1 min 35 s |
| 14:50:23 | Deploy #18 re-run, plan started | 2 min 49 s |
| 14:51:04 | Plan finished: 0 to add, 1 to change, 0 to destroy | 3 min 30 s |
| 14:51:58 | Approved, apply started | 4 min 24 s |
| 14:52:34 | Apply finished, 8080 rule removed | 5 min 0 s |
| 14:53:25 | Drift check #3 started | 5 min 51 s |
| 14:53:58 | Issue #29 closed by the check | 6 min 24 s |
| 14:54:01 | Drift check #3 finished, passed | 6 min 27 s |

## What the Watchdog produced

Issue #29, opened by the workflow:

```
The nightly drift check found differences between the AWS account and the Terraform code.

What to do: find out who changed what (CloudTrail), then either put the change into code
through a PR, or re-run the last deploy to put the account back to what the code says.

  # aws_security_group.range_web will be updated in-place
  ~ resource "aws_security_group" "range_web" {
        id = "sg-0e27cf9f9b289a45d"
      ~ ingress = [
          - {
              - cidr_blocks      = ["0.0.0.0/0"]
              - from_port        = 8080
              - protocol         = "tcp"
              - to_port          = 8080
                ...
            },
            # (1 unchanged element hidden)
        ]
        name = "watchdog-range-web"
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

The `-` lines read as "Terraform would remove this", because the code does not have it.

## Findings

1. **The chain works end to end.** Caught, reported, put back and confirmed, all through the pipeline. The fix was an approved deploy, not a console click.
2. **The check is fast; the schedule is not.** 39 s from start to issue. Today's 1 min 31 s is only because the check was started by hand. On the nightly schedule, a change like this could stand for up to 24 hours. That is acceptable for drift in general, but not for exposure: the patrol covers 22 and 3389 in about 2.5 minutes, and every other port waits for the night.
3. **The issue says what changed, not who.** Who comes from CloudTrail (the AuthorizeSecurityGroupIngress event). The open CloudTrail follow-up from Game Day 01 would answer both who and when within a minute.
4. **Scrubbing worked.** The public issue shows no account ID and no email address.
5. **Re-running the latest Deploy run is a safe revert only if it was built from the current code.** Deploy #18 ran at commit 5ef5b56. The only later merge (PR #28) touched the workflow file, not `terraform/` or `lambdas/`, so the code was the same. The deploy runs on every change under those folders, so the latest run normally carries the current code, but the run's commit is worth checking before re-running.
6. **The human gate held.** The revert still needed the production approval, and the plan was read before approving.

## Follow-up

- [ ] Watch the first scheduled run, 19 Nov 03:00 SAST (expect no changes)
- [ ] Near-real-time CloudTrail alert on `AuthorizeSecurityGroupIngress` (also open from Game Day 01)
- [ ] Game Day 05: lose the Terraform state file and recover it from S3 versioning

## Lessons

1. Detection is not repair. Keeping the drift check report-only leaves the decision (revert, or adopt the change into code) with a person.
2. A nightly check is a safety net, not an alarm. Anything that needs minutes has to be event-driven.
