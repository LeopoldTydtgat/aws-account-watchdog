# Phase 3, step 1a: what the weekly housekeeper is allowed to do.
# The function comes in the next PR, so these permissions are live
# before anything tries to use them (same split as D-020).

locals {
  housekeeper_name = "watchdog-housekeeper"
}

resource "aws_cloudwatch_log_group" "housekeeper" {
  name              = "/aws/lambda/${local.housekeeper_name}"
  retention_in_days = 30
}

resource "aws_iam_role" "housekeeper" {
  name = local.housekeeper_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

# The housekeeper only looks and reports. It has no permission to stop,
# delete or tag anything, so a bug can never remove a resource.
#
# Blast radius if these credentials leak: list EC2 resources and tags in
# this account, write housekeeping items (and only those) to one table,
# read one parameter, send email from the verified identity, write its
# own logs and Watchdog metrics. Nothing else.
resource "aws_iam_role_policy" "housekeeper" {
  name = "watchdog-housekeeper-least-privilege"
  role = aws_iam_role.housekeeper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # EC2 Describe calls and the tagging API do not support
        # resource-level permissions.
        Sid    = "ReadResourcesAndTags"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
          "ec2:DescribeAddresses",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "tag:GetResources"
        ]
        Resource = "*"
      },
      {
        # LeadingKeys pins writes to partition HK, so this role cannot
        # touch the cost history or the incidents in the same table.
        Sid       = "WriteHousekeepingReports"
        Effect    = "Allow"
        Action    = "dynamodb:PutItem"
        Resource  = aws_dynamodb_table.watchdog_data.arn
        Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["HK"] } }
      },
      {
        Sid      = "ReadReportAddress"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:eu-north-1:${data.aws_caller_identity.current.account_id}:parameter/watchdog/report-email"
      },
      {
        # identity/* because the identity ARN contains my email (D-015).
        Sid      = "SendReportEmail"
        Effect   = "Allow"
        Action   = "ses:SendEmail"
        Resource = "arn:aws:ses:eu-north-1:${data.aws_caller_identity.current.account_id}:identity/*"
      },
      {
        Sid      = "WriteOwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.housekeeper.arn}:*"
      },
      {
        Sid       = "PublishWatchdogMetrics"
        Effect    = "Allow"
        Action    = "cloudwatch:PutMetricData"
        Resource  = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = "Watchdog" } }
      }
    ]
  })
}
