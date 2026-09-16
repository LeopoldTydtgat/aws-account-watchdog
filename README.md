# AWS Account Watchdog

> Operational guardrails for my AWS account: daily cost reporting, automated security-group remediation, resource hygiene checks, drift detection, and incident logging — built with least-privilege IAM, Terraform, and keyless CI/CD, for under $1.50/month.

**Status:** Phase 0 — foundations. Live since September 2026.

---

## The 30-second version

I run my personal AWS account like a small production environment. The Watchdog:

- Reports spend daily (readable ops email, not a raw number)
- Detects and remediates exposed security groups, with dry-run and allow-list safety controls
- Flags forgotten resources before they bill for nothing
- Detects infrastructure drift nightly and opens an issue when the console disagrees with the code
- Monitors its own health (heartbeat: alerts when a report *doesn't* arrive)
- Logs every incident and documents every decision

Everything is Terraform, deployed keylessly via GitHub Actions OIDC. Cost: under $1.50/month, and the Watchdog reports its own cost.

## Why this isn't "AWS already does this"

I use AWS's native controls — Budgets, Cost Anomaly Detection, Config, CloudTrail, Access Analyzer — as the detection layer. The Watchdog is the layer companies actually build in-house: routing findings, applying custom remediation logic with safety controls, logging incidents, and producing reports a human actually reads. I'm not rebuilding AWS features out of ignorance; I'm extending them deliberately, and this README documents which is which.

## Region choice

This runs in us-east-1: fullest free tier, all services, lowest cost. For workloads holding South African personal data, POPIA data-residency considerations would point to af-south-1 (Cape Town). The Watchdog holds only my own account's billing and configuration metadata, so cost and service coverage won. The trade-off is documented, not ignored.

## Cost (real observed numbers)

| Piece | Expected | Observed |
|---|---|---|
| Lambda (×3) | $0 | — |
| EventBridge | $0 | — |
| DynamoDB (provisioned) | $0 | — |
| SES / SNS / SQS | $0 | — |
| CloudWatch | $0 | — |
| CloudTrail (S3 storage) | ~$0.01–0.05 | — |
| Cost Explorer API | ~$0.30 | — |
| AWS Config (scoped to SGs) | ~$0.20–0.50 | — |
| **Total** | **~$0.50–1.50/month** | — |

Observed column fills in as the system runs.

## Deep dives

- [Decisions log](DECISIONS.md) — every design choice, including rejected ones
- [Changelog](CHANGELOG.md)
- docs/ — architecture, IAM matrix, threat model, runbooks, incident reports, game days *(coming in later phases)*
- proof/ — real reports, screenshots, alarm emails, masked and dated

## Honest framing

Single-account, single-region, built for learning and evidence. I used AI as an implementation accelerator; the architecture, service choices, IAM boundaries, cost constraints, testing approach, and documentation are mine, and I can defend every decision in this repo.
