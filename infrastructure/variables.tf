variable "bgg_api_token" {
  description = "The authorization token for the BGG API"
  type        = string
  default     = ""
  sensitive   = true
}

variable "data_lambda_concurrency_limit" {
  description = "Reserved concurrent executions limit for the game data scraper Lambda"
  type        = number
  default     = 2
}

variable "user_lambda_concurrency_limit" {
  description = "Reserved concurrent executions limit for the user collection scraper Lambda"
  type        = number
  default     = 2
}

variable "cors_allowed_origins" {
  description = "Allowed origins for CORS configuration in API Gateway"
  type        = list(string)
  default     = [
    "https://bionicle4365.github.io",
    "http://localhost:4000",
    "http://127.0.0.1:4000"
  ]
}
