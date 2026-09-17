terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "watchdog-tfstate-895196059907"
    key          = "watchdog/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
