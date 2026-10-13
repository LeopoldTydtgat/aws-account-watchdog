provider "aws" {
  region = "eu-north-1"

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
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      project    = "watchdog"
      owner      = "leopold"
      managed-by = "terraform"
    }
  }
}
