# Phase 2, step 3a: what the security-group remediator is allowed to do,
# and where its failures go. The function itself comes in the next PR, so
# these permissions are live before anything tries to use them (D-020).

locals {
  sg_remediator_name = "watchdog-sg-remediator"
}

resource "aws_cloudwatch_log_group" "sg_remediator" {
  name              = "/aws/lambda/${local.sg_remediator_name}"
  retention_in_days = 30
}

# Dead-letter queue: an event the remediator could not handle after its
# retries lands here instead of disappearing. 14 days is the SQS maximum,
# long enough to notice and replay by hand.
resource "aws_sqs_queue" "sg_remediator_dlq" {
  name                      = "${local.sg_remediator_name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_iam_role" "sg_remediator" {
  name = local.sg_remediator_name

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

# Stage 1 (dry run): the role can look at security groups but cannot
# change them. There is deliberately no ec2:RevokeSecurityGroupIngress
# here, so dry run is enforced by IAM, not only by a flag in the code.
# Stage 2 adds that one permission.
#
# Blast radius if these credentials leak: list security groups, write
# incident items (and only incident items) to one table, read one
# parameter, send email from the verified identity, write its own logs,
# Watchdog metrics and one queue. Nothing else.
resource "aws_iam_role_policy" "sg_remediator" {
  name = "watchdog-sg-remediator-least-privilege"
  role = aws_iam_role.sg_remediator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # EC2 Describe calls do not support resource-level permissions.
        Sid      = "ReadSecurityGroups"
        Effect   = "Allow"
        Action   = "ec2:DescribeSecurityGroups"
        Resource = "*"
      },
      {
        # LeadingKeys pins writes to partition INC, so this role cannot
        # overwrite the cost history in the same table.
        Sid       = "WriteIncidents"
        Effect    = "Allow"
        Action    = "dynamodb:PutItem"
        Resource  = aws_dynamodb_table.watchdog_data.arn
        Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["INC"] } }
      },
      {
        Sid      = "ReadAlertAddress"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:eu-north-1:${data.aws_caller_identity.current.account_id}:parameter/watchdog/report-email"
      },
      {
        # identity/* because the identity ARN contains my email (D-015).
        Sid      = "SendAlertEmail"
        Effect   = "Allow"
        Action   = "ses:SendEmail"
        Resource = "arn:aws:ses:eu-north-1:${data.aws_caller_identity.current.account_id}:identity/*"
      },
      {
        Sid      = "WriteOwnLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.sg_remediator.arn}:*"
      },
      {
        Sid       = "PublishWatchdogMetrics"
        Effect    = "Allow"
        Action    = "cloudwatch:PutMetricData"
        Resource  = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = "Watchdog" } }
      },
      {
        # Lambda sends failed events here on the function's behalf.
        Sid      = "SendToDeadLetterQueue"
        Effect   = "Allow"
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.sg_remediator_dlq.arn
      }
    ]
  })
}
