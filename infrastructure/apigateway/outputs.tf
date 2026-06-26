output "api_gateway_url" {
  description = "The endpoint URL of the API Gateway"
  value       = aws_apigatewayv2_api.bgg_api.api_endpoint
}

output "api_gateway_execution_arn" {
  description = "The execution ARN of the API Gateway"
  value       = aws_apigatewayv2_api.bgg_api.execution_arn
}
