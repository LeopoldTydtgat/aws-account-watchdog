# Break-glass alerts for the management account (us-east-1).
locals {
  iam_change_events = [
    "AttachRolePolicy", "DetachRolePolicy", "PutRolePolicy", "DeleteRolePolicy",
    "UpdateAssumeRolePolicy",
    "AttachUserPolicy", "DetachUserPolicy", "PutUserPolicy", "DeleteUserPolicy",
    "AttachGroupPolicy", "DetachGroupPolicy", "PutGroupPolicy", "DeleteGroupPolicy",
    "CreatePolicy", "DeletePolicy", "CreatePolicyVersion", "DeletePolicyVersion",
    "SetDefaultPolicyVersion",
    "CreateUser", "CreateAccessKey", "CreateLoginProfile", "UpdateLoginProfile"
  ]
}

resource "aws_sns_topic" "security_alerts" {
  provider = aws.us_east_1
  name     = "watchdog-security-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  provider  = aws.us_east_1
  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Any root sign-in or root API call.
resource "aws_cloudwatch_event_rule" "root_activity" {
  provider    = aws.us_east_1
  name        = "watchdog-root-activity"
  description = "Break-glass: any root user sign-in or API call"

  event_pattern = jsonencode({
    "detail-type" = ["AWS Console Sign In via CloudTrail", "AWS API Call via CloudTrail"]
    detail = {
      userIdentity = { type = ["Root"] }
    }
  })
}

resource "aws_cloudwatch_event_target" "root_activity_email" {
  provider  = aws.us_east_1
  rule      = aws_cloudwatch_event_rule.root_activity.name
  target_id = "security-alerts-sns"
  arn       = aws_sns_topic.security_alerts.arn
}

resource "aws_cloudwatch_event_rule" "iam_changes" {
  provider    = aws.us_east_1
  name        = "watchdog-iam-changes"
  description = "Break-glass: any IAM permission change in the management account"

  event_pattern = jsonencode({
    source        = ["aws.iam"]
    "detail-type" = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource = ["iam.amazonaws.com"]
      eventName   = local.iam_change_events
    }
  })
}

resource "aws_cloudwatch_event_target" "iam_changes_email" {
  provider  = aws.us_east_1
  rule      = aws_cloudwatch_event_rule.iam_changes.name
  target_id = "security-alerts-sns"
  arn       = aws_sns_topic.security_alerts.arn
}

resource "aws_sns_topic_policy" "security_alerts" {
  provider = aws.us_east_1
  arn      = aws_sns_topic.security_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowWatchdogRulesToPublish"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.security_alerts.arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [
            aws_cloudwatch_event_rule.root_activity.arn,
            aws_cloudwatch_event_rule.iam_changes.arn
          ]
        }
      }
    }]
  })
}
