output "dynamodb_table_name" {
  description = "The name of the DynamoDB table"
  value       = aws_dynamodb_table.bgg_user_preferences.name
}

output "dynamodb_table_arn" {
  description = "The ARN of the DynamoDB table"
  value       = aws_dynamodb_table.bgg_user_preferences.arn
}

output "dynamodb_cafes_table_name" {
  description = "The name of the Cafes DynamoDB table"
  value       = aws_dynamodb_table.bgg_cafes.name
}

output "dynamodb_cafes_table_arn" {
  description = "The ARN of the Cafes DynamoDB table"
  value       = aws_dynamodb_table.bgg_cafes.arn
}
