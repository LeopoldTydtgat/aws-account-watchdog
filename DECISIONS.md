# Decisions Log

Every significant design decision, including the ones I rejected. Rejections are documented because *why not* is half of engineering.

---

## D-001 - Positioning: extend native AWS controls, don't rebuild them

AWS Budgets, Cost Anomaly Detection, Config, CloudTrail, and Access Analyzer form the detection layer. The Watchdog is the in-house layer on top: routing, custom remediation with safety controls, incident logging, human-readable reporting. The README documents which is which.

## D-002 - Adopted upgrades (from external design critiques)

| Upgrade | Why |
|---|---|
| Dry-run mode + allow-list tag + rich incident logging on the remediator | Kills the "reckless automation" objection. It runs in DRY_RUN until trusted. |
| Game days, incident reports, runbooks | Free, un-copyable evidence; writing them is interview drilling. |
| Terraform drift detection | Nightly `terraform plan` in CI; console changes fail the pipeline and open a GitHub issue. |
| Native AWS controls alongside custom ones | All free/near-free; enables the integration positioning (D-001). |
| Slim VPC "test range" | Realistic target for the security patrol at $0: no instances, no NAT. |
| Break-glass alerting | CloudTrail/EventBridge alert on privileged-access events. |
| Operations documentation pack | IAM matrix, threat model, SLOs, runbooks, layered README, proof gallery. |
| Heartbeat metrics + DLQ | Monitor for the presence of success, not just the absence of errors. |
| Ops-grade report content | Totals, 7-day trend, % change, top services, status line. |

## D-003 - Rejected suggestions (with reasons)

| Suggestion | Why rejected |
|---|---|
| Target workload: EC2 + RDS + NAT Gateway | A NAT Gateway alone costs ~$32/month - 30x the project's cost, to guard decoys. The slim test range delivers the networking signal for $0. Rejecting this for cost reasons is itself the FinOps story. |
| Step Functions + human-in-the-loop approval | Right instinct, over-engineered for a single-person account. Dry-run + allow-list delivers the same safety signal explainably. Reserved for a future project. |
| Security Hub + Jira ITSM integration | Security Hub isn't free; Jira adds an external system. The integration *pitch* is kept; the build is not. |
| VPC Flow Logs parsing | Depth without an audience at this scale (no workload traffic). Future improvement. |
| Database restore drill | Watchdog uses DynamoDB; no Postgres, no containers in this stack. Depth beats breadth. |

## D-004 - Region: eu-north-1 (forced, and verified by testing)

The plan targeted us-east-1 (fullest free tier, cheapest). Reality: this account type is governed by an AWS-managed Service Control Policy that explicitly denies regional services (S3, Lambda, DynamoDB) outside eu-north-1, where AWS provisioned the project. Verified by CLI testing: CreateBucket denied in us-east-1 by SCP, identical call succeeded in eu-north-1; IAM (global) unaffected.

So: everything builds in eu-north-1. Free-tier allowances for the services used (Lambda, DynamoDB, EventBridge, SQS, SNS, CloudWatch) apply regardless of region, so the cost model survives. The original trade-off note stands: POPIA data-residency would point to af-south-1 for workloads holding South African personal data; this project holds only my own account metadata.

Lesson recorded: platform constraints are discovered by testing, not assumed from documentation.

## D-005 - Account type: AWS new experience (Builder ID)

The account was created through AWS's 2026 sign-up experience, where an AWS Builder ID (social login) replaces the classic root user and the account is organised as a "project". Consequences, mapped against classic root hardening:

- No classic root user exists → "root MFA, no root keys" becomes **Builder ID hardening**: TOTP MFA registered, recovery email set, MFA on the upstream social-login provider.
- Daily identity is the Builder ID itself (AccountFullAccessRole) → no separate IAM admin user needed.
- CLI access via `aws login` browser flow: temporary assumed-role credentials, max 12h, **zero stored access keys** - stronger than the classic access-key pattern the original plan assumed.
- The account sits inside an AWS-managed organisation with a Service Control Policy: region-locked to eu-north-1, some services unavailable (Cost Anomaly Detection, IAM Access Analyzer). Documented per-case as they surface.

