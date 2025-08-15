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

module "sqs" {
  source = "./sqs"
  sqs_queue_name = "bgg_game_data_scraper_queue"
}

module "lambda" {
  source = "./lambda"
  lambda_function_name = "bgg_game_data_scraper"
  sqs_queue_url = module.sqs.sqs_queue_url
  sqs_queue_arn = module.sqs.sqs_queue_arn
  lambda_execution_role_arn = module.iam.lambda_exec_role_arn
}

module "iam" {
  source = "./iam"
  lambda_execution_role_name = "bgg_game_data_scraper_role"
}