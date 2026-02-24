variable "project_name" {
  description = "Project name prefix"
}

variable "environment" {
  description = "Deployment environment"
}

variable "bucket_id" {
  description = "S3 bucket name (used for S3 target paths)"
}

variable "bucket_arn" {
  description = "S3 bucket ARN (used for IAM policies)"
}
