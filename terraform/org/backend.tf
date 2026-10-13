# Org stack: applied locally with the mgmt profile, never by the pipeline.
# State lives in the Hello World state bucket under its own key, read with
# the default (Hello World) profile.
terraform {
  backend "s3" {
    bucket       = "watchdog-tfstate-895196059907"
    key          = "org/terraform.tfstate"
    region       = "eu-north-1"
    encrypt      = true
    use_lockfile = true
    profile      = "default"
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
