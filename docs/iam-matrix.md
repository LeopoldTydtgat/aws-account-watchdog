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

## watchdog-sg-remediator (Hello World)

Trusted by: lambda.amazonaws.com, only from this account (aws:SourceAccount).

| Permission | Resource | Why |
|---|---|---|
| ec2:DescribeSecurityGroups | * | Read the flagged group as it is now. EC2 Describe calls have no resource-level permissions |
| dynamodb:PutItem | watchdog-data table, partition INC only (dynamodb:LeadingKeys) | Log incidents without being able to overwrite the cost history in the same table |
| ssm:GetParameter | /watchdog/report-email | Read the alert address at runtime (D-015) |
| ses:SendEmail | SES identities in eu-north-1 | Send the alert. identity/* because the identity ARN contains the address |
| logs:CreateLogStream, logs:PutLogEvents | its own log group | Write its logs |
| cloudwatch:PutMetricData | * where namespace = Watchdog | Publish SgRemediatorSuccess and SgRemediatorFailure |
| sqs:SendMessage | watchdog-sg-remediator-dlq | Lambda's on-failure destination sends failed events with the function's role |

Not granted in stage 1: ec2:RevokeSecurityGroupIngress. Dry run is enforced by IAM as well as by code (D-020).

Blast radius: list security groups, write incident items to one table, read one parameter, send email from the verified identity, write its own logs, Watchdog metrics and one queue. It cannot change any security group.

## watchdog-housekeeper (Hello World)

Trusted by: lambda.amazonaws.com, only from this account (aws:SourceAccount).

| Permission | Resource | Why |
|---|---|---|
| ec2:DescribeInstances, DescribeVolumes, DescribeSnapshots, DescribeAddresses, DescribeVpcs, DescribeSubnets, DescribeSecurityGroups | * | Find forgotten and untagged EC2 resources. EC2 Describe calls have no resource-level permissions |
| tag:GetResources | * | Read the tags of everything else in the region |
| dynamodb:PutItem | watchdog-data table, partition HK only (dynamodb:LeadingKeys) | Store each weekly report without being able to touch costs or incidents |
| ssm:GetParameter | /watchdog/report-email | Read the report address at runtime (D-015) |
| ses:SendEmail | SES identities in eu-north-1 | Send the report. identity/* because the identity ARN contains the address |
| logs:CreateLogStream, logs:PutLogEvents | its own log group | Write its logs |
| cloudwatch:PutMetricData | * where namespace = Watchdog | Publish HousekeepingSuccess and HousekeepingFailure |

Not granted: any stop, delete, modify or tag action. The housekeeper reports; a person decides (D-021).

Blast radius: list EC2 resources and tags in this account, write housekeeping items to one table, read one parameter, send email from the verified identity, write its own logs and Watchdog metrics. It cannot change anything.

## watchdog-github-deploy (Hello World)

Trusted by: GitHub OIDC, only for this repo's main branch and production environment (D-011).

| Permission | Resource | Why |
|---|---|---|
| PowerUserAccess (AWS managed) | * | Create and change the Watchdog's resources through Terraform |
| IAM role management (create, delete, tag, inline and attached policies, PassRole) | roles named watchdog-* | PowerUserAccess excludes IAM. Scoped so the pipeline can only manage the Watchdog's own roles |
| Read, tag and update thumbprint | the GitHub OIDC provider | Let Terraform manage the provider it authenticates through |
| iam:PassRole, only to config.amazonaws.com | AWSServiceRoleForConfig | Point the Config recorder at its service-linked role (D-019) |

Blast radius: the largest in the project. Anyone who could run a workflow on main with the production environment could change any non-IAM resource and any watchdog-* role. Mitigations: OIDC trust pinned to numeric repo and owner IDs, branch protection on main, and a required manual approval before every apply (D-009).

## watchdog-github-drift (Hello World)

Trusted by: GitHub OIDC, only for jobs in this repo's drift-check environment, which only the main branch can use (D-022).

| Permission | Resource | Why |
|---|---|---|
| ReadOnlyAccess (AWS managed) | * | terraform plan refreshes every resource in the stack and reads the state file |

Not granted: any write, including the state lock file (the plan runs with -lock=false). ReadOnlyAccess does not include kms:Decrypt, so SecureString parameters stay unreadable.

Blast radius: read most of the account's configuration and the Terraform state. No changes of any kind. It reads more widely than any other role, which is why only one environment may use it.

## watchdog-cloudtrail-to-cloudwatch (management account)

Trusted by: cloudtrail.amazonaws.com.

| Permission | Resource | Why |
|---|---|---|
| logs:CreateLogStream, logs:PutLogEvents | /watchdog/org-trail log streams | Deliver the organisation trail into CloudWatch Logs for the root activity alarm (D-016) |

Blast radius: write log events into one log group.
