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

Corrections to earlier entries: D-004's region is now a choice, not forced; the region lock is my own SCP (p-soifw7zx), kept deliberately. D-005's note that Cost Anomaly Detection and Access Analyzer are unavailable no longer holds; both are live.
