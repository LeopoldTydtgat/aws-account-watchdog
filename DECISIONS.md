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

---

*Format: new decisions get D-numbers and a date from here on.*
