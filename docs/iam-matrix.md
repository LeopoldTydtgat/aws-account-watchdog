# IAM matrix

Every role the Watchdog creates, what it may do, on what, and why. If a role's credentials leaked, the Blast radius column is the worst case.

No IAM users and no long-lived access keys exist anywhere in the Watchdog.

## watchdog-cost-reporter (Hello World)

Trusted by: lambda.amazonaws.com, only from this account (aws:SourceAccount).

| Permission | Resource | Why |
|---|---|---|
| ce:GetCostAndUsage | * | Read yesterday's cost. Cost Explorer has no resource-level permissions |
| dynamodb:PutItem, dynamodb:Query | watchdog-data table | Store each day and read the past week for the trend |
| ssm:GetParameter | /watchdog/report-email | Read the report address at runtime (D-015) |
| ses:SendEmail | SES identities in eu-north-1 | Send the report. identity/* because the identity ARN contains the address; sandbox mode limits sending to verified identities |
| logs:CreateLogStream, logs:PutLogEvents | its own log group | Write its logs. The log group is made by Terraform, so no CreateLogGroup |
| cloudwatch:PutMetricData | * where namespace = Watchdog | Publish CostReportSuccess and CostReportFailure |

Blast radius: read cost metadata, read and write one table, read one parameter, send email from the verified identity, write its own logs and Watchdog metrics. Nothing else.

## watchdog-github-deploy (Hello World)

Trusted by: GitHub OIDC, only for this repo's main branch and production environment (D-011).

| Permission | Resource | Why |
|---|---|---|
| PowerUserAccess (AWS managed) | * | Create and change the Watchdog's resources through Terraform |
| IAM role management (create, delete, tag, inline and attached policies, PassRole) | roles named watchdog-* | PowerUserAccess excludes IAM. Scoped so the pipeline can only manage the Watchdog's own roles |
| Read, tag and update thumbprint | the GitHub OIDC provider | Let Terraform manage the provider it authenticates through |

Blast radius: the largest in the project. Anyone who could run a workflow on main with the production environment could change any non-IAM resource and any watchdog-* role. Mitigations: OIDC trust pinned to numeric repo and owner IDs, branch protection on main, and a required manual approval before every apply (D-009).

## watchdog-cloudtrail-to-cloudwatch (management account)

Trusted by: cloudtrail.amazonaws.com.

| Permission | Resource | Why |
|---|---|---|
| logs:CreateLogStream, logs:PutLogEvents | /watchdog/org-trail log streams | Deliver the organisation trail into CloudWatch Logs for the root activity alarm (D-016) |

Blast radius: write log events into one log group.
