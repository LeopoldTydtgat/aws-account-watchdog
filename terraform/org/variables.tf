variable "alert_email" {
  description = "Address for security alerts. Set in terraform.tfvars (git-ignored)."
  type        = string
  sensitive   = true
}
