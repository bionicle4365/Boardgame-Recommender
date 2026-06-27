resource "aws_ses_domain_identity" "boardgame_app" {
  domain = var.domain_name
}

resource "aws_ses_domain_dkim" "boardgame_app" {
  domain = aws_ses_domain_identity.boardgame_app.domain
}

# Allow Cognito to send emails using this identity
data "aws_iam_policy_document" "ses_identity_policy" {
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [aws_ses_domain_identity.boardgame_app.arn]

    principals {
      type        = "Service"
      identifiers = ["cognito-idp.amazonaws.com"]
    }
  }
}

resource "aws_ses_identity_policy" "cognito_ses_policy" {
  identity = aws_ses_domain_identity.boardgame_app.arn
  name     = "CognitoSendEmailPolicy"
  policy   = data.aws_iam_policy_document.ses_identity_policy.json
}
