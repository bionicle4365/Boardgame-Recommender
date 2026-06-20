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
