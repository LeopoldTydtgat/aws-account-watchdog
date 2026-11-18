# Phase 2, step 3b: the security-group remediator and the EventBridge
# rule that wakes it when Config marks a security group NON_COMPLIANT.
# Stage 1: DRY_RUN is on. It alerts and logs, it changes nothing (D-020).

data "archive_file" "sg_remediator" {
  type             = "zip"
  source_dir       = "${path.module}/../lambdas/sg_remediator"
  output_path      = "${path.module}/build/sg_remediator.zip"
  output_file_mode = "0644"
  excludes         = ["__pycache__", "__pycache__/**"]
}

resource "aws_lambda_function" "sg_remediator" {
  function_name = local.sg_remediator_name
  role          = aws_iam_role.sg_remediator.arn
  handler       = "remediator.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 30

  filename         = data.archive_file.sg_remediator.output_path
  source_code_hash = data.archive_file.sg_remediator.output_base64sha256

  environment {
    variables = {
      DRY_RUN            = "true"
      TABLE_NAME         = aws_dynamodb_table.watchdog_data.name
      REPORT_EMAIL_PARAM = "/watchdog/report-email"
      CONFIG_RULE_NAME   = aws_config_config_rule.restricted_admin_ports.name
      # Same ports the Config rule checks, read from the rule itself so
      # the two can never disagree.
      BLOCKED_PORTS = join(",", values(jsondecode(aws_config_config_rule.restricted_admin_ports.input_parameters)))
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.sg_remediator.name
  }
}

# Two retries, then the event goes to the dead-letter queue with the
# error attached. Retries are safe: a repeat of the same Config verdict
# is detected and skipped (idempotency check in the code).
resource "aws_lambda_function_event_invoke_config" "sg_remediator" {
  function_name                = aws_lambda_function.sg_remediator.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600

  destination_config {
    on_failure {
      destination = aws_sqs_queue.sg_remediator_dlq.arn
    }
  }
}

# Only NON_COMPLIANT results from this one rule. COMPLIANT results and
# other rules never reach the function.
resource "aws_cloudwatch_event_rule" "sg_noncompliant" {
  name        = "watchdog-sg-noncompliant"
  description = "Config found a security group open to the internet on an admin port"

  event_pattern = jsonencode({
    source        = ["aws.config"]
    "detail-type" = ["Config Rules Compliance Change"]
    detail = {
      messageType         = ["ComplianceChangeNotification"]
      configRuleName      = [aws_config_config_rule.restricted_admin_ports.name]
      newEvaluationResult = { complianceType = ["NON_COMPLIANT"] }
    }
  })
}

# If EventBridge itself cannot deliver to the function (for example a
# permission problem), the event goes to the same dead-letter queue.
resource "aws_cloudwatch_event_target" "sg_noncompliant" {
  rule = aws_cloudwatch_event_rule.sg_noncompliant.name
  arn  = aws_lambda_function.sg_remediator.arn

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 3
  }

  dead_letter_config {
    arn = aws_sqs_queue.sg_remediator_dlq.arn
  }
}

resource "aws_lambda_permission" "sg_noncompliant" {
  statement_id  = "AllowConfigNonCompliantRule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sg_remediator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sg_noncompliant.arn
}

# Lambda writes failures to the queue with the function's own role.
# EventBridge needs this queue policy instead: only this rule may send,
# and only over HTTPS.
resource "aws_sqs_queue_policy" "sg_remediator_dlq" {
  queue_url = aws_sqs_queue.sg_remediator_dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowRuleDeliveryFailures"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.sg_remediator_dlq.arn
        Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.sg_noncompliant.arn } }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.sg_remediator_dlq.arn
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      }
    ]
  })
}
