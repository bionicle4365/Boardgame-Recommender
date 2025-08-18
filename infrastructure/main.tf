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
  sqs_queue_visibility_timeout_seconds = module.lambda.bgg_game_data_scraper_lambda_timeout
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

module "glue" {
  source = "./glue"
  glue_database_name = "boardgame_app"
  glue_raw_table_name = "boardgame_app_raw_table"
  glue_combined_table_name = "boardgame_app_combined_table"
  combine_glue_job_name = "boardgame_app_combine_job"
  combine_glue_job_script_key = module.s3.combine_glue_job_script_key
  glue_service_role_arn = module.iam.glue_service_role_arn
}

module "s3" {
  source = "./s3"
  s3_bucket_name = "boardgame-app"
  combine_glue_job_script_name = "combine_raw_to_single_file.py"
}