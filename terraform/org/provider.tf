# allowed_account_ids stops this stack ever running against the wrong account.
provider "aws" {
  region              = "eu-north-1"
  profile             = "mgmt"
  allowed_account_ids = ["815915547314"]

  default_tags {
    tags = {
      project    = "watchdog"
      owner      = "leopold"
      managed-by = "terraform"
    }
  }
}

# AWS records IAM and sign-in events in us-east-1, so security alarms live there.
provider "aws" {
  alias               = "us_east_1"
  region              = "us-east-1"
  profile             = "mgmt"
  allowed_account_ids = ["815915547314"]

  default_tags {
    tags = {
      project    = "watchdog"
      owner      = "leopold"
      managed-by = "terraform"
    }
  }
}
