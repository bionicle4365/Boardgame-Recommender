variable "cors_allowed_origins" {
  description = "Allowed origins for CORS configuration in API Gateway"
  type        = list(string)
}

variable "bgg_api_proxy_lambda_arn" {
  description = "The ARN of the bgg_api_proxy Lambda function (invoke URI)"
  type        = string
}

variable "bgg_api_proxy_lambda_function_name" {
  description = "The function name of the bgg_api_proxy Lambda"
  type        = string
}

variable "bgg_recommender_lambda_arn" {
  description = "The ARN of the bgg_recommender Lambda function (invoke URI)"
  type        = string
}

variable "bgg_recommender_lambda_function_name" {
  description = "The function name of the bgg_recommender Lambda"
  type        = string
}

variable "bgg_preferences_lambda_arn" {
  description = "The ARN of the bgg_preferences Lambda function (invoke URI)"
  type        = string
}

variable "bgg_preferences_lambda_function_name" {
  description = "The function name of the bgg_preferences Lambda"
  type        = string
}

variable "cognito_user_pool_client_id" {
  description = "The Cognito User Pool Client ID used for the JWT authorizer audience"
  type        = string
}

variable "cognito_user_pool_issuer" {
  description = "The issuer URL for the Cognito User Pool (used by the JWT authorizer)"
  type        = string
}
