# Changelog

All notable changes to this project, newest first.

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