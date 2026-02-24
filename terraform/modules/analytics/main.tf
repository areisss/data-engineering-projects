data "aws_iam_policy_document" "glue_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.project_name}-glue-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_s3" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      var.bucket_arn,
      "${var.bucket_arn}/*",
    ]
  }
}

resource "aws_iam_policy" "glue_s3" {
  name   = "${var.project_name}-glue-s3-${var.environment}"
  policy = data.aws_iam_policy_document.glue_s3.json
}

resource "aws_iam_role_policy_attachment" "glue_s3" {
  role       = aws_iam_role.glue.name
  policy_arn = aws_iam_policy.glue_s3.arn
}

resource "aws_glue_catalog_database" "main" {
  name = "${var.project_name}_${var.environment}"
}

resource "aws_s3_object" "whatsapp_silver_script" {
  bucket = var.bucket_id
  key    = "glue-scripts/whatsapp_silver/job.py"
  source = "${path.root}/glue_jobs/whatsapp_silver/job.py"
  etag   = filemd5("${path.root}/glue_jobs/whatsapp_silver/job.py")
}

resource "aws_glue_job" "whatsapp_silver" {
  name         = "${var.project_name}-whatsapp-silver-${var.environment}"
  role_arn     = aws_iam_role.glue.arn
  glue_version = "3.0"

  command {
    name            = "pythonshell"
    script_location = "s3://${var.bucket_id}/glue-scripts/whatsapp_silver/job.py"
    python_version  = "3.9"
  }

  default_arguments = {
    "--BUCKET_NAME"               = var.bucket_id
    "--GLUE_DATABASE"             = aws_glue_catalog_database.main.name
    "--additional-python-modules" = "awswrangler"
    "--enable-job-insights"       = "false"
  }

  # 0.0625 DPU is the minimum for Python Shell (~$0.003/run at 5 min)
  max_capacity = 0.0625
  timeout      = 60

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Runs at 05:00 UTC daily, one hour before the crawler (06:00 UTC)
resource "aws_glue_trigger" "whatsapp_silver_daily" {
  name     = "${var.project_name}-whatsapp-silver-daily-${var.environment}"
  type     = "SCHEDULED"
  schedule = "cron(0 5 * * ? *)"

  actions {
    job_name = aws_glue_job.whatsapp_silver.name
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Crawler targets silver/whatsapp/ and registers the Parquet schema.
resource "aws_glue_crawler" "whatsapp_silver" {
  name          = "${var.project_name}-whatsapp-silver-${var.environment}"
  role          = aws_iam_role.glue.arn
  database_name = aws_glue_catalog_database.main.name

  s3_target {
    path = "s3://${var.bucket_id}/silver/whatsapp/"
  }

  # Runs daily at 06:00 UTC after the overnight Glue job
  schedule = "cron(0 6 * * ? *)"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_athena_workgroup" "main" {
  name = "${var.project_name}-${var.environment}"

  configuration {
    result_configuration {
      output_location = "s3://${var.bucket_id}/athena-results/"
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
