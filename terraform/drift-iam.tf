# Phase 3, step 2a: a read-only role for the nightly drift check.
#
# The drift check runs terraform plan every night with nobody watching.
# It only needs to read, so it gets its own role instead of borrowing the
# deploy role (D-022). The workflow file comes in a later PR, so this
# role exists before anything tries to use it.

resource "aws_iam_role" "github_drift" {
  name = "watchdog-github-drift"

  # Only jobs in this repo's drift-check environment may use this role.
  # The deploy role trusts main and production; this one trusts neither.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:LeopoldTydtgat@272191895/aws-account-watchdog@1373360883:environment:drift-check"
        }
      }
    }]
  })
}

# terraform plan only reads: it refreshes every resource and reads the
# state file. The workflow runs plan with -lock=false, so it never writes
# the lock file in the state bucket either.
#
# Blast radius if these credentials leak: read most of the account's
# configuration and the state file. No changes of any kind. ReadOnlyAccess
# does not include kms:Decrypt, so SecureString parameters stay unreadable.
resource "aws_iam_role_policy_attachment" "drift_read_only" {
  role       = aws_iam_role.github_drift.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}
