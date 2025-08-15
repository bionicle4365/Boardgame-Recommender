resource "aws_ecr_repository" "boardgame_app_repo" {
  name                 = "boardgame-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}


