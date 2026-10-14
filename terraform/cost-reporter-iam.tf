# Phase 1, step 2: what the cost-reporter Lambda is allowed to do.
# The function itself comes in the next PR.

locals {
  cost_reporter_name = "watchdog-cost-reporter"
}

# Created here rather than by Lambda, so retention is set and the role
# needs no logs:CreateLogGroup.
resource "aws_cloudwatch_log_group" "cost_reporter" {
  name              = "/aws/lambda/${local.cost_reporter_name}"
  retention_in_days = 30
}

resource "aws_iam_role" "cost_reporter" {
  name = local.cost_reporter_name

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

# Blast radius if these credentials leak: read cost metadata, read and
# write one table, read one parameter, send email from a verified
# identity, write its own logs and Watchdog metrics. Nothing else.
resource "aws_iam_role_policy" "cost_reporter" {
  name = "watchdog-cost-reporter-least-privilege"
  role = aws_iam_role.cost_reporter.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadCostData"
        Effect   = "Allow"
        Action   = "ce:GetCostAndUsage"
        Resource = "*"
      },
      {
        Sid      = "ReadWriteReportTable"
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:Query"]
        Resource = aws_dynamodb_table.watchdog_data.arn
      },
      {
        Sid      = "ReadReportAddress"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:eu-north-1:${data.aws_caller_identity.current.account_id}:parameter/watchdog/report-email"
      },
      {
        # identity/* because the identity ARN contains my email (D-015).
        # Sandbox mode limits sending to verified identities anyway.
        Sid      = "SendReportEmail"
        Effect   = "Allow"
        Action   = "ses:SendEmail"
        Resource = "arn:aws:ses:eu-north-1:${data.aws_caller_identity.current.account_id}:identity/*"
      },
      {
        Sid      = "WriteOwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.cost_reporter.arn}:*"
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