# Terraform Deployment

This Terraform configuration deploys the OpenAI proxy with F5 AI Guardrails to AWS for testing. The infrastructure includes AWS App Runner for hosting, Secrets Manager for secure credential storage, and WAF for IP-based access control.

See the [main project README](../README.md) for application details and configuration options.

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) (>= 1.0)
- AWS CLI configured with appropriate credentials
- OpenAI API key
- F5 AI Guardrails API token and project ID
- Your public IP address (for WAF allowlist)

## Quick Start

1. **Create a `terraform.tfvars` file** with required variables:

```hcl
allowed_ip      = "1.2.3.4/32"  # Your IP address
openai_api_key  = "sk-..."      # Your OpenAI API key
openai_api_url  = "https://api.openai.com/v1"
openai_model    = "gpt-4"
openai_system_prompt = "You are a helpful assistant."

f5_api_token    = "your-f5-token"
f5_api_url      = "https://api.f5.com/v1"
f5_project_id   = "your-project-id"
f5_scan_prompt  = "true"
f5_scan_response = "true"
f5_redact_prompt = "false"
f5_redact_response = "false"

debug = "false"
```

2. **Initialize and apply**:

```bash
terraform init
terraform plan
terraform apply
```

3. **Get the application URL**:

```bash
terraform output app_url
```

The proxy will be accessible at the output URL, restricted to your IP address via WAF.

## Cleanup

```bash
terraform destroy
```
