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

# ---------------------------------------------------------------------------
# Glue PySpark job (glueetl, Glue 4.0)
# Replaced Python Shell (pythonshell / 0.0625 DPU) with a PySpark job for
# typed schema enforcement, Snappy-compressed Parquet, and proper column stats.
# Cost: G.1X × 2 workers ≈ $0.07/run (~$2/month at one run per day).
# ---------------------------------------------------------------------------

resource "aws_glue_job" "whatsapp_silver" {
  name         = "${var.project_name}-whatsapp-silver-${var.environment}"
  role_arn     = aws_iam_role.glue.arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${var.bucket_id}/glue-scripts/whatsapp_silver/job.py"
    python_version  = "3"
  }

  default_arguments = {
    "--BUCKET_NAME"             = var.bucket_id
    "--GLUE_DATABASE"           = aws_glue_catalog_database.main.name
    "--enable-glue-datacatalog" = "true"
    "--enable-job-insights"     = "false"
  }

  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60

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

# Crawler targets silver/whatsapp/ and refreshes partition metadata.
# Runs one hour after the Glue job as a safety net for catalog drift.
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

# ---------------------------------------------------------------------------
# Athena named queries
# ---------------------------------------------------------------------------

resource "aws_athena_named_query" "messages_per_day" {
  name      = "whatsapp_messages_per_day"
  workgroup = aws_athena_workgroup.main.name
  database  = aws_glue_catalog_database.main.name
  query     = <<-SQL
    SELECT   date,
             COUNT(*)             AS message_count,
             COUNT(DISTINCT sender) AS active_senders
    FROM     whatsapp_messages
    GROUP BY date
    ORDER BY date DESC
  SQL
}

resource "aws_athena_named_query" "top_senders" {
  name      = "whatsapp_top_senders"
  workgroup = aws_athena_workgroup.main.name
  database  = aws_glue_catalog_database.main.name
  query     = <<-SQL
    SELECT   sender,
             COUNT(*)                                             AS message_count,
             ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total,
             AVG(word_count)                                      AS avg_words
    FROM     whatsapp_messages
    GROUP BY sender
    ORDER BY message_count DESC
    LIMIT    20
  SQL
}
