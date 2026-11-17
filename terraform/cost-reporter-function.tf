# Phase 1, step 3: the cost-reporter function and its nightly schedule.

# Zips the function code at plan time. Tests are not shipped.
# output_file_mode pins file permissions so Windows and Linux build the
# same zip, otherwise every plan from a different machine shows a change.
data "archive_file" "cost_reporter" {
  type             = "zip"
  source_dir       = "${path.module}/../lambdas/cost_reporter"
  output_path      = "${path.module}/build/cost_reporter.zip"
  output_file_mode = "0644"
  excludes         = ["__pycache__", "__pycache__/**"]
}

resource "aws_lambda_function" "cost_reporter" {
  function_name = local.cost_reporter_name
  role          = aws_iam_role.cost_reporter.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  memory_size   = 128
  timeout       = 60

  filename         = data.archive_file.cost_reporter.output_path
  source_code_hash = data.archive_file.cost_reporter.output_base64sha256

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.watchdog_data.name
      REPORT_EMAIL_PARAM = "/watchdog/report-email"
      TARGET_MONTHLY_USD = "1.50"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.cost_reporter.name
  }
}

# One retry, then give up: a second failure is a real problem and the
# heartbeat alarm (Phase 4) is what should catch it, not endless retries.
# Rewriting a day is safe because the table key is the date.
resource "aws_lambda_function_event_invoke_config" "cost_reporter" {
  function_name                = aws_lambda_function.cost_reporter.function_name
  maximum_retry_attempts       = 1
  maximum_event_age_in_seconds = 3600
}

# 04:00 UTC is 06:00 SAST. South Africa has no daylight saving, so this
# never drifts. By then Cost Explorer has most of yesterday.
resource "aws_cloudwatch_event_rule" "cost_report_nightly" {
  name                = "watchdog-cost-report-nightly"
  description         = "Runs the Watchdog cost report at 06:00 SAST"
  schedule_expression = "cron(0 4 * * ? *)"
}

resource "aws_cloudwatch_event_target" "cost_report_nightly" {
  rule = aws_cloudwatch_event_rule.cost_report_nightly.name
  arn  = aws_lambda_function.cost_reporter.arn
}

# Lets this one rule, and nothing else, invoke the function.
resource "aws_lambda_permission" "cost_report_nightly" {
  statement_id  = "AllowNightlySchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_reporter.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cost_report_nightly.arn
}
