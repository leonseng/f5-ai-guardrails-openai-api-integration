resource "random_id" "suffix" {
  byte_length = 4
  keepers = {
    app_name = var.app_name
  }
}

locals {
  app_name   = "${var.app_name}-${random_id.suffix.hex}"
  allowed_ip = var.allowed_ip
}

###############################################################################
# Secrets Manager
###############################################################################

resource "aws_secretsmanager_secret" "openai_api_key" {
  name = "${local.app_name}/OPENAI_API_KEY"
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "f5_api_token" {
  name = "${local.app_name}/F5_AI_GUARDRAILS_API_TOKEN"
}

resource "aws_secretsmanager_secret_version" "f5_api_token" {
  secret_id     = aws_secretsmanager_secret.f5_api_token.id
  secret_string = var.f5_api_token
}

###############################################################################
# IAM - App Runner instance role (to read secrets)
###############################################################################

data "aws_iam_policy_document" "apprunner_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["tasks.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_instance_role" {
  name               = "${local.app_name}-instance-role"
  assume_role_policy = data.aws_iam_policy_document.apprunner_assume_role.json
}

data "aws_iam_policy_document" "secrets_read" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      aws_secretsmanager_secret.openai_api_key.arn,
      aws_secretsmanager_secret.f5_api_token.arn,
    ]
  }
}

resource "aws_iam_policy" "secrets_read" {
  name   = "${local.app_name}-secrets-read"
  policy = data.aws_iam_policy_document.secrets_read.json
}

resource "aws_iam_role_policy_attachment" "secrets_read" {
  role       = aws_iam_role.apprunner_instance_role.name
  policy_arn = aws_iam_policy.secrets_read.arn
}

###############################################################################
# IAM - App Runner access role (to pull image from ECR public / Docker Hub)
###############################################################################

data "aws_iam_policy_document" "apprunner_build_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apprunner_access_role" {
  name               = "${local.app_name}-access-role"
  assume_role_policy = data.aws_iam_policy_document.apprunner_build_assume_role.json
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_access_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

###############################################################################
# App Runner Service
###############################################################################

resource "aws_apprunner_service" "this" {
  service_name = local.app_name

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_access_role.arn
    }

    image_repository {
      image_identifier      = var.container_image
      image_repository_type = "ECR"

      image_configuration {
        port = var.container_port

        runtime_environment_variables = {
          OPENAI_API_URL                   = var.openai_api_url
          MODEL                            = var.openai_model
          SYSTEM_PROMPT                    = var.openai_system_prompt
          F5_AI_GUARDRAILS_API_URL         = var.f5_api_url
          F5_AI_GUARDRAILS_PROJECT_ID      = var.f5_project_id
          F5_AI_GUARDRAILS_SCAN_PROMPT     = var.f5_scan_prompt
          F5_AI_GUARDRAILS_SCAN_RESPONSE   = var.f5_scan_response
          F5_AI_GUARDRAILS_REDACT_PROMPT   = var.f5_redact_prompt
          F5_AI_GUARDRAILS_REDACT_RESPONSE = var.f5_redact_response
          DEBUG                            = var.debug
        }

        runtime_environment_secrets = {
          OPENAI_API_KEY             = aws_secretsmanager_secret.openai_api_key.arn
          F5_AI_GUARDRAILS_API_TOKEN = aws_secretsmanager_secret.f5_api_token.arn
        }
      }
    }

    auto_deployments_enabled = false
  }

  instance_configuration {
    cpu               = var.instance_cpu
    memory            = var.instance_memory
    instance_role_arn = aws_iam_role.apprunner_instance_role.arn
  }

  tags = {
    Name = local.app_name
  }
}

###############################################################################
# WAF - IP allowlist (us-east-1 required for App Runner WAF)
###############################################################################

resource "aws_wafv2_ip_set" "allowed" {
  name               = "${local.app_name}-allowed-ips"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = [local.allowed_ip]
}

resource "aws_wafv2_web_acl" "this" {
  name  = "${local.app_name}-acl"
  scope = "REGIONAL"

  default_action {
    block {}
  }

  rule {
    name     = "AllowMyIP"
    priority = 1

    action {
      allow {}
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.allowed.arn
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.app_name}-allow-my-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.app_name}-acl"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_apprunner_service.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}
