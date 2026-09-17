resource "aws_ssm_parameter" "watchdog_canary" {
  name  = "/watchdog/canary"
  type  = "String"
  value = "phase-0-terraform-works"
}
