resource "aws_secretsmanager_secret" "ecr_repository_url_secret" {
  name        = "ecr_repository_url"
  description = "Secret for ECR repository URL"
}

resource "aws_secretsmanager_secret_version" "ecr_repository_url_secret_version" {
  secret_id     = aws_secretsmanager_secret.ecr_repository_url_secret.id
  secret_string = var.ecr_repository_url
}