variable "project_name" {
  description = "Project name prefix"
}

variable "environment" {
  description = "Deployment environment"
}

variable "bucket_arn" {
  description = "ARN of the S3 bucket Lambdas need access to"
}

variable "dynamodb_arn" {
  description = "ARN of the DynamoDB PhotoMetadata table"
}

variable "bucket_id" {
  description = "S3 bucket name (used for S3 notification filter and Lambda env var)"
}

variable "dynamodb_table_name" {
  description = "DynamoDB PhotoMetadata table name (injected into photo processor Lambda)"
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool used to authorize the API Gateway"
}

variable "athena_database" {
  description = "Glue/Athena database name containing the whatsapp_messages table"
}

variable "athena_workgroup" {
  description = "Athena workgroup name to use for query execution"
}
