resource "aws_dynamodb_table" "bgg_user_preferences" {
  name         = "bgg-user-preferences"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  tags = {
    Environment = "production"
    Project     = "Boardgame-Recommender"
  }
}

resource "aws_dynamodb_table" "bgg_game_night_sessions" {
  name         = "bgg-game-night-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "creator_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  global_secondary_index {
    name            = "creator_id-created_at-index"
    hash_key        = "creator_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = {
    Environment = "production"
    Project     = "Boardgame-Recommender"
  }
}
