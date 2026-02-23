variable "aws_region" {
  description = "Primary AWS region for resources"
  type        = string
  default     = "ap-southeast-2"
}

variable "app_name" {
  description = "Application name used for resource naming"
  type        = string
  default     = "openai-proxy-with-f5-guardrails"
}

variable "allowed_ip" {
  description = "IP address or CIDR block allowed to access the application (e.g., 1.2.3.4/32)"
  type        = string
}

variable "container_image" {
  description = "Docker container image for the application"
  type        = string
  default     = "public.ecr.aws/docker/library/leonseng/openai-proxy-with-f5-guardrails:latest"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = string
  default     = "8000"
}

variable "instance_cpu" {
  description = "CPU units for App Runner instance (256 = 0.25 vCPU)"
  type        = string
  default     = "256"
}

variable "instance_memory" {
  description = "Memory for App Runner instance in MB (512 = 0.5 GB)"
  type        = string
  default     = "512"
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "openai_api_url" {
  description = "OpenAI API URL"
  type        = string
}

variable "openai_model" {
  description = "OpenAI model to use"
  type        = string
}

variable "openai_system_prompt" {
  description = "System prompt for OpenAI"
  type        = string
}

variable "f5_api_token" {
  description = "F5 AI Guardrails API token"
  type        = string
  sensitive   = true
}

variable "f5_api_url" {
  description = "F5 AI Guardrails API URL"
  type        = string
}

variable "f5_project_id" {
  description = "F5 AI Guardrails project ID"
  type        = string
}

variable "f5_scan_prompt" {
  description = "Enable/disable F5 AI Guardrails prompt scanning"
  type        = string
}

variable "f5_scan_response" {
  description = "Enable/disable F5 AI Guardrails response scanning"
  type        = string
}

variable "f5_redact_prompt" {
  description = "Enable/disable F5 AI Guardrails prompt redaction"
  type        = string
}

variable "f5_redact_response" {
  description = "Enable/disable F5 AI Guardrails response redaction"
  type        = string
}

variable "debug" {
  description = "Enable/disable debug mode"
  type        = string
}
