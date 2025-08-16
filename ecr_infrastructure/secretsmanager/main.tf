resource "aws_secretsmanager_secret" "bgg_game_scraper_repository_url_secret" {
  name        = "bgg_game_scraper_repository_url"
  description = "Secret for ECR repository URL"
}

resource "aws_secretsmanager_secret_version" "bgg_game_scraper_repository_url_secret_version" {
  secret_id     = aws_secretsmanager_secret.bgg_game_scraper_repository_url_secret.id
  secret_string = var.bgg_game_scraper_ecr_url
}

resource "aws_secretsmanager_secret" "bgg_game_data_scraper_repository_url_secret" {
  name        = "bgg_game_data_scraper_repository_url"
  description = "Secret for ECR repository URL"
}

resource "aws_secretsmanager_secret_version" "bgg_game_data_scraper_repository_url_secret_version" {
  secret_id     = aws_secretsmanager_secret.bgg_game_data_scraper_repository_url_secret.id
  secret_string = var.bgg_game_data_scraper_ecr_url
}