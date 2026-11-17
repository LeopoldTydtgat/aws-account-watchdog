# Changelog

All notable changes to this project, newest first.

## 2026-11-17 - Security patrol live in dry run (Phase 2)
- PR #16: VPC test range (10.20.0.0/16, public and private subnets, no instances, no NAT). Security groups watchdog-range-web (443 open) and watchdog-range-admin (22 from inside the VPC only); default security group stripped.
- Config service-linked role created by hand (D-017).
- PR #17: AWS Config recording security groups only, private history bucket, managed rule watchdog-restricted-admin-ports for 22 and 3389 (D-019). First apply failed on an IAM propagation race between the new PassRole permission and the recorder; the re-run applied the remaining 4 resources.
- PR #18: watchdog-sg-remediator role (no revoke permission in stage 1), log group and dead-letter queue, shipped ahead of the function.
- PR #19: watchdog-sg-remediator function in DRY_RUN, EventBridge rule on NON_COMPLIANT results, retries and dead-letter queue, 21 new unit tests (D-020). Pipeline zip hash matched the local build.
- Game Day 01 (docs/game-days/game-day-01.md): SSH opened to the world on the test range, WOULD REVOKE alert 2 min 42 s later.
- Runbook: docs/runbooks/security-remediation-failed.md. IAM matrix updated.

## 2026-11-17 - Nightly cost report live
- PR #14: cost-reporter Lambda, EventBridge schedule at 04:00 UTC (06:00 SAST), one async retry, invoke permission limited to that rule (D-018).
- CI: new python-tests job runs pytest on every PR.
- Deploy: the built Lambda zip now travels from the plan job to the apply job. .gitattributes keeps .py line endings identical across Windows and Linux.
- First run: manual 7-day backfill stored 7 days and emailed the report for 16 Nov: $0.0068, on pace for $0.23/month.
- IAM matrix started (docs/iam-matrix.md).

## 2026-10-14 - Phase 1 groundwork
- SES identity verified and report address stored in SSM by hand (D-017).
- PR #12: watchdog-data DynamoDB table, provisioned 1/1 (always free), deletion protection on.
- PR #13: watchdog-cost-reporter role, least-privilege inline policy and 30-day log group.

## 2026-10-13 - Audit layer live, root alarm fixed after game day
- PR #7 (Hello World, via pipeline): CloudTrail log bucket (versioned, SSE-S3, 30-day expiry, writable only by the org trail), IAM Access Analyzer, us-east-1 SNS topic and EventBridge rule for IAM changes. Email subscription added by hand (D-015).
- PR #8 (management account, applied locally, D-014): organisation trail watchdog-org-trail (multi-region, log file validation) covering all three accounts (D-013), plus us-east-1 SNS topic and EventBridge rules for root activity and IAM changes.
- Game day: a root sign-in routed through us-west-2 was missed by the us-east-1 root rule (D-016).
- PR #9 (management account, applied locally): org trail also delivers to CloudWatch Logs; CIS root-usage metric filter and alarm watchdog-root-activity notify through an eu-north-1 SNS topic.
- All alarms proven live: IAM-change emails within a minute in both accounts; root alarm email 3 minutes after sign-in.
- Decisions D-013 to D-017 recorded, including the register of manual changes outside Terraform.

## 2026-09-20 - OIDC live, keyless CI/CD working end to end
- Activated advanced features on the account, taking control of the organisation (D-010). The old sandbox SCP set was replaced; the policy denying iam:CreateOpenIDConnectProvider no longer exists.
- Created the GitHub OIDC provider and watchdog-github-deploy role via Terraform. PowerUserAccess plus an inline policy scoped to watchdog-* roles and the one OIDC provider.
- Fixed the trust policy to match GitHub's numeric-ID subject claims, diagnosed from CloudTrail after 24 denied assume-role attempts (D-011).
- AWS_DEPLOY_ROLE_ARN secret populated with the real ARN; placeholder removed.
- Deploy pipeline green end to end: plan on main, manual approval gate, apply. Zero stored AWS keys.
- Dropped screenshots as the default proof mechanism (D-012).


## 2026-09-17 - Paid Plan upgrade, pipeline v1
- Upgraded account to Paid Plan (D-008); OIDC apply blocked pending SCP removal
- Added CI workflow (ci.yml): terraform fmt -check, init -backend=false, and validate run on every pull request via GitHub Actions. No AWS credentials involved.
- Added deploy workflow (deploy.yml): terraform plan via OIDC on pushes to main touching terraform/, apply gated behind manual approval (GitHub production environment). Inert until the OIDC role exists. Created the production environment (required reviewer) and AWS_DEPLOY_ROLE_ARN secret (placeholder until SCP lifts).

## 2026-09-16 - Phase 0 begins
- AWS account created (new experience / Builder ID, project provisioned by AWS)
- Builder ID hardened: TOTP MFA registered, recovery email set
- Zero-spend budget + $1 monthly cost budget created, email alerts on
- Local tooling installed: git, AWS CLI v2, Terraform (Windows 11)
- CLI authenticated keylessly via `aws login` (temporary credentials, no stored keys)
- Repo created public with README skeleton, DECISIONS.md, CHANGELOG.md
- Added deploy workflow (deploy.yml): terraform plan via OIDC on pushes to main touching terraform/, apply gated behind manual approval (GitHub production environment). Inert until the OIDC role exists. Created the production environment (required reviewer) and AWS_DEPLOY_ROLE_ARN secret (placeholder until SCP lifts).
