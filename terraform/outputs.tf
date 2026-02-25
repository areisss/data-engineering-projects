output "photo_metadata_table_name" {
  description = "DynamoDB table name for photo metadata"
  value       = module.storage.photo_metadata_table_name
}

output "athena_workgroup_name" {
  description = "Athena workgroup name"
  value       = module.analytics.athena_workgroup_name
}

output "glue_database_name" {
  description = "Glue catalog database name"
  value       = module.analytics.glue_database_name
}

output "lambda_role_arn" {
  description = "IAM role ARN for Lambda functions"
  value       = module.compute.lambda_role_arn
}

output "glue_job_name" {
  description = "Glue job name for the WhatsApp silver transformation"
  value       = module.analytics.glue_job_name
}

output "photos_api_url" {
  description = "Base URL for the Photos REST API (GET /photos requires Cognito JWT)"
  value       = module.compute.photos_api_url
}

output "whatsapp_api_url" {
  description = "Base URL for the WhatsApp Messages REST API (GET /chats requires Cognito JWT)"
  value       = module.compute.whatsapp_api_url
}