## D-006 - Free plan reality (observed, not assumed)

$120 credits (not the $200 the research suggested; $100 base plus $20 earned), 6-month free period ending 16 March 2027, account requires upgrade to Paid Plan before then or it closes. Upgrade reminder set for mid-February 2027. Documented because verified numbers beat researched numbers.

## D-007 - Public repo from day one

The repo is the portfolio; recruiters and screeners must be able to read it. Safety comes from discipline, not privacy: OIDC means no keys exist to leak, account IDs are masked in all published screenshots, and secret scanning (gitleaks) runs in CI.


## D-008 - Early upgrade from Free Plan to Paid Plan (17 Sep 2026)

**Status:** Accepted. SCP removal still pending, see below.

**Context:** Plan v2 scheduled the Paid Plan upgrade for month 5, purely as
account survival. During Phase 0 the Free Plan turned out to be more
restrictive than documented: free-plan accounts sit inside an AWS-managed
organisation (o-laqten2dhu, management account 815915547314) with SCP
p-3aemv0uc attached, which explicitly denies iam:CreateOpenIDConnectProvider.
That blocks GitHub OIDC entirely, and keyless CI/CD is a core positioning
point of this project.

**Decision:** Upgrade to the Paid Plan immediately rather than wait for
month 5. Alternatives considered:
- Long-lived access keys in GitHub Secrets: rejected, kills the zero-keys
  positioning; kept only as a documented last resort.
- Wait until month 5: rejected, would stall the pipeline for months.

**Cost controls at upgrade:** $120 credits intact (valid to ~Sep 2027),
$0 due at upgrade, monthly spend limit set at $20 (console minimum), all
three early cost controls enabled (stop new launches, pause idle resources,
pause top cost drivers). Charges consume credits before the card.

**Aftermath:** ~Minutes after upgrade, terraform apply still hit the SCP
deny. aws organizations describe-organization confirmed the account was
still inside o-laqten2dhu. Billing flips immediately on upgrade; removal
from the managed organisation is a separate backend process with no
documented timing. Retrying over ~24h; if still denied, escalating via a
free Account and billing support case.

**Lesson:** The 2025 free-plan model is not just a billing tier, it is an
org-level permission boundary. Verifying the actual SCP against required
IAM actions belongs in day-one account planning.


## D-009: Manual approval gate on terraform apply (2026-09-17)

Decision: The deploy pipeline runs terraform plan automatically on main, but apply waits for manual approval via a GitHub production environment with a required reviewer.

Why: I am learning; I want to read every plan before it changes AWS. A bad merge cannot silently alter the account. Plan output is saved as an artefact and handed to apply, so what is approved is exactly what runs. This mirrors the standard team pattern (automated plan, human-gated apply).

Alternative rejected: fully automatic apply on merge. One click cheaper, but removes the review moment and the safety net, both of which matter more than speed at this stage.

---

*Format: new decisions get D-numbers and a date from here on.*

## D-010: Activate advanced features to regain org control (2026-09-20)

Decision: Activate advanced features on the AWS account, promoting it to full control of its own organisation, so the blocking SCP could be lifted.

Context: D-008 assumed the SCP sat in an AWS-managed organisation outside my control. A support case corrected that: o-laqten2dhu is my own organisation. The confusion came from one root email (leopold.tydtgat77@gmail.com) serving both the member account and the management account, while Builder ID social login always lands in the member account. Classic root sign-in to the management account was impossible because its password was never set and the reset flow looped on captcha.

The real door was settings.aws.com, reached via Manage projects, which exposes the management layer. Activating advanced features is irreversible and free, preserves all existing resources, and permanently removes the $20 console spend limit. The zero-spend and $1 budget alarms survive, so the loss was accepted.

