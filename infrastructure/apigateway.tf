resource "aws_apigatewayv2_api" "bgg_api" {
  name          = "bgg-api-gateway"
  protocol_type = "HTTP"
  
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "bgg_api_stage" {
  api_id      = aws_apigatewayv2_api.bgg_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "bgg_api_proxy_integration" {
  api_id           = aws_apigatewayv2_api.bgg_api.id
  integration_type = "AWS_PROXY"

  integration_uri    = module.lambda.bgg_api_proxy_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "bgg_api_proxy_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "GET /collection"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_api_proxy_integration.id}"
}

resource "aws_apigatewayv2_integration" "bgg_recommender_integration" {
  api_id           = aws_apigatewayv2_api.bgg_api.id
  integration_type = "AWS_PROXY"

  integration_uri    = module.lambda.bgg_recommender_arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "bgg_recommender_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "GET /recommendations"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_recommender_integration.id}"
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.bgg_api_proxy_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bgg_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_recommender" {
  statement_id  = "AllowRecommenderExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.bgg_recommender_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bgg_api.execution_arn}/*/*"
}

output "api_gateway_url" {
  description = "The endpoint URL of the API Gateway"
  value       = aws_apigatewayv2_api.bgg_api.api_endpoint
}
