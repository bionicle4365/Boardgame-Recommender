resource "aws_ses_email_identity" "boardgame_app" {
  email = var.email_address
}

# Allow Cognito to send emails using this identity
data "aws_iam_policy_document" "ses_identity_policy" {
  statement {
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [aws_ses_email_identity.boardgame_app.arn]

    principals {
      type        = "Service"
      identifiers = ["cognito-idp.amazonaws.com"]
    }
  }
}

resource "aws_ses_identity_policy" "cognito_ses_policy" {
  identity = aws_ses_email_identity.boardgame_app.arn
  name     = "CognitoSendEmailPolicy"
  policy   = data.aws_iam_policy_document.ses_identity_policy.json
}
