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