Outcome: Activation completed. The old sandbox policy set was replaced entirely; p-3aemv0uc no longer exists. Seven SCPs remain, none denying iam:CreateOpenIDConnectProvider. The region-restriction policy (p-soifw7zx) permits iam:* in us-east-1, which is where IAM calls land since IAM is a global service. terraform apply then created the OIDC provider and deploy role on the first attempt.

Correction to D-008: the Paid Plan upgrade was not what unblocked this, and waiting 24h would never have helped. The blocker was organisational, not billing. Rejecting the long-lived-keys fallback was right; it was never needed.

Still watching: four BudgetsSpendLimitDeny* policies exist (Bedrock, Lambda, SageMaker, NewWorkloads). DenyNewWorkloads blocks lambda:CreateFunction, dynamodb:CreateTable and sqs:CreateQueue among others. Their Targets tabs must be checked before Phase 1, since an attachment to 895196059907 would stop the Watchdog build dead.


## D-011: OIDC trust matches immutable numeric subject claims (2026-09-20)

Decision: The deploy role trust policy matches the GitHub OIDC subject claim in its numeric-ID form, listing both the main-branch and production-environment subjects.

Context: With the SCP gone, every deploy run still failed with sts:AssumeRoleWithWebIdentity AccessDenied. CloudTrail showed the actual claim GitHub presented:

  repo:LeopoldTydtgat@272191895/aws-account-watchdog@1373360883:ref:refs/heads/main

GitHub now embeds immutable numeric owner and repo IDs. The plain repo path shown in every tutorial no longer matches literally. 24 denied attempts were logged before the cause was found.

Why the numeric form is better: renaming a repository or transferring ownership cannot silently carry access across. The identity is pinned to the object, not to a mutable label.

Both subjects are listed because the apply job runs under environment: production, which changes the claim from the ref form to the environment form. A StringEquals list is an OR of exact matches, no wildcards.

Second failure, fixed in the same change: PowerUserAccess deliberately excludes IAM, so the role could not read the OIDC provider its own Terraform manages. Granted GetOpenIDConnectProvider, TagOpenIDConnectProvider and UpdateOpenIDConnectProviderThumbprint scoped to that one provider. Create and Delete withheld on purpose: the pipeline cannot remove its own trust anchor or mint new federation paths.

Diagnostic lesson: the error message named no subject. CloudTrail did. Reading the event record beat guessing at the trust policy.

Evidence: Deploy #2 green end to end (plan, gated approval, apply), zero stored AWS keys.


## D-012: Screenshots dropped as default proof (2026-09-20)

Decision: Screenshots are no longer the default evidence mechanism for this project.

Why: Capturing and filing them is slow enough that it interrupts the build, and better evidence exists at zero effort. Proof comes from the public repo history (commits with reasoning, PR bodies, dates), linked workflow run URLs, CloudTrail JSON pasted into incident reports, and CI status badges. These are machine-generated, timestamped and harder to fake than an image.

Screenshots are kept only where nothing else can show the thing: a delivered report email, a dashboard graph over time, a security-group before and after.

This supersedes the screenshot requirements in build plan v2.

## D-013: One organisation-wide CloudTrail trail (2026-10-13)

Decision: A single organisation trail, watchdog-org-trail, created from the management account, covers all three accounts. Multi-region, log file validation on, home region eu-north-1, writing to the bucket watchdog-cloudtrail-895196059907 in the Hello World account.

Why: Root lives in the management account. A trail inside Hello World alone would never see a root sign-in, which is the event I most need to catch. One org trail also means one bucket, one retention rule and one place to search.

Bucket: versioned, public access blocked, SSE-S3 rather than KMS (KMS would add about $1/month, more than the rest of the project), 30-day expiry, HTTPS only, and a bucket policy that lets only this one trail write.

