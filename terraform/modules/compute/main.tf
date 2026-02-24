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

# ---------------------------------------------------------------------------
# Photo processor Lambda (Step 5)
# Pillow is cross-compiled for Amazon Linux 2023 (manylinux_2_28_x86_64)
# so the zip can be built on any OS without Docker.
# ---------------------------------------------------------------------------

resource "null_resource" "build_photo_processor" {
  triggers = {
    handler_hash = filemd5("${path.root}/lambdas/photo_processor/handler.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      python3 -m pip install pillow \
        --platform manylinux_2_28_x86_64 \
        --implementation cp \
        --python-version 312 \
        --abi cp312 \
        --only-binary=:all: \
        --target ${path.root}/lambdas/photo_processor/package \
        --upgrade --quiet && \
      cp ${path.root}/lambdas/photo_processor/handler.py \
         ${path.root}/lambdas/photo_processor/package/handler.py
    EOT
  }
}

data "archive_file" "photo_processor" {
  depends_on  = [null_resource.build_photo_processor]
  type        = "zip"
  source_dir  = "${path.root}/lambdas/photo_processor/package"
  output_path = "${path.root}/lambdas/photo_processor/handler.zip"
}

resource "aws_lambda_function" "photo_processor" {
  filename         = data.archive_file.photo_processor.output_path
  function_name    = "${var.project_name}-photo-processor-${var.environment}"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  source_code_hash = data.archive_file.photo_processor.output_base64sha256
  timeout          = 60
  memory_size      = 512

  environment {
    variables = {
      BUCKET_NAME = var.bucket_id
      TABLE_NAME  = var.dynamodb_table_name
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_lambda_permission" "s3_invoke_photo_processor" {
  statement_id  = "AllowS3InvokePhotoProcessor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.photo_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn
}
