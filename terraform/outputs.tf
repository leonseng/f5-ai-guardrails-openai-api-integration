output "app_url" {
  value = "https://${aws_apprunner_service.this.service_url}"
}
