# Root activity alarm, independent of region.
# Root sign-ins are recorded in whichever region AWS routes the sign-in
# through (observed: us-west-2), so an EventBridge rule in one region
# missed them. The multi-region org trail delivers every region's events
# to this one log group, where a metric filter catches root activity
# in any account and any region.

resource "aws_cloudwatch_log_group" "trail" {
  name              = "/watchdog/org-trail"
  retention_in_days = 30
}

# CloudTrail may only write into this one log group, nothing else.
resource "aws_iam_role" "trail_to_cloudwatch" {
  name = "watchdog-cloudtrail-to-cloudwatch"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "trail_to_cloudwatch" {
  name = "write-org-trail-log-group"
  role = aws_iam_role.trail_to_cloudwatch.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "WriteOnlyToOrgTrailLogGroup"
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.trail.arn}:log-stream:*"
    }]
  })
}

# Pattern verified with test-metric-filter against a real root ConsoleLogin
# (us-west-2) and a non-root CreateUser control before deploying.
resource "aws_cloudwatch_log_metric_filter" "root_activity" {
  name           = "watchdog-root-activity"
  log_group_name = aws_cloudwatch_log_group.trail.name
  pattern        = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"

  metric_transformation {
    name      = "RootActivityCount"
    namespace = "Watchdog/Security"
    value     = "1"
  }
}

# Alarms can only notify a topic in their own region, hence a topic here.
resource "aws_sns_topic" "security_alerts_home" {
  name = "watchdog-security-alerts"
}

resource "aws_sns_topic_subscription" "email_home" {
  topic_arn = aws_sns_topic.security_alerts_home.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "root_activity" {
  alarm_name          = "watchdog-root-activity"
  alarm_description   = "Root user activity in any account or region of the organisation"
  namespace           = "Watchdog/Security"
  metric_name         = "RootActivityCount"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.security_alerts_home.arn]
}