Alternative rejected: one trail per account. Three trails, three buckets, three sets of rules to keep in step, for the same coverage.

Trade-off: logs live in a workload account, not a dedicated log-archive account as a company would run it. Accepted at single-person scale; carried into the threat model.

## D-014: Organisation stack applied locally, never by the pipeline (2026-10-13)

Decision: terraform/org (the org trail and the management-account alerting) is applied by hand from my machine with the mgmt CLI profile. The pipeline never touches the management account.

Why: The deploy role lives in Hello World. Giving it any route into the management account would make the pipeline the biggest blast radius in the project: whoever controls the pipeline would control the organisation. This stack is set up once and rarely changes, so automation buys little.

Safeguards: provider allowed_account_ids pinned to the management account, so a wrong profile fails before any change; state in the same versioned, encrypted state bucket under its own key (org/terraform.tfstate); code still goes through a PR (PR #8), so every change is reviewed and on record.

Cost of the choice: drift checks on this stack are a manual terraform plan, not the nightly pipeline check.

## D-015: Alert email kept out of the public repo (2026-10-13)

Decision: My alert email address never appears in the public repo or in pipeline output.

How: The Hello World topic is in Terraform, but its email subscription was added once by hand with aws sns subscribe. The org stack is applied locally with no public plan artefact, so its address lives in a git-ignored terraform.tfvars.

Why: Pipeline plan output is saved as an artefact on a public repo, readable by anyone with a GitHub account. An email address in code or pipeline tfvars would be published there. An SNS email subscription also needs a human to click a confirmation link, so Terraform cannot fully own it anyway.

Trade-off: if the Hello World topic is ever recreated, its subscription disappears silently. It is listed in the manual changes register (D-017) and checked with aws sns list-subscriptions-by-topic.

## D-016: Root alarm moved to CloudWatch Logs after a game day found it blind (2026-10-13)

Context: The first root alert was an EventBridge rule (watchdog-root-activity) in us-east-1 in the management account, on the assumption that AWS records root sign-ins there. Testing it on 13 Oct: a root sign-in at 16:21 was recorded in us-west-2, because AWS routed it through us-west-2.signin.aws.amazon.com. The root console calls that followed in us-east-1 were all read-only, and EventBridge does not receive read-only management events. The rule saw nothing. A later sign-in through the global endpoint was recorded in us-east-1 and was caught. So the rule worked only sometimes, depending on routing I do not control.

Decision: The org trail also delivers to a CloudWatch Logs group, /watchdog/org-trail (30-day retention). A metric filter using the CIS root-usage pattern counts root activity, and the alarm watchdog-root-activity (Sum over 60 seconds, threshold 1, missing data treated as not breaching) emails through an eu-north-1 SNS topic. The trail is multi-region, so a root event from any region lands in the same log group. Routing no longer matters.

Checked before applying: the delivery role watchdog-cloudtrail-to-cloudwatch can only CreateLogStream and PutLogEvents into that one group. The filter pattern was tested with aws logs test-metric-filter against the real us-west-2 event (match) and a non-root CreateUser event (no match). Log volume measured at about 1 GB/month, inside the 5 GB free tier.

Proof: root sign-in 18:06:39, alarm email 18:09:38.

Alternative rejected: more EventBridge rules in more regions. Still a bet on where AWS routes sign-in, and each extra region means another edit to an SCP already near its 5,120-character limit.

The us-east-1 EventBridge rule stays as a faster path when it does fire. The alarm is the guarantee.

Lesson: an alarm that has never fired on the real event is not proven.

## D-017: Register of manual changes outside Terraform (2026-10-13)

Everything below was changed by hand in the console or CLI. None of it is in code, so drift detection will not see it. Listed so the account can be audited and rebuilt.

| Date | Change | Where | Why |
|---|---|---|---|
| 2026-09-21 | Root password set (stored in password manager) and root MFA added (authenticator app, separate from Google) | Management account | Root hardening; the password had never been set |
| 2026-09-21 | Centralised root access enabled (RootCredentialsManagement, RootSessions) | Organisation | Member accounts hold no root credentials (verified "Not present"); root tasks run from the management account |
| 2026-09-21 | Cost Anomaly Detection subscription set to a single $1 absolute threshold | Management account, covers the org | Earliest possible warning at this spend level |
| 2026-09-21 | SCP BudgetsSpendLimitDenyNewWorkloads deleted | Organisation | Would have blocked Lambda, DynamoDB and SQS creation in Phase 1; closes the open item in D-010 |
| 2026-10-05 | SCP p-soifw7zx: events:* and sns:* added to the us-east-1 allow list | Organisation | IAM events are recorded in us-east-1, so the IAM-change rules and their SNS topics must live there. Original saved locally as scp-p-soifw7zx-original.json |
| 2026-10-05 | CloudTrail trusted access enabled | Organisation | Required before an organisation trail can exist |
| 2026-10-13 | Email subscription on Hello World us-east-1 topic watchdog-security-alerts | Hello World | See D-015 |
| 2026-10-14 | SES email identity verified in eu-north-1 (account stays in the SES sandbox) | Hello World | The cost report sends from and to this one address. The identity ARN contains the address, so it stays out of code (D-015) |
| 2026-10-14 | SSM parameter /watchdog/report-email (String) | Hello World | The Lambda reads the address at runtime, so it never appears in code or pipeline output (D-015). String, not SecureString: an address is not a secret, and SecureString would need KMS decrypt on the role |
| 2026-11-17 | Service-linked role AWSServiceRoleForConfig created (`aws iam create-service-linked-role --aws-service-name config.amazonaws.com`) | Hello World | Config's recorder needs it. The pipeline role can only manage watchdog-* roles, so Terraform references this role by ARN and may only pass it to config.amazonaws.com (D-019) |

Corrections to earlier entries: D-004's region is now a choice, not forced; the region lock is my own SCP (p-soifw7zx), kept deliberately. D-005's note that Cost Anomaly Detection and Access Analyzer are unavailable no longer holds; both are live.

## D-018: Nightly cost report design (2026-11-17)

Decision: one Lambda, watchdog-cost-reporter (Python 3.13, arm64, 128 MB), run by an EventBridge schedule at 04:00 UTC, which is 06:00 SAST all year because South Africa has no daylight saving. It asks Cost Explorer for yesterday's cost by service, stores the day in watchdog-data, reads the previous week back, and emails a short report: total, prior day with % change, 7-day average, top 5 services and a status line.

Choices and why:

- Credits and refunds are filtered out. With $120 of credits on the account, a credit-adjusted figure would read $0.00 every day and hide real usage.
- The table key is the date (pk COST, sk YYYY-MM-DD) and every write is a full overwrite. A retry or a re-run cannot duplicate a day, and a later run picks up Cost Explorer's revisions to an estimated day.
- One async retry, events older than an hour dropped. Every attempt is a paid Cost Explorer request ($0.01). A second failure is a real fault, and catching it is the job of the heartbeat alarm planned for Phase 4, which watches the CostReportSuccess metric.
- Status line rules: SPIKE when a day is more than double the 7-day average and at least $0.05 (doubling from $0.01 to $0.02 is noise); OVER TARGET when the 30-day projection passes $1.50; otherwise OK.
- Report logic (dates, parsing, trend maths, email text) lives in cost_report.py with no AWS calls, so it is unit-tested without credentials. handler.py only does the AWS calls. 13 tests run in CI on every PR.
- Manual backfill: invoking with {"backfill_days": 7} loads up to 30 days in a single Cost Explorer request.
- The Lambda zip is built during terraform plan. The apply job runs on a fresh runner, so deploy.yml carries the zip with the plan artefact. .gitattributes forces LF line endings on .py files so the zip hashes the same on Windows and Linux; the first pipeline plan matched the local plan's hash exactly.

Alternatives rejected: parsing the Cost and Usage Report from S3 (free, but far more moving parts to save about $0.30 a month); SNS instead of SES for the email (SNS sends plain notification text with an unsubscribe footer, not a readable report).

Proof: manual backfill run on 17 Nov 2026 returned status 200, stored 7 days and delivered the report for 16 Nov ($0.0068, on pace for $0.23/month) to the inbox.

## D-019: AWS Config scoped to security groups as the detection layer (2026-11-17)

Decision: AWS Config records one resource type, AWS::EC2::SecurityGroup, continuously, and runs one AWS managed rule, RESTRICTED_INCOMING_TRAFFIC (watchdog-restricted-admin-ports), which marks a security group NON_COMPLIANT when it allows inbound TCP from anywhere on 22 (SSH) or 3389 (RDP). Config history goes to a private bucket, watchdog-config-<account>, SSE-S3, 30-day expiry, writable only by Config for this account, HTTPS only.

Choices and why:

- Security groups only. Config bills per configuration item recorded ($0.003 each, continuous) and per rule evaluation ($0.001 each). Recording every resource type would bill for every change in the account for no benefit here. A handful of security groups that rarely change cost cents a month.
- Continuous, not daily, recording. Daily recording is cheaper per item only when resources change often, and it would turn a 2-minute detection into up to 24 hours.
- A managed rule, not a custom Lambda rule. AWS maintains the logic, and it costs nothing extra to run.
- The service-linked role is created once by hand (D-017). The pipeline's IAM permissions stop at watchdog-* roles. It gets iam:PassRole on this one role, only when passed to config.amazonaws.com.

Alternative rejected: CloudTrail plus EventBridge alone, matching AuthorizeSecurityGroupIngress calls. Faster (seconds), and free, but it only sees the API call, not the resulting state. It misses a group that was already open before the Watchdog existed, and it has to reimplement "is this exposed?" for every way a rule can be written. It remains a useful early warning on top of Config (open follow-up from Game Day 01).

Lesson from the first deploy (Deploy #11): the PassRole permission and the recorder were applied in the same run with nothing ordering them. The recorder call reached IAM before the new permission had propagated and failed with AccessDenied. The re-run succeeded with nothing changed in code. Since then, a role and the resource that needs it ship in separate PRs (see D-020).

## D-020: Security-group remediator, dry run first (2026-11-17)

Decision: Lambda watchdog-sg-remediator (Python 3.13, arm64, 256 MB; raised from 128 MB after Game Day 01) is triggered by EventBridge rule watchdog-sg-noncompliant, which passes only NON_COMPLIANT results from watchdog-restricted-admin-ports. The function reads the group as it is now, finds each rule open to 0.0.0.0/0 or ::/0 on a blocked port, writes an incident to watchdog-data and emails the result.

Two stages:

- **Stage 1, now: DRY_RUN.** Alerts WOULD REVOKE and changes nothing. Enforced twice: the code treats anything other than exactly "false" as dry run, and the role has no ec2:RevokeSecurityGroupIngress at all.
- **Stage 2, later: live.** Adds that one permission, scoped to security groups, and sets DRY_RUN to "false". The function then removes only the exposed rules, re-reads the group and reports what is left. Criteria to switch: two weeks in dry run with every alert a true positive.

Safety controls:

- Allow-list: a group tagged watchdog:exclude=true gets ALERT ONLY in either stage, for ports opened on purpose. The alert still goes out, so an exception is never silent.
- Idempotency: EventBridge and Lambda can both deliver an event more than once. The incident key is the Config evaluation time plus the group ID (pk INC, sk <time>#<sg-id>). It is written OPEN with a conditional put, then NOTIFIED after the email. A repeat of a NOTIFIED incident is skipped; an attempt that died before emailing can be retried.
- The function re-reads the group instead of trusting the event, so a group closed or deleted in the meantime causes no action.
- The blocked ports are read from the Config rule's own parameters, so the rule and the function cannot drift apart.
- Least privilege: DynamoDB writes are limited to the INC partition with dynamodb:LeadingKeys, so this role cannot touch the cost history in the same table.

Failure handling: two Lambda retries, then the event goes to SQS dead-letter queue watchdog-sg-remediator-dlq (SSE, 14 days) through an on-failure destination. EventBridge delivery failures go to the same queue; its policy allows only this rule, HTTPS only. Runbook: docs/runbooks/security-remediation-failed.md.

Delivery: role, log group and queue shipped first (PR #18), the function and trigger second (PR #19), so the permissions existed before anything used them (lesson in D-019).

Alternatives rejected: Step Functions with a human approval step (right instinct, too heavy for one account; dry run plus allow-list gives the same safety and is easier to explain); revoking the whole rule set of a flagged group (would break legitimate rules such as SSH from inside the VPC).

Proof: Game Day 01 (docs/game-days/game-day-01.md). Port 22 opened to the world at 18:26:13, alert sent at 18:28:55, 2 min 42 s end to end.

## D-021: Weekly housekeeper, report only (2026-11-18)

Decision: Lambda watchdog-housekeeper (Python 3.13, arm64, 256 MB) runs every Monday at 04:30 UTC (06:30 SAST) from EventBridge rule watchdog-housekeeper-weekly. It reads EC2 resources and resource tags in eu-north-1 and emails a plain-English report of:

- unattached EBS volumes (billed every hour, serve nothing)
- stopped instances (still pay for their disks)
- Elastic IPs attached to nothing (charged every hour)
- snapshots older than 30 days
- resources missing the `project` or `owner` tag

Each finding comes with why it matters and what to do. The run is stored in watchdog-data (pk HK, sk run date) and publishes HousekeepingSuccess or HousekeepingFailure for the Phase 4 heartbeat.

Report only: the role has Describe and tag-read permissions, no stop, delete or tag. Removing resources is irreversible, so a person decides. Same principle as the remediator's dry run (D-020), without a stage 2.

Scope and known limits:

- eu-north-1 only. The region-lock SCP (D-004) blocks EC2 and tagging calls in us-east-1, and only EventBridge rules and SNS topics live there.
- EC2 resources are read with Describe calls, so even never-tagged ones are seen. Everything else comes from the Resource Groups Tagging API, which only lists resources that have, or once had, a tag. A non-EC2 resource that was never tagged is invisible to this check. Accepted: everything the Watchdog builds carries default tags, and the costly forgotten resources are EC2.
- What AWS creates by itself is skipped by the tag check: the default VPC, its default subnets and every security group named `default`. Everything a person makes, including inside the default VPC, is checked. The first version skipped the whole default VPC; the live test showed it hid two hand-made security groups (PR #25).
- `managed-by` is not required, so a resource made by hand on purpose only needs `project` and `owner`.

Failure handling: one async retry, then the heartbeat alarm (Phase 4) is what should notice, same as the cost reporter (D-018). A re-run on the same day overwrites that day's item.

Delivery: role and log group first (PR #23), function and schedule second (PR #24), as in D-020. PR #25 fixed the default-VPC rule and made the deploy pipeline run on `lambdas/**` as well, because Terraform zips the Lambda code and a code-only change would otherwise never deploy.

Alternatives rejected: AWS Trusted Advisor cost checks (full checks need a Business support plan); AWS Config with the required-tags managed rule (would mean recording every resource type, which Config bills per item, against the security-groups-only scope in D-019); auto-deleting old snapshots (irreversible, and a person should decide).

Proof: live test 18 Nov. 12:31 run found the two hand-made security groups missing tags; with an untagged 1 GiB test volume added, the next run reported 4 findings (the volume as unattached and as untagged). The volume was then deleted.
