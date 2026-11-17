# Phase 2, step 2: AWS Config, the detection layer for the security patrol.
# Config records every change to a security group and checks each one
# against a rule. The remediator (next step) acts on the result.
#
# Cost: Config is not free. Recording is scoped to security groups only
# (a handful of items) and one rule, so this is cents a month (D-019).

locals {
  config_bucket_name = "watchdog-config-${data.aws_caller_identity.current.account_id}"

  # Created once by hand (D-017). The pipeline role cannot read IAM roles
  # outside watchdog-*, so Terraform refers to it by ARN instead of managing it.
  config_service_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/config.amazonaws.com/AWSServiceRoleForConfig"
}

# ---------- Where Config writes its history ----------

resource "aws_s3_bucket" "config" {
  bucket = local.config_bucket_name
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket                  = aws_s3_bucket.config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "config" {
  bucket = aws_s3_bucket.config.id

  rule {
    id     = "expire-after-30-days"
    status = "Enabled"
    filter {}

    expiration {
      days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Only the Config service, acting for this account, may check and write
# to the bucket. Plain HTTP is refused.
resource "aws_s3_bucket_policy" "config" {
  bucket = aws_s3_bucket.config.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ConfigBucketChecks"
        Effect    = "Allow"
        Principal = { Service = "config.amazonaws.com" }
        Action    = ["s3:GetBucketAcl", "s3:ListBucket"]
        Resource  = aws_s3_bucket.config.arn
        Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
      },
      {
        Sid       = "ConfigDelivery"
        Effect    = "Allow"
        Principal = { Service = "config.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.config.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
            "s3:x-amz-acl"      = "bucket-owner-full-control"
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.config.arn, "${aws_s3_bucket.config.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}

# ---------- The recorder ----------

resource "aws_config_configuration_recorder" "main" {
  name     = "watchdog-recorder"
  role_arn = local.config_service_role_arn

  # Security groups only. Recording everything would bill for every
  # resource change in the account for no benefit to this project.
  recording_group {
    all_supported  = false
    resource_types = ["AWS::EC2::SecurityGroup"]
  }

  recording_mode {
    recording_frequency = "CONTINUOUS"
  }
}

resource "aws_config_delivery_channel" "main" {
  name           = "watchdog-delivery"
  s3_bucket_name = aws_s3_bucket.config.id

  depends_on = [aws_config_configuration_recorder.main, aws_s3_bucket_policy.config]
}

resource "aws_config_configuration_recorder_status" "main" {
  name       = aws_config_configuration_recorder.main.name
  is_enabled = true

  depends_on = [aws_config_delivery_channel.main]
}

# ---------- The rule ----------

# AWS managed rule: a security group is NON_COMPLIANT if it allows
# inbound TCP from 0.0.0.0/0 on any listed port. 22 is SSH, 3389 is RDP.
resource "aws_config_config_rule" "restricted_admin_ports" {
  name        = "watchdog-restricted-admin-ports"
  description = "Flags security groups open to the internet on SSH (22) or RDP (3389)"

  source {
    owner             = "AWS"
    source_identifier = "RESTRICTED_INCOMING_TRAFFIC"
  }

  input_parameters = jsonencode({
    blockedPort1 = "22"
    blockedPort2 = "3389"
  })

  scope {
    compliance_resource_types = ["AWS::EC2::SecurityGroup"]
  }

  depends_on = [aws_config_configuration_recorder_status.main]
}
