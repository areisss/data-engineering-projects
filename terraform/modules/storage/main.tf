# References the existing Amplify-managed S3 bucket without taking ownership.
# To migrate ownership to Terraform later:
#   terraform import module.storage.aws_s3_bucket.main <bucket-name>
data "aws_s3_bucket" "main" {
  bucket = var.existing_bucket_name
}

resource "aws_dynamodb_table" "photo_metadata" {
  name         = "${var.project_name}-photo-metadata-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "photo_id"

  attribute {
    name = "photo_id"
    type = "S"
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
