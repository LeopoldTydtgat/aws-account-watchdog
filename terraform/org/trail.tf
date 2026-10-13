# One organisation-wide trail: covers all three accounts and every region,
# and sees root activity. Logs go to the bucket in Hello World (Part A).
# A copy goes to CloudWatch Logs so root activity in any region can raise
# an alarm (see root-monitoring.tf).
resource "aws_cloudtrail" "org" {
  name                          = "watchdog-org-trail"
  s3_bucket_name                = "watchdog-cloudtrail-895196059907"
  is_organization_trail         = true
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true

  # CloudTrail requires the ":*" log stream wildcard on the group ARN.
  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.trail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.trail_to_cloudwatch.arn

  # The role must be able to write before CloudTrail validates it.
  depends_on = [aws_iam_role_policy.trail_to_cloudwatch]
}
