output "cognito_user_pool_id" {
  description = "The ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.bgg_user_pool.id
}

output "cognito_user_pool_client_id" {
  description = "The ID of the Cognito User Pool Client"
  value       = aws_cognito_user_pool_client.bgg_user_pool_client.id
}

output "cognito_user_pool_issuer" {
  description = "The issuer URL for the Cognito User Pool (used for JWT authorizer)"
  value       = "https://cognito-idp.us-east-1.amazonaws.com/${aws_cognito_user_pool.bgg_user_pool.id}"
}
