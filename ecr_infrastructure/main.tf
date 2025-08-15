terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
  backend "s3" {}
}

module "ecr" {
  source = "./ecr"
}

module "secretsmanager" {
  source = "./secretsmanager"
  ecr_repository_url = module.ecr.boardgame_app_ecr_repository_url
}