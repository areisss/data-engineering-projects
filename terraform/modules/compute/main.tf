data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_s3_dynamodb" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.bucket_arn,
      "${var.bucket_arn}/*",
    ]
  }

  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [var.dynamodb_arn]
  }
}

resource "aws_iam_policy" "lambda_s3_dynamodb" {
  name   = "${var.project_name}-lambda-s3-dynamodb-${var.environment}"
  policy = data.aws_iam_policy_document.lambda_s3_dynamodb.json
}

resource "aws_iam_role_policy_attachment" "lambda_s3_dynamodb" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda_s3_dynamodb.arn
}

data "archive_file" "whatsapp_bronze" {
  type        = "zip"
  source_file = "${path.root}/lambdas/whatsapp_bronze/handler.py"
  output_path = "${path.root}/lambdas/whatsapp_bronze/handler.zip"
}

resource "aws_lambda_function" "whatsapp_bronze" {
  filename         = data.archive_file.whatsapp_bronze.output_path
  function_name    = "${var.project_name}-whatsapp-bronze-${var.environment}"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  source_code_hash = data.archive_file.whatsapp_bronze.output_base64sha256
  timeout          = 60
  memory_size      = 256

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_lambda_permission" "s3_invoke_whatsapp_bronze" {
  statement_id  = "AllowS3InvokeWhatsappBronze"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.whatsapp_bronze.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}

# Photo processing Lambda is added in Step 5.
