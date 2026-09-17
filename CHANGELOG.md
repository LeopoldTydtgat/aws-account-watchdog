# Changelog

All notable changes to this project, newest first.

## 2026-09-16 - Phase 0 begins
- AWS account created (new experience / Builder ID, project provisioned by AWS)
- Builder ID hardened: TOTP MFA registered, recovery email set
- Zero-spend budget + $1 monthly cost budget created, email alerts on
- Local tooling installed: git, AWS CLI v2, Terraform (Windows 11)
- CLI authenticated keylessly via `aws login` (temporary credentials, no stored keys)
- Repo created public with README skeleton, DECISIONS.md, CHANGELOG.md

## 2026-09-17 - Paid Plan upgrade
- Upgraded account to Paid Plan (D-008); OIDC apply blocked pending SCP removal
