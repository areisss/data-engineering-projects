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
  source       = "./modules/compute"
  project_name = var.project_name
  environment  = var.environment
  bucket_arn   = module.storage.bucket_arn
  dynamodb_arn = module.storage.photo_metadata_table_arn
}

module "analytics" {
  source       = "./modules/analytics"
  project_name = var.project_name
  environment  = var.environment
  bucket_id    = module.storage.bucket_id
  bucket_arn   = module.storage.bucket_arn
}
