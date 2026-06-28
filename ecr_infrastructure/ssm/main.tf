resource "aws_ssm_parameter" "bgg_game_scraper_repository_url" {
  name        = "/bgg/ecr/bgg_game_scraper_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_game_scraper_ecr_url
}

resource "aws_ssm_parameter" "bgg_game_data_scraper_repository_url" {
  name        = "/bgg/ecr/bgg_game_data_scraper_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_game_data_scraper_ecr_url
}

resource "aws_ssm_parameter" "bgg_user_data_scraper_repository_url" {
  name        = "/bgg/ecr/bgg_user_data_scraper_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_user_data_scraper_ecr_url
}

resource "aws_ssm_parameter" "bgg_recommender_repository_url" {
  name        = "/bgg/ecr/bgg_recommender_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_recommender_ecr_url
}

resource "aws_ssm_parameter" "bgg_compactor_repository_url" {
  name        = "/bgg/ecr/bgg_compactor_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_compactor_ecr_url
}

resource "aws_ssm_parameter" "bgg_taste_analytics_repository_url" {
  name        = "/bgg/ecr/bgg_taste_analytics_repository_url"
  description = "SSM Parameter for ECR repository URL"
  type        = "String"
  value       = var.bgg_taste_analytics_ecr_url
}


