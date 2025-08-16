output "bgg_game_scraper_ecr_url" {
  description = "URL of the ECR repository for bgg_game_scraper"
  value       = aws_ecr_repository.bgg_game_scraper_repo.repository_url
}

output "bgg_game_data_scraper_ecr_url" {
  description = "URL of the ECR repository for bgg_game_data_scraper"
  value       = aws_ecr_repository.bgg_game_data_scraper_repo.repository_url
}