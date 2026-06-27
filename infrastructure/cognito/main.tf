resource "aws_cognito_user_pool" "bgg_user_pool" {
  name = "bgg-recommender-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = var.ses_source_arn
    from_email_address    = var.ses_from_email_address
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your Boardgame Recommender Verification Code"
    email_message        = <<-EOT
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: 'Inter', sans-serif; background-color: #1a1a1a; color: #ffffff; padding: 20px; text-align: center; }
          .container { max-width: 600px; margin: 0 auto; background-color: #2d2d2d; border-radius: 8px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
          h1 { color: #8b5cf6; margin-bottom: 20px; }
          p { font-size: 16px; line-height: 1.5; color: #d1d5db; }
          .code-box { background-color: #1a1a1a; border: 1px solid #4b5563; border-radius: 6px; padding: 15px; font-size: 24px; letter-spacing: 4px; font-weight: bold; color: #a78bfa; margin: 30px 0; display: inline-block; }
          .footer { margin-top: 30px; font-size: 12px; color: #6b7280; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>Welcome to Boardgame Recommender!</h1>
          <p>We're thrilled to have you join our community. To complete your signup and verify your email address, please use the code below:</p>
          <div class="code-box">{####}</div>
          <p>If you didn't request this email, you can safely ignore it.</p>
          <div class="footer">Boardgame Recommender &copy; 2026</div>
        </div>
      </body>
      </html>
    EOT
  }

  schema {
    attribute_data_type      = "String"
    developer_only_attribute = false
    mutable                  = true
    name                     = "email"
    required                 = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }
}

resource "aws_cognito_user_pool_client" "bgg_user_pool_client" {
  name         = "bgg-recommender-client"
  user_pool_id = aws_cognito_user_pool.bgg_user_pool.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
}
