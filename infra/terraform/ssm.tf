# ---------------------------------------------------------------------
#  Secrets in SSM Parameter Store -> scripts/fetch-env.sh -> /opt/cloudvote/.env
#  Passwords are generated here; nobody types or commits them.
#  Read the admin password with:
#    aws ssm get-parameter --name /cloudvote/prod/ADMIN_PASSWORD --with-decryption --query Parameter.Value --output text
#  NOTE: Terraform state contains these values – keep state private.
# ---------------------------------------------------------------------
resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "random_password" "admin" {
  length  = 20
  special = false
}

locals {
  ssm_prefix = "/${var.project}/${var.environment}"
  app_settings = {
    SECRET_KEY        = { value = random_password.secret_key.result, secure = true }
    POSTGRES_PASSWORD = { value = random_password.postgres.result, secure = true }
    REDIS_PASSWORD    = { value = random_password.redis.result, secure = true }
    ADMIN_PASSWORD    = { value = "${random_password.admin.result}9a", secure = true } # letter + digit guaranteed
    POSTGRES_USER     = { value = "voting", secure = false }
    POSTGRES_DB       = { value = "voting", secure = false }
    ADMIN_USERNAME    = { value = var.admin_username, secure = false }
    LOG_LEVEL         = { value = "INFO", secure = false }
    SEED_DEMO_POLL    = { value = "true", secure = false }
  }
}

resource "aws_ssm_parameter" "app" {
  for_each = local.app_settings
  name     = "${local.ssm_prefix}/${each.key}"
  type     = each.value.secure ? "SecureString" : "String"
  value    = each.value.value
}
