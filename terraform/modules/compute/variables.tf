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
