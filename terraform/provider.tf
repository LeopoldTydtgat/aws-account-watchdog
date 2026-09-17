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
