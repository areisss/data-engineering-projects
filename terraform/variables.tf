variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as a prefix for all resources"
  default     = "data-engineering"
}

variable "environment" {
  description = "Deployment environment"
  default     = "dev"
}

variable "existing_bucket_name" {
  description = "Name of the existing Amplify-managed S3 bucket"
  default     = "mycloudstorage23f6ba8ba38b482a89d1456b9da085d23f14b-dev"
}
