# Phase 3, step 1b: the housekeeper function and its weekly schedule.
# Report only: it finds forgotten and untagged resources and emails a
# plain-English list. It never changes anything (D-021).

data "archive_file" "housekeeper" {
  type             = "zip"
  source_dir       = "${path.module}/../lambdas/housekeeper"
  output_path      = "${path.module}/build/housekeeper.zip"
  output_file_mode = "0644"
  excludes         = ["__pycache__", "__pycache__/**"]
}

# 256 MB from the start: Game Day 01 showed 128 MB is tight for boto3
# and doubles the run time for about the same cost.
resource "aws_lambda_function" "housekeeper" {
  function_name = local.housekeeper_name
  role          = aws_iam_role.housekeeper.arn
  handler       = "housekeeper.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 60

  filename         = data.archive_file.housekeeper.output_path
  source_code_hash = data.archive_file.housekeeper.output_base64sha256

  environment {
    variables = {
      TABLE_NAME            = aws_dynamodb_table.watchdog_data.name
      REPORT_EMAIL_PARAM    = "/watchdog/report-email"
      REQUIRED_TAGS         = "project,owner"
      SNAPSHOT_MAX_AGE_DAYS = "30"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.housekeeper.name
  }
}

# One retry, then give up, same as the cost reporter: a second failure is
# a real problem for the heartbeat alarm (Phase 4) to catch. A re-run is
# safe because the table key is the run date.
resource "aws_lambda_function_event_invoke_config" "housekeeper" {
  function_name                = aws_lambda_function.housekeeper.function_name
  maximum_retry_attempts       = 1
  maximum_event_age_in_seconds = 3600
}

# Mondays 04:30 UTC, which is 06:30 SAST, half an hour after the nightly
# cost report.
resource "aws_cloudwatch_event_rule" "housekeeper_weekly" {
  name                = "watchdog-housekeeper-weekly"
  description         = "Runs the Watchdog housekeeping report on Mondays at 06:30 SAST"
  schedule_expression = "cron(30 4 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "housekeeper_weekly" {
  rule = aws_cloudwatch_event_rule.housekeeper_weekly.name
  arn  = aws_lambda_function.housekeeper.arn
}

# Lets this one rule, and nothing else, invoke the function.
resource "aws_lambda_permission" "housekeeper_weekly" {
  statement_id  = "AllowWeeklySchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.housekeeper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.housekeeper_weekly.arn
}
