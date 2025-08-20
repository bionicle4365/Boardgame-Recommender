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
  region = "us-east-1"
}

module "ecr" {
  source = "./ecr"
}

module "secretsmanager" {
  source = "./secretsmanager"
  bgg_game_data_scraper_ecr_url = module.ecr.bgg_game_data_scraper_ecr_url
  bgg_game_scraper_ecr_url = module.ecr.bgg_game_scraper_ecr_url
  bgg_user_data_scraper_ecr_url = module.ecr.bgg_user_data_scraper_ecr_url
}