output "glue_database_name" {
  value = aws_glue_catalog_database.main.name
}

output "athena_workgroup_name" {
  value = aws_athena_workgroup.main.name
}

output "glue_crawler_name" {
  value = aws_glue_crawler.whatsapp_silver.name
}

output "glue_job_name" {
  value = aws_glue_job.whatsapp_silver.name
}

output "glue_role_arn" {
  value = aws_iam_role.glue.arn
}

output "athena_query_messages_per_day_id" {
  value = aws_athena_named_query.messages_per_day.id
}

output "athena_query_top_senders_id" {
  value = aws_athena_named_query.top_senders.id
}
