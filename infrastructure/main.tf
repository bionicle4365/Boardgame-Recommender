terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

module "dynamodb" {
  source = "./dynamodb"
}

module "ses" {
  source      = "./ses"
  domain_name = "meeplemanifesto.com"
}

module "cognito" {
  source                 = "./cognito"
  ses_source_arn         = module.ses.ses_domain_identity_arn
  ses_from_email_address = "Boardgame Recommender <noreply@meeplemanifesto.com>"
}

module "sqs" {
  source                                    = "./sqs"
  data_sqs_queue_name                       = "bgg_game_data_scraper_queue"
  data_sqs_queue_visibility_timeout_seconds = module.lambda.bgg_game_data_scraper_lambda_timeout
  user_sqs_queue_name                       = "bgg_user_data_scraper_queue"
  user_sqs_queue_visibility_timeout_seconds = module.lambda.bgg_user_data_scraper_lambda_timeout
  s3_bucket_arn                             = module.s3.bucket_arn
}

module "lambda" {
  source                        = "./lambda"
  data_lambda_function_name     = "bgg_game_data_scraper"
  data_sqs_queue_url            = module.sqs.data_sqs_queue_url
  data_sqs_queue_arn            = module.sqs.data_sqs_queue_arn
  user_sqs_queue_arn            = module.sqs.user_sqs_queue_arn
  user_sqs_queue_url            = module.sqs.user_sqs_queue_url
  lambda_execution_role_arn     = module.iam.lambda_exec_role_arn
  user_lambda_function_name     = "bgg_user_data_scraper"
  bgg_api_token                 = var.bgg_api_token
  s3_bucket_name                = module.s3.bucket_name
  data_lambda_concurrency_limit = var.data_lambda_concurrency_limit
  user_lambda_concurrency_limit = var.user_lambda_concurrency_limit
  dynamodb_table_name           = module.dynamodb.dynamodb_table_name
  taste_analytics_sqs_queue_arn = module.sqs.taste_analytics_sqs_queue_arn
  bgg_game_data_scraper_ecr_url = module.ecr.bgg_game_data_scraper_ecr_url
  bgg_user_data_scraper_ecr_url = module.ecr.bgg_user_data_scraper_ecr_url
  bgg_recommender_ecr_url       = module.ecr.bgg_recommender_ecr_url
  bgg_compactor_ecr_url         = module.ecr.bgg_compactor_ecr_url
  bgg_taste_analytics_ecr_url   = module.ecr.bgg_taste_analytics_ecr_url
}

module "iam" {
  source                     = "./iam"
  lambda_execution_role_name = "bgg_game_data_scraper_role"
}

# module "glue" {
#   source = "./glue"
#   glue_database_name = "boardgame_app"
#   glue_raw_table_name = "boardgame_app_raw_table"
#   glue_combined_table_name = "boardgame_app_combined_table"
#   combine_glue_job_name = "boardgame_app_combine_job"
#   combine_glue_job_script_key = module.s3.combine_glue_job_script_key
#   glue_service_role_arn = module.iam.glue_service_role_arn
#   glue_user_raw_table_name = "boardgame_app_user_raw_table"
# }

module "s3" {
  source                        = "./s3"
  s3_bucket_name                = "boardgame-app"
  taste_analytics_sqs_queue_arn = module.sqs.taste_analytics_sqs_queue_arn
  # combine_glue_job_script_name = "combine_raw_to_single_file.py"
}


module "ecs" {
  source                   = "./ecs"
  s3_bucket_name           = module.s3.bucket_name
  s3_bucket_arn            = module.s3.bucket_arn
  sqs_queue_name           = module.sqs.data_sqs_queue_name
  sqs_queue_arn            = module.sqs.data_sqs_queue_arn
  bgg_api_token            = var.bgg_api_token
  bgg_game_scraper_ecr_url = module.ecr.bgg_game_scraper_ecr_url
}

module "eventbridge" {
  source                      = "./eventbridge"
  ecs_cluster_arn             = module.ecs.cluster_arn
  ecs_task_definition_arn     = module.ecs.task_definition_arn
  ecs_subnets                 = module.ecs.subnets
  ecs_security_group_id       = module.ecs.security_group_id
  ecs_task_execution_role_arn = module.ecs.ecs_task_execution_role_arn
  ecs_task_role_arn           = module.ecs.ecs_task_role_arn
  compactor_lambda_arn        = module.lambda.bgg_compactor_arn
  compactor_lambda_name       = module.lambda.bgg_compactor_function_name
  preview_refresh_lambda_arn  = module.lambda.bgg_preview_refresh_arn
  preview_refresh_lambda_name = module.lambda.bgg_preview_refresh_function_name
}

module "apigateway" {
  source = "./apigateway"

  cors_allowed_origins = var.cors_allowed_origins

  bgg_api_proxy_lambda_arn           = module.lambda.bgg_api_proxy_arn
  bgg_api_proxy_lambda_function_name = module.lambda.bgg_api_proxy_function_name
  bgg_recommender_lambda_arn         = module.lambda.bgg_recommender_arn
  bgg_recommender_lambda_function_name = module.lambda.bgg_recommender_function_name
  bgg_preferences_lambda_arn         = module.lambda.bgg_preferences_arn
  bgg_preferences_lambda_function_name = module.lambda.bgg_preferences_function_name

  cognito_user_pool_client_id = module.cognito.cognito_user_pool_client_id
  cognito_user_pool_issuer    = module.cognito.cognito_user_pool_issuer
}

