terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
  backend "s3" {}
}

module "sqs" {
  source = "./modules/sqs"
  sqs_queue_name = "bgg_game_data_scraper_queue"
}

module "lambda" {
  source = "./modules/lambda"
  lambda_function_name = "bgg_game_data_scraper"
  sqs_queue_url = module.sqs.sqs_queue_url
  sqs_queue_arn = module.sqs.sqs_queue_arn
  lambda_execution_role_arn = module.iam.lambda_exec.arn
}

module "iam" {
  source = "./modules/iam"
  lambda_execution_role_name = "bgg_game_data_scraper_role"
}