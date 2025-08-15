terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
  backend "s3" {}
}

provider "aws" {
  access_key = var.aws_access_key
  secret_key = var.aws_secret_access_key
}

module "ecr" {
  source = "./ecr"
}