# One organisation-wide trail: covers all three accounts and every region,
# and sees root activity. Logs go to the bucket in Hello World (Part A).
resource "aws_cloudtrail" "org" {
  name                          = "watchdog-org-trail"
  s3_bucket_name                = "watchdog-cloudtrail-895196059907"
  is_organization_trail         = true
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
}
