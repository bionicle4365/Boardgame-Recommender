resource "aws_apigatewayv2_api" "bgg_api" {
  name          = "bgg-api-gateway"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins  = var.cors_allowed_origins
    allow_methods  = ["GET", "POST", "OPTIONS"]
    allow_headers  = ["content-type", "authorization"]
    expose_headers = ["content-encoding"]
    max_age        = 300
  }
}

resource "aws_apigatewayv2_stage" "bgg_api_stage" {
  api_id      = aws_apigatewayv2_api.bgg_api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
}

resource "aws_apigatewayv2_integration" "bgg_api_proxy_integration" {
  api_id           = aws_apigatewayv2_api.bgg_api.id
  integration_type = "AWS_PROXY"

  integration_uri        = var.bgg_api_proxy_lambda_arn
  integration_method     = "POST"
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

  integration_uri        = var.bgg_recommender_lambda_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "bgg_recommender_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "GET /recommendations"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_recommender_integration.id}"
}

resource "aws_apigatewayv2_route" "bgg_recommender_post_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "POST /recommendations"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_recommender_integration.id}"
}

resource "aws_apigatewayv2_route" "bgg_profile_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "GET /profile"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_recommender_integration.id}"
}

resource "aws_apigatewayv2_route" "bgg_conventions_route" {
  api_id    = aws_apigatewayv2_api.bgg_api.id
  route_key = "GET /conventions"
  target    = "integrations/${aws_apigatewayv2_integration.bgg_recommender_integration.id}"
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.bgg_api_proxy_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bgg_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_recommender" {
  statement_id  = "AllowRecommenderExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.bgg_recommender_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bgg_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_authorizer" "cognito_authorizer" {
  api_id           = aws_apigatewayv2_api.bgg_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-authorizer"

  jwt_configuration {
    audience = [var.cognito_user_pool_client_id]
    issuer   = var.cognito_user_pool_issuer
  }
}

resource "aws_apigatewayv2_integration" "bgg_preferences_integration" {
  api_id           = aws_apigatewayv2_api.bgg_api.id
  integration_type = "AWS_PROXY"

  integration_uri        = var.bgg_preferences_lambda_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "bgg_get_preferences_route" {
  api_id             = aws_apigatewayv2_api.bgg_api.id
  route_key          = "GET /preferences"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
  target             = "integrations/${aws_apigatewayv2_integration.bgg_preferences_integration.id}"
}

resource "aws_apigatewayv2_route" "bgg_post_preferences_route" {
  api_id             = aws_apigatewayv2_api.bgg_api.id
  route_key          = "POST /preferences"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_authorizer.id
  target             = "integrations/${aws_apigatewayv2_integration.bgg_preferences_integration.id}"
}

resource "aws_lambda_permission" "apigw_preferences" {
  statement_id  = "AllowPreferencesExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.bgg_preferences_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.bgg_api.execution_arn}/*/*"
}
