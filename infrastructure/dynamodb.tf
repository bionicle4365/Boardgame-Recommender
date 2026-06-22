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

output "dynamodb_table_name" {
  description = "The name of the DynamoDB table"
  value       = aws_dynamodb_table.bgg_user_preferences.name
}
