resource "aws_ecr_repository" "bgg_game_scraper_repo" {
  name                 = "bgg_game_scraper"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "bgg_game_data_scraper_repo" {
  name                 = "bgg_game_data_scraper"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
