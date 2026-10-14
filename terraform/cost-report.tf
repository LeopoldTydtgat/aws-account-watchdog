# Phase 1: nightly cost report.
# Built step by step. Step 1: the table the report writes to.

# Provisioned 1/1 stays inside the always-free 25 RCU/WCU.
# On-demand has no free tier, so it is never used here.
resource "aws_dynamodb_table" "watchdog_data" {
  name           = "watchdog-data"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "pk"
  range_key      = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Free. Stops an accidental terraform destroy or console delete
  # from wiping the report history.
  deletion_protection_enabled = true
}