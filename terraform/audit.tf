# Audit layer (Hello World side).
# 1. S3 bucket that stores the organisation CloudTrail logs.
#    The trail itself is created in the management account (terraform/org).
# 2. IAM Access Analyzer for this account.
# 3. Break-glass alarm: any IAM permission change in this account emails me.

locals {
  management_account_id = "815915547314"
  organization_id       = "o-laqten2dhu"
  org_trail_arn         = "arn:aws:cloudtrail:eu-north-1:${local.management_account_id}:trail/watchdog-org-trail"

  # IAM actions that change who can do what. This account has no IAM users,
  # so user and access key creation are included: any of them is suspicious.
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

# ---------- CloudTrail log bucket ----------

resource "aws_s3_bucket" "trail" {
  bucket = "watchdog-cloudtrail-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "trail" {
  bucket = aws_s3_bucket.trail.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 (free). A customer-managed KMS key would cost about $1/month.
resource "aws_s3_bucket_server_side_encryption_configuration" "trail" {
  bucket = aws_s3_bucket.trail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "trail" {
  bucket     = aws_s3_bucket.trail.id
  depends_on = [aws_s3_bucket_versioning.trail]

  rule {
    id     = "expire-logs-after-30-days"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }

    # Deleted or overwritten logs stay recoverable for another 30 days.
    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  rule {
    id     = "clean-up-delete-markers"
    status = "Enabled"
    filter {}

    expiration {
      expired_object_delete_marker = true
    }
  }
}

# Only the organisation trail may write here, and only over HTTPS.
resource "aws_s3_bucket_policy" "trail" {
  bucket     = aws_s3_bucket.trail.id
  depends_on = [aws_s3_bucket_public_access_block.trail]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "CloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail.arn
        Condition = { StringEquals = { "aws:SourceArn" = local.org_trail_arn } }
      },
      {
        Sid       = "CloudTrailWriteManagementAccount"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail.arn}/AWSLogs/${local.management_account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl"  = "bucket-owner-full-control"
            "aws:SourceArn" = local.org_trail_arn
          }
        }
      },
      {
        Sid       = "CloudTrailWriteOrganisation"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail.arn}/AWSLogs/${local.organization_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl"  = "bucket-owner-full-control"
            "aws:SourceArn" = local.org_trail_arn
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.trail.arn, "${aws_s3_bucket.trail.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

# ---------- IAM Access Analyzer ----------

resource "aws_accessanalyzer_analyzer" "account" {
  analyzer_name = "watchdog-account-analyzer"
  type          = "ACCOUNT"
}

# ---------- Break-glass: IAM permission changes (us-east-1) ----------

resource "aws_sns_topic" "security_alerts" {
  provider = aws.us_east_1
  name     = "watchdog-security-alerts"
}

# The email subscription is added once by hand (aws sns subscribe), so my
# address never passes through the public pipeline. See DECISIONS.md.

resource "aws_cloudwatch_event_rule" "iam_changes" {
  provider    = aws.us_east_1
  name        = "watchdog-iam-changes"
  description = "Break-glass: any IAM permission change in this account"

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
      Sid       = "AllowEventBridgeRuleToPublish"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.security_alerts.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.iam_changes.arn } }
    }]
  })
}
