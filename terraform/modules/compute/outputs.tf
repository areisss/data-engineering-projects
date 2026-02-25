output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}

output "lambda_role_name" {
  value = aws_iam_role.lambda.name
}

output "whatsapp_bronze_lambda_arn" {
  value = aws_lambda_function.whatsapp_bronze.arn
}

output "photo_processor_lambda_arn" {
  value = aws_lambda_function.photo_processor.arn
}

output "photos_api_url" {
  value = "${aws_api_gateway_stage.main.invoke_url}/photos"
}

output "whatsapp_api_url" {
  value = "${aws_api_gateway_stage.main.invoke_url}/chats"
}
