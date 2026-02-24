output "bucket_id" {
  value = data.aws_s3_bucket.main.id
}

output "bucket_arn" {
  value = data.aws_s3_bucket.main.arn
}

output "photo_metadata_table_name" {
  value = aws_dynamodb_table.photo_metadata.name
}

output "photo_metadata_table_arn" {
  value = aws_dynamodb_table.photo_metadata.arn
}
