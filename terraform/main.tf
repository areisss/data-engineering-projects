provider "aws" {
  region = var.aws_region
}

module "storage" {
  source               = "./modules/storage"
  project_name         = var.project_name
  environment          = var.environment
  existing_bucket_name = var.existing_bucket_name
}

module "compute" {
  source                = "./modules/compute"
  project_name          = var.project_name
  environment           = var.environment
  bucket_id             = module.storage.bucket_id
  bucket_arn            = module.storage.bucket_arn
  dynamodb_arn          = module.storage.photo_metadata_table_arn
  dynamodb_table_name   = module.storage.photo_metadata_table_name
  cognito_user_pool_arn = var.cognito_user_pool_arn
}

# S3 bucket notifications are managed here (root module) to avoid conflicts
# when multiple Lambdas need triggers on the same bucket (added in steps 3 & 5).
resource "aws_s3_bucket_notification" "main" {
  bucket = module.storage.bucket_id

  lambda_function {
    lambda_function_arn = module.compute.whatsapp_bronze_lambda_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw-whatsapp-uploads/"
    filter_suffix       = ".txt"
  }

  lambda_function {
    lambda_function_arn = module.compute.photo_processor_lambda_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw-photos/"
  }

  depends_on = [module.compute]
}

module "analytics" {
  source       = "./modules/analytics"
  project_name = var.project_name
  environment  = var.environment
  bucket_id    = module.storage.bucket_id
  bucket_arn   = module.storage.bucket_arn
}
