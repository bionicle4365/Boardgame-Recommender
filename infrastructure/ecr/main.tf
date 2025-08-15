resource "aws_ecr_repository" "boardgame_app_repo" {
  name                 = "boardgame-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

output "boardgame_app_ecr_repository_url" {
  description = "URL of the ECR repository for boardgame-app"
  value       = aws_ecr_repository.boardgame_app_repo.repository_url
}
