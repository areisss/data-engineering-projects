# Personal Cloud Data Platform — Engineering Deep Dive

> A self-contained mini-course using `areisss/data-engineering-projects` as the case study.
> Follow this to rebuild, understand, and extend every layer of the system from scratch.

---

## Introduction

This document is a structured learning path for re-building this project from zero in a blank AWS account. It is written for someone who already understands SQL and Python but is new to building cloud-native infrastructure, event-driven pipelines, and React frontends end-to-end.

Each module follows the same pattern:

- **Concepts** — the theory you need, grounded in this project
- **Lab** — concrete steps to build the thing from scratch
- **Trade-offs** — explicit design critiques and alternatives
- **Exercises** — hands-on tasks with clear success criteria
- **Check-yourself questions** — for self-assessment

Work through the modules in order. Each one builds on the previous.

---

## Architecture Overview

Before diving into modules, you need a mental map of the whole system.

### AWS Services in Use

| Service | Role |
|---|---|
| **S3** | Single bucket: raw uploads, bronze/silver data layers, processed photos, Athena results, Glue scripts, static website |
| **Lambda** | Four event-driven functions: WhatsApp validator, photo processor, photos API, chats API |
| **API Gateway** | REST API: `GET /photos` and `GET /chats`, both Cognito-authorized |
| **DynamoDB** | `PhotoMetadata` table: one item per photo, stores EXIF, dimensions, S3 keys |
| **Glue** | PySpark job to parse raw WhatsApp text into Parquet; Glue Catalog as the metastore |
| **Athena** | Serverless SQL over Parquet (the silver layer); named queries pre-configured |
| **Cognito** | User Pool for authentication (Amplify-managed); ID token passed to API Gateway |
| **IAM** | One Lambda role, one Glue role; scoped to the single S3 bucket |
| **CloudWatch** | Automatic Lambda logs |

### How the Services Connect

```
Browser (React + Amplify)
  │
  ├─ Amplify Storage (uploadData) ──► S3 raw-photos/           ──► Lambda: photo_processor
  │                                     raw-whatsapp-uploads/   ──► Lambda: whatsapp_bronze
  │                                     misc/, uploads-landing/
  │
  ├─ Amplify Storage (list/getUrl) ◄── S3 misc/, uploads-landing/
  │
  ├─ fetch (GET /photos)  ──► API Gateway ──► Lambda: photos_api  ──► DynamoDB + S3 pre-signed URLs
  │
  └─ fetch (GET /chats)   ──► API Gateway ──► Lambda: whatsapp_api ──► Athena ──► S3 silver/
                                                                                     (Glue Catalog)
```

All API calls carry a Cognito ID token in the `Authorization` header. The Cognito User Pool validates the token before the Lambda is invoked.

### High-Level Data Flows

**WhatsApp chat pipeline (bronze → silver → queryable)**

```
1. User exports WhatsApp chat as .txt
2. Uploads via React → raw-whatsapp-uploads/export.txt
3. S3 event triggers whatsapp_bronze Lambda
   → validates format (≥2 WhatsApp-style timestamp lines)
   → copies to bronze/whatsapp/year=2024/month=03/export.txt
4. Glue PySpark job (manual or scheduled daily at 05:00 UTC)
   → reads all bronze .txt files
   → parses date/time/sender/message with regex
   → writes date-partitioned Parquet to silver/whatsapp/
   → registers whatsapp_messages table in Glue Catalog
5. Athena query via whatsapp_api Lambda
   → SELECT ... FROM whatsapp_messages WHERE sender LIKE '%Alice%'
   → returns JSON array to React
```

**Photo pipeline (upload → thumbnail → queryable gallery)**

```
1. User uploads .jpg → raw-photos/photo.jpg
2. S3 event triggers photo_processor Lambda (512 MB RAM, Pillow bundled)
   → copies original to photos/originals/photo.jpg
   → resizes to ≤300px thumbnail → photos/thumbnails/photo.jpg
   → extracts EXIF (taken_at, camera, GPS, flash)
   → derives tags: landscape/portrait/square, flash, gps
   → writes item to DynamoDB PhotoMetadata
3. React PhotosPage fetches GET /photos
   → photos_api scans DynamoDB
   → generates pre-signed S3 URLs (thumbnail: 1h, original: 24h)
   → returns sorted JSON to React
4. React renders thumbnail grid grouped by year-month
```

### How Terraform Is Organized

```
terraform/
├── bootstrap/          # one-time: creates the S3 state bucket + DynamoDB lock table
├── versions.tf         # Terraform version, AWS provider version, S3 backend config
├── variables.tf        # region, project_name, environment, bucket name, Cognito ARN
├── main.tf             # calls modules + wires S3 bucket notifications
├── outputs.tf          # surfaces API URLs, table names for CI/CD to consume
└── modules/
    ├── storage/        # DynamoDB table; references S3 bucket as a data source
    ├── compute/        # 4 Lambdas + API Gateway + IAM roles + permissions
    └── analytics/      # Glue job + crawler + Athena workgroup + named queries
```

The root `main.tf` is the *director* — it calls the three modules, passes values between them, and adds the S3 bucket notification rules that connect S3 events to specific Lambdas. Modules are self-contained; they declare their inputs as `variable` blocks and expose their outputs as `output` blocks.

---

## Module 1 — Terraform and AWS Foundations

### Concepts

#### What Terraform Does

Terraform is an Infrastructure-as-Code (IaC) tool. You describe the desired state of your AWS resources in `.tf` files; Terraform figures out what to create, update, or destroy to reach that state.

The core workflow is:

```
terraform init     # download providers, configure backend
terraform plan     # show the diff (what will change)
terraform apply    # make the changes
terraform destroy  # tear everything down
```

#### State

Terraform tracks what it has created in a **state file** (`terraform.tfstate`). Without state, Terraform cannot know that the S3 bucket named `my-bucket` it sees in AWS is the same bucket it previously created — it would try to create another one.

In this project the state file lives in S3 (remote state), not on your laptop:

```hcl
# terraform/versions.tf
terraform {
  backend "s3" {
    bucket         = "artur-file-processor-tf-state"
    key            = "data-engineering/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

The DynamoDB table prevents two people (or two CI runs) from applying at the same time. Each `terraform apply` writes a lock to DynamoDB before touching state; it removes the lock when done.

**Critical rule**: never edit `terraform.tfstate` manually. If it gets out of sync with reality, use `terraform import` to reconcile.

#### Variables, Locals, and Outputs

```hcl
variable "project_name" {
  default = "data-engineering"
}

locals {
  prefix = "${var.project_name}-${var.environment}"
}

output "photos_api_url" {
  value = module.compute.photos_api_url
}
```

- **Variables** are inputs to a module or root config. They can have defaults.
- **Locals** are computed values used within one file (no defaults, not inputs).
- **Outputs** expose values to the caller or to `terraform output` on the CLI.

CI/CD uses `terraform output -raw photos_api_url` to get the API URL and set it as a GitHub secret.

#### Modules

A module is just a directory with `.tf` files. You call it with:

```hcl
module "storage" {
  source       = "./modules/storage"
  project_name = var.project_name
  environment  = var.environment
}
```

The module receives values through its declared `variable` blocks and returns values through `output` blocks. The caller accesses outputs as `module.storage.photo_table_name`.

Modules are good because:
- They have a defined interface (inputs/outputs), hiding implementation detail.
- You can reuse them for different environments (`dev`, `prod`) by passing different variables.
- They keep `main.tf` readable — the root just orchestrates; modules do the real work.

#### Data Sources vs Resources

A `resource` creates something. A `data` source reads something that already exists:

```hcl
# This creates a new bucket (Terraform owns it)
resource "aws_s3_bucket" "mine" {
  bucket = "my-new-bucket"
}

# This reads an existing bucket (Terraform does NOT own it)
data "aws_s3_bucket" "amplify" {
  bucket = var.existing_bucket_name
}
```

This project uses a `data` source for the S3 bucket because Amplify CLI created it — Terraform should not try to recreate or destroy it.

#### The Bootstrap Problem

Remote state requires an S3 bucket to exist *before* Terraform can store state. But you can't use Terraform to create that bucket if Terraform doesn't have state yet. The solution is a one-time `bootstrap/` subdirectory that uses *local* state to create the state bucket.

```
terraform/bootstrap/
├── main.tf     # creates the state bucket and DynamoDB lock table
└── versions.tf # uses local backend (no remote state needed)
```

You run bootstrap once per AWS account and never touch it again.

### Lab: Setting Up the Terraform Foundation

**Goal**: A blank AWS account with a remote state backend and a minimal S3 data bucket.

**Step 1 — Bootstrap the state infrastructure**

Create `terraform/bootstrap/main.tf`:

```hcl
resource "aws_s3_bucket" "tf_state" {
  bucket = "myproject-tf-state"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_dynamodb_table" "tf_locks" {
  name         = "terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}
```

Run: `terraform init && terraform apply`

Verify in the AWS Console that the S3 bucket and DynamoDB table exist.

**Step 2 — Configure the remote backend**

Create `terraform/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "myproject-tf-state"
    key            = "data-engineering/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
}
```

Run: `terraform init` — Terraform will ask to migrate local state to S3.

**Step 3 — Create the first module (storage)**

Create `terraform/modules/storage/main.tf`:

```hcl
data "aws_s3_bucket" "main" {
  bucket = var.bucket_name
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
```

See `terraform/modules/storage/` in this repo for variables.tf and outputs.tf.

**Step 4 — Wire it in the root**

In `terraform/main.tf`:

```hcl
module "storage" {
  source       = "./modules/storage"
  project_name = var.project_name
  environment  = var.environment
  bucket_name  = var.existing_bucket_name
}
```

Run `terraform plan` — you should see only one resource to create (the DynamoDB table).

**Verification**: `terraform apply`, then check the DynamoDB console for the new table.

### Trade-offs

**Why separate `bootstrap/` from the main config?**

The state bucket is special: everything else depends on it. Keeping it in a separate directory with local state prevents a chicken-and-egg problem and also means `terraform destroy` on the main config never accidentally deletes the state store.

**Why not just use Amplify for everything?**

Amplify CLI is excellent for managed services (Cognito, S3 with fine-grained auth rules), but it is opinionated and hard to extend. The moment you need a Glue job, an Athena workgroup, or a custom Lambda with specific IAM, you hit its ceiling. Terraform handles arbitrary AWS resources with no friction. This project uses Amplify for auth/storage (its strengths) and Terraform for everything custom.

**Why one environment (`dev`) instead of `dev` + `prod`?**

At personal scale, the overhead of maintaining two full stacks outweighs the benefit. The `environment` variable is in place so you can instantiate a second stack by passing `environment = "prod"` to the modules — but the trigger to do that is real usage, not principle.

### Exercises

1. **New module**: Create `terraform/modules/logging/` that provisions an S3 bucket with SSE and a 90-day lifecycle rule that transitions objects to `GLACIER`. Wire it in the root `main.tf`. Verify with `terraform plan` that only the new bucket is created.

2. **Output chaining**: Add an output `dynamodb_table_arn` to `modules/storage/outputs.tf`, surface it in the root `outputs.tf`, then run `terraform output dynamodb_table_arn` after applying. Understand why the root output must reference `module.storage.dynamodb_table_arn`.

3. **Workspace experiment**: Run `terraform workspace new staging`, then `terraform plan`. Observe how the workspace name does *not* automatically change the `environment` variable. What would you need to change in `variables.tf` to make environment track workspace automatically?

4. **State inspection**: After applying, run `terraform state list`. Find your DynamoDB table in the list. Run `terraform state show <address>`. What fields does Terraform track that you did not specify in the `.tf` file?

5. **Intentional drift**: In the AWS Console, manually add a tag to the DynamoDB table. Run `terraform plan` — does Terraform detect the drift? Why or why not?

### Check-Yourself Questions

1. What is Terraform state, and what breaks if it gets out of sync with reality?
2. What is the difference between a `resource` and a `data` source?
3. Why does this project have a `bootstrap/` directory?
4. What does `terraform plan` actually do? Why should you always read the plan before applying?
5. Why use Terraform modules instead of putting everything in one `main.tf`?
6. In which situations would you use `terraform import`?

---

## Module 2 — The Data Lakehouse: S3, Glue, and Athena

### Concepts

#### The Medallion Architecture

A data lakehouse organizes raw data into layers that represent progressively cleaner and more structured data:

| Layer | Storage | Format | Purpose |
|---|---|---|---|
| **Raw** | `raw-whatsapp-uploads/` | `.txt` | Original file, untouched |
| **Bronze** | `bronze/whatsapp/year=.../month=.../` | `.txt` | Validated, partitioned, unchanged format |
| **Silver** | `silver/whatsapp/` | Parquet, snappy | Parsed, typed, queryable |

In this project there is no gold layer because the "reporting" use case (the React app) is served by the silver layer directly via Athena.

**Why bronze at all, if silver is the real deal?**

Because reprocessing is inevitable. If you parse directly from raw to silver in one step, any bug in the parser corrupts your only copy. Bronze gives you a clean, cheap backup of the validated originals at the correct S3 partition paths, so you can re-run the Glue job at any time without re-uploading.

#### Hive Partitioning

Parquet files in S3 become efficiently queryable when organized as:

```
silver/whatsapp/date=2024-03-01/part-00000.snappy.parquet
silver/whatsapp/date=2024-03-02/part-00000.snappy.parquet
```

This is called **Hive partitioning**. When you run `SELECT * FROM whatsapp_messages WHERE date = '2024-03-01'`, Athena reads only the `date=2024-03-01/` prefix — it skips all other partitions. At large scale this makes queries orders of magnitude faster and cheaper (Athena charges per byte scanned).

The Glue Catalog stores the mapping from logical table names (`whatsapp_messages`) to S3 paths and column schemas. Athena uses the catalog at query time to know where to find data.

#### Glue PySpark Job

AWS Glue is a managed Spark environment. A Glue job runs PySpark code on a cluster that AWS provisions and tears down automatically. You pay per DPU-hour (Data Processing Unit); at G.1X with 2 workers for under a minute, the cost is around $0.07 per run.

The `whatsapp_silver` job:

1. Lists all `.txt` files in `bronze/whatsapp/` using boto3.
2. Parses each file line-by-line using a regex that matches WhatsApp timestamp formats.
3. Builds a Spark DataFrame with a typed schema.
4. Writes to Parquet, partitioned by `date`, using overwrite mode.
5. Registers (or re-registers) the table in the Glue Catalog using `CREATE EXTERNAL TABLE`.

Key snippet from `glue_jobs/whatsapp_silver/job.py`:

```python
# Two common WhatsApp date formats
DATE_PATTERNS = [
    re.compile(r'^\[?(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]?\s+-\s+(.+?):\s+(.*)$'),
    re.compile(r'^\[?(\d{1,2})[-.](\d{1,2})[-.](\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]?\s+-\s+(.+?):\s+(.*)$'),
]
```

A stable `message_id` is computed as `SHA-256(source_file:line_index)[:16]`. This means re-running the job on the same input always produces the same IDs — idempotency.

#### Athena

Athena is serverless SQL. It reads Parquet files from S3, uses the Glue Catalog for schema, and returns results. There is no server to manage. You pay $5 per TB scanned.

In this project Athena is accessed two ways:
1. **Lambda** (`whatsapp_api`): programmatically, via `boto3.client('athena')`, polling until the query succeeds.
2. **Console**: directly, using the named queries pre-configured in Terraform.

### Lab: Building the WhatsApp Pipeline from Scratch

**Step 1 — The bronze Lambda**

Create `terraform/lambdas/whatsapp_bronze/handler.py`. The core logic:

```python
import re, boto3, urllib.parse

BRONZE_PREFIX = "bronze/whatsapp"
WHATSAPP_RE = re.compile(r'^\[?\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4},?\s+\d{1,2}:\d{2}')
s3 = boto3.client('s3')

def handler(event, context):
    record = event['Records'][0]['s3']
    bucket = record['bucket']['name']
    key = urllib.parse.unquote_plus(record['object']['key'])

    obj = s3.get_object(Bucket=bucket, Key=key)
    lines = obj['Body'].read().decode('utf-8', errors='replace').splitlines()
    matches = sum(1 for l in lines if WHATSAPP_RE.match(l))
    if matches < 2:
        print(f"Rejected {key}: only {matches} WhatsApp lines")
        return {'statusCode': 200}

    # Derive partition from filename's last-modified date
    last_modified = obj['LastModified']
    dest_key = f"{BRONZE_PREFIX}/year={last_modified.year}/month={last_modified.month:02d}/{key.split('/')[-1]}"
    s3.copy_object(Bucket=bucket, CopySource={'Bucket': bucket, 'Key': key}, Key=dest_key)
    return {'statusCode': 200}
```

See `terraform/lambdas/whatsapp_bronze/handler.py` for the complete version.

**Step 2 — Package and deploy the Lambda with Terraform**

In `terraform/modules/compute/main.tf` (relevant snippet):

```hcl
data "archive_file" "whatsapp_bronze" {
  type        = "zip"
  source_dir  = "${path.root}/../terraform/lambdas/whatsapp_bronze"
  output_path = "${path.root}/packages/whatsapp_bronze.zip"
}

resource "aws_lambda_function" "whatsapp_bronze" {
  function_name    = "${var.project_name}-whatsapp-bronze-${var.environment}"
  role             = aws_iam_role.lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.whatsapp_bronze.output_path
  source_code_hash = data.archive_file.whatsapp_bronze.output_base64sha256
  timeout          = 60
  memory_size      = 256
}
```

The `source_code_hash` ensures Terraform re-deploys the Lambda only when the zip changes. Without it, Terraform would not detect handler code changes.

**Step 3 — Wire the S3 trigger**

In `terraform/main.tf` (root, not in a module, because it cross-cuts storage and compute):

```hcl
resource "aws_lambda_permission" "whatsapp_bronze_s3" {
  action        = "lambda:InvokeFunction"
  function_name = module.compute.whatsapp_bronze_function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.storage.bucket_arn
}

resource "aws_s3_bucket_notification" "main" {
  bucket = module.storage.bucket_id
  depends_on = [
    aws_lambda_permission.whatsapp_bronze_s3,
    aws_lambda_permission.photo_processor_s3,
  ]
  lambda_function {
    lambda_function_arn = module.compute.whatsapp_bronze_function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw-whatsapp-uploads/"
    filter_suffix       = ".txt"
  }
  # ... photo_processor notification
}
```

Note the `aws_lambda_permission` resource. S3 needs explicit permission to invoke a Lambda. Without it, S3 will call the function and receive an access denied error — Terraform will not warn you; you will only see the failure in Lambda's CloudWatch logs.

**Step 4 — The Glue job (analytics module)**

The Glue job Terraform resource uploads the script to S3 first:

```hcl
resource "aws_s3_object" "whatsapp_silver_script" {
  bucket = var.bucket_id
  key    = "glue-scripts/whatsapp_silver/job.py"
  source = "${path.root}/glue_jobs/whatsapp_silver/job.py"
  etag   = filemd5("${path.root}/glue_jobs/whatsapp_silver/job.py")
}

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
  }
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60
}
```

**Step 5 — Run the job and query**

```bash
# Trigger the job manually
aws glue start-job-run --job-name "data-engineering-whatsapp-silver-dev"

# Watch it complete (check the Glue console or poll with CLI)
aws glue get-job-run --job-name "data-engineering-whatsapp-silver-dev" --run-id <run-id>

# Query with Athena (via AWS Console or CLI)
aws athena start-query-execution \
  --query-string "SELECT sender, COUNT(*) AS cnt FROM whatsapp_messages GROUP BY sender" \
  --work-group "data-engineering-dev" \
  --query-execution-context Database=data_engineering_dev
```

### Trade-offs

**Why Glue (PySpark) instead of a Lambda?**

Lambda has a 15-minute timeout and 10 GB memory limit. For small exports (< 50 MB), a Lambda would work. But PySpark gives you:

- **Schema enforcement**: you define column types explicitly; bad data raises schema errors, not silent nulls.
- **Snappy-compressed Parquet**: roughly 5–10× compression vs raw text, and columnar format means Athena scans only the columns you query.
- **Partition pruning**: Spark writes `date=2024-03-01/` directory structure natively; Athena exploits it automatically.
- **Horizontal scale**: if exports grow to gigabytes, add more workers; no code changes needed.

The cost is higher per run (~$0.07 vs ~$0.00001 for Lambda). At one run per day that's ~$2/month.

**Why store both bronze *and* silver instead of overwriting raw?**

Bronze is immutable. If the parser has a bug — say it drops messages with emoji in the sender name — you can fix the parser and re-run the Glue job against bronze. If you had written parsed output back over the raw file, you would need to re-upload all your exports.

**Why `overwrite` mode in the Glue job (not `append`)?**

Because WhatsApp exports are cumulative: a new export of the same chat includes all old messages plus new ones. If you append, you duplicate every previously seen message. Overwrite-per-partition ensures idempotency: running the same export twice produces the same silver layer.

### Exercises

1. **Add a column**: Modify the Glue job to add a `message_length` column (character count of the message field). Re-run the job. Write an Athena query that returns the average message length per sender. Verify the column appears in the Glue Catalog schema.

2. **Add a named query**: In `terraform/modules/analytics/main.tf`, add an `aws_athena_named_query` resource that finds the five dates with the most messages. Apply and verify it appears in the Athena console under "Saved queries".

3. **Bronze validation test**: Write a unit test for the bronze Lambda's validation logic. Create a string with 1 valid WhatsApp line (should be rejected) and another with 3 valid lines (should be accepted). See `terraform/lambdas/whatsapp_bronze/test_handler.py` for the existing test structure.

4. **Partition experiment**: After running the Glue job, go to the S3 console and count how many `date=.../` directories exist. Run `SELECT COUNT(*) FROM whatsapp_messages` in Athena. Now add a `WHERE date > '2024-01-01'` predicate. Check "Data scanned" in the Athena query results — is it less than the full scan?

5. **Crawler vs MSCK REPAIR**: The project uses `MSCK REPAIR TABLE` in the Glue job itself to register partitions. Disable that line and instead run the Glue Crawler. Observe the difference. Which is faster? What happens if you have 1,000 partitions?

### Check-Yourself Questions

1. Explain the bronze/silver split in your own words. What happens if you skip bronze?
2. What is Hive partitioning and why does it make Athena queries cheaper?
3. What does the Glue Catalog store, and how does Athena use it?
4. Why does the Glue job use `overwrite` mode instead of `append`?
5. What makes the `message_id` stable across job reruns, and why does that matter?
6. What is a DPU in Glue, and how does it affect cost?

---

## Module 3 — Event-Driven Compute: Lambda and IAM

### Concepts

#### Event-Driven Architecture

In this system, nothing runs on a schedule unless explicitly configured. Events trigger work:

- A file lands in `raw-photos/` → S3 sends a notification → Lambda runs.
- A user calls `GET /photos` → API Gateway receives the request → Lambda runs.

There are no long-running processes. Lambda functions start, do their work, and stop. AWS charges only for the compute time consumed (invocation count + GB-seconds of memory × duration).

This is the opposite of a traditional server running 24/7. The trade-off is **cold starts** (the first invocation after a period of inactivity may take 200–500 ms to initialize) versus **zero cost at zero traffic**.

#### Lambda Lifecycle

When Lambda runs your function:

1. **Cold start** (first invocation or after inactivity): AWS provisions a micro-VM, downloads and extracts your deployment package, runs module-level initialization code (the top of your `handler.py`, outside the `handler()` function).
2. **Warm invocations**: the micro-VM stays alive for ~5–15 minutes. Module-level objects (boto3 clients, compiled regexes) are reused. This is why you define boto3 clients at module level, not inside the handler function.

```python
# Good: initialized once, reused across warm invocations
s3 = boto3.client('s3')
_re = re.compile(r'^\[?\d{1,2}[/\-.]...')

def handler(event, context):
    # uses module-level s3 and _re
```

#### IAM: Roles and Policies

IAM controls *who* can do *what* to *which* resources.

Every Lambda runs with an **IAM role**. The role has an **assume role policy** (trust policy) that says which service can use the role, and **permission policies** that say what the role can do.

```
Lambda function
  └── assumes: aws_iam_role.lambda
        └── trust policy: "lambda.amazonaws.com can AssumeRole"
        └── attached policy 1: AWSLambdaBasicExecutionRole (CloudWatch write)
        └── attached policy 2: custom S3 + DynamoDB permissions
        └── attached policy 3: custom Athena + Glue permissions
```

**Principle of least privilege**: only grant the permissions actually needed. In this project the S3 policy is scoped to `var.bucket_arn` and `var.bucket_arn/*` — not `arn:aws:s3:::*`. The DynamoDB policy is scoped to the specific table ARN.

Common mistake: writing `Resource = "*"` to make a policy work quickly. This grants the Lambda permission to read and write every S3 bucket and DynamoDB table in the account. Never do this in production.

#### S3 Event Notifications

S3 can notify Lambda when objects are created, deleted, or restored. The notification specifies:
- Which bucket events to watch (`s3:ObjectCreated:*`)
- Which prefix to filter on (`raw-photos/`)
- Which suffix (`*.jpg`, etc.)
- Which Lambda ARN to call

Two Terraform resources are always needed together:

```hcl
# 1. Tell Lambda to allow S3 to invoke it
resource "aws_lambda_permission" "photo_processor_s3" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.photo_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.bucket_arn   # scope to specific bucket
}

# 2. Tell S3 to send notifications to Lambda
resource "aws_s3_bucket_notification" "main" {
  bucket = var.bucket_id
  lambda_function {
    lambda_function_arn = aws_lambda_function.photo_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw-photos/"
  }
}
```

If you configure the notification without the permission, S3 cannot call the Lambda — you will see `AccessDenied` errors in CloudWatch, and S3 will silently discard the event after a few retries.

#### Deployment Packages

Lambda code is deployed as a `.zip` file. For pure Python (standard library + boto3, which is pre-installed in the Lambda runtime), you just zip your handler:

```hcl
data "archive_file" "whatsapp_bronze" {
  type        = "zip"
  source_dir  = "${path.root}/../lambdas/whatsapp_bronze"
  output_path = "${path.root}/packages/whatsapp_bronze.zip"
}
```

For third-party libraries (like Pillow in `photo_processor`), you must bundle them:

```hcl
resource "null_resource" "build_photo_processor" {
  triggers = { handler_hash = filemd5("${path.root}/../lambdas/photo_processor/handler.py") }
  provisioner "local-exec" {
    command = <<-EOT
      pip install pillow \
        --platform manylinux_2_28_x86_64 \
        --python-version 3.12 \
        --only-binary=:all: \
        --target ${path.root}/../lambdas/photo_processor/package/
    EOT
  }
}
```

The `--platform manylinux_2_28_x86_64` flag downloads the pre-compiled Linux binary for Pillow, even when running on macOS. Without this, Pillow compiled on macOS would crash on Amazon Linux.

### Lab: Writing and Deploying a Lambda from Scratch

**Goal**: A working Lambda that validates a WhatsApp export, triggered by S3.

**Step 1 — Write the handler** (see `terraform/lambdas/whatsapp_bronze/handler.py`)

Key things to get right:
- Decode the S3 key: `urllib.parse.unquote_plus(record['object']['key'])` — S3 URL-encodes spaces and special characters.
- Read the body: `obj['Body'].read().decode('utf-8', errors='replace')` — `errors='replace'` prevents a crash on non-UTF-8 characters.
- Return a proper response: `{'statusCode': 200}` — not returning anything makes Lambda log a warning.

**Step 2 — Write the tests**

Before deploying, test locally with `pytest`. The key technique is mocking boto3:

```python
from unittest.mock import patch, MagicMock

@patch('handler.s3')
def test_valid_file_is_copied(mock_s3):
    mock_s3.get_object.return_value = {
        'Body': MagicMock(read=lambda: VALID_CONTENT.encode()),
        'LastModified': datetime(2024, 3, 1),
    }
    result = handler(make_event('raw-whatsapp-uploads/export.txt'), None)
    assert result['statusCode'] == 200
    mock_s3.copy_object.assert_called_once()
```

Run: `cd terraform/lambdas/whatsapp_bronze && python -m pytest test_handler.py -v`

**Step 3 — Add IAM**

The Lambda role needs S3 `GetObject` (to read the uploaded file) and `PutObject`/`CopyObject` (to write to bronze). See `terraform/modules/compute/main.tf` for the complete role and policy.

**Step 4 — Apply and smoke-test**

```bash
cd terraform && terraform apply

# Upload a test file via the React app or directly:
aws s3 cp test_export.txt s3://your-bucket/raw-whatsapp-uploads/test.txt

# Check Lambda logs:
aws logs tail /aws/lambda/data-engineering-whatsapp-bronze-dev --follow
```

### Trade-offs

**Why one shared IAM role for all four Lambdas instead of one role per Lambda?**

Simplicity. Four roles × three policies each = 12 IAM resources to manage. One role with the union of all permissions is simpler for a single-developer project.

The cost: every Lambda can read DynamoDB and query Athena, even the ones that don't need it. If one Lambda were compromised, an attacker could read all your data through any of the four entry points.

For production multi-tenant systems, use per-function roles scoped to only what that function needs. For personal projects, the union-role approach is fine.

**Why Pillow bundled in the deployment package instead of a Lambda Layer?**

A Layer is a separate versioned artifact that multiple functions can share. The advantage is smaller per-function deployment packages and the ability to update the library independently of the handler code.

The disadvantage: another artifact to version, another Terraform resource to manage (`aws_lambda_layer_version`), and the `layers` argument in the function resource. For one function using Pillow, bundling is simpler and the 50 MB deployment package limit is not an issue.

**Why Python 3.12 and not the latest?**

AWS adds new runtimes with a lag. Python 3.13 may not be available in all regions. More importantly, Pillow's pre-compiled manylinux wheel must match the Python minor version. Pinning to 3.12 ensures reproducible builds.

### Exercises

1. **Add a new Lambda**: Create `terraform/lambdas/archive_notify/handler.py` that logs the S3 key and file size of any object uploaded to `raw-archive/`. Add the Terraform resources for the Lambda, an S3 notification for `raw-archive/`, and the required Lambda permission. Verify by uploading a file and checking CloudWatch logs.

2. **Least-privilege IAM**: The current Lambda role grants `s3:DeleteObject`. Identify which Lambda actually needs it and which ones do not. Write a more restrictive IAM policy that grants `DeleteObject` only to the Lambdas that require it. (Hint: look at which Lambda copies to `bronze/` vs which one overwrites thumbnails.)

3. **Cold start measurement**: Add `import time; start = time.time()` at the top of `handler.py` (module level) and log `time.time() - start` inside the handler. Deploy and invoke the Lambda several times in quick succession (warm), then wait 15 minutes and invoke again (cold). Compare the log times.

4. **Dead letter queue**: Add an SQS Dead Letter Queue (DLQ) to the `whatsapp_bronze` Lambda. Configure it to receive events that fail after 2 retries. Terraform resource: `aws_sqs_queue` + `dead_letter_config` in `aws_lambda_function`. Trigger a failure by uploading a non-UTF-8 file and observe the DLQ.

5. **Version pinning**: The `photo_processor` Pillow build uses `--only-binary=:all:`. Remove that flag and try to build. What happens? Why is that flag necessary in a CI environment?

### Check-Yourself Questions

1. What is a Lambda cold start and how does module-level code affect it?
2. Why do you need both `aws_lambda_permission` and `aws_s3_bucket_notification` to trigger Lambda from S3?
3. What does the `source_code_hash` field on `aws_lambda_function` do?
4. Explain `--platform manylinux_2_28_x86_64` in the Pillow pip install command.
5. What does IAM least privilege mean in practice? Give a concrete example from this project.
6. What is the difference between an IAM role's trust policy and its permission policy?

---

## Module 4 — APIs and Authentication: API Gateway, Cognito, CORS

### Concepts

#### API Gateway REST API

API Gateway sits between the internet and your Lambda functions. It handles:

- **Routing**: `GET /photos` → `photos_api` Lambda, `GET /chats` → `whatsapp_api` Lambda.
- **Authorization**: validate the Cognito ID token before invoking Lambda.
- **CORS**: respond to browser preflight `OPTIONS` requests.
- **Throttling**: protect your Lambdas from accidental or malicious high traffic (not configured in this project, but available).

The integration type used here is **AWS_PROXY** (Lambda Proxy). With this integration, API Gateway passes the entire HTTP request to Lambda as a JSON event, and the Lambda must return a properly formatted response:

```python
return {
    'statusCode': 200,
    'headers': {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
    },
    'body': json.dumps(data),
}
```

The alternative is **AWS** (non-proxy) integration, which lets you transform requests/responses with VTL (Velocity Template Language) mapping templates. That is more powerful but vastly more complex. Lambda Proxy is almost always the right choice for new APIs.

#### Cognito Authorizer

Instead of managing JWTs yourself, you attach a Cognito User Pool authorizer to API Gateway. When a request arrives:

1. API Gateway extracts the token from the `Authorization` header.
2. API Gateway calls Cognito to validate the token signature and expiry.
3. If valid, the request proceeds to Lambda; if not, API Gateway returns 401 without touching Lambda.

From Terraform:

```hcl
resource "aws_api_gateway_authorizer" "cognito" {
  name          = "cognito-authorizer"
  rest_api_id   = aws_api_gateway_rest_api.main.id
  type          = "COGNITO_USER_POOLS"
  provider_arns = [var.cognito_user_pool_arn]
}

resource "aws_api_gateway_method" "photos_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.photos.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}
```

On the React side, the Amplify `fetchAuthSession()` call retrieves the Cognito ID token, which is then passed as the `Authorization` header:

```javascript
const session = await fetchAuthSession();
const token = session.tokens?.idToken?.toString();
const res = await fetch(apiUrl, { headers: { Authorization: token } });
```

#### CORS

Browsers enforce the **Same-Origin Policy**: JavaScript on `https://my-app.s3-website.amazonaws.com` cannot call `https://xyz.execute-api.us-east-1.amazonaws.com` without explicit CORS headers.

Before every cross-origin request, the browser sends a **preflight** `OPTIONS` request. The server must respond with:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
```

In this project, `OPTIONS` methods use a **MOCK** integration — API Gateway responds immediately with the required headers without invoking Lambda at all:

```hcl
resource "aws_api_gateway_method" "photos_options" {
  http_method   = "GET"
  authorization = "NONE"   # no auth on OPTIONS
}

resource "aws_api_gateway_integration" "photos_options" {
  type = "MOCK"
  request_templates = { "application/json" = "{\"statusCode\": 200}" }
}
```

The `GET` Lambda must *also* include CORS headers in its response body, because after the preflight succeeds, the actual GET response also needs `Access-Control-Allow-Origin`.

#### API Gateway Deployments and Stages

Changes to API Gateway resources do not take effect until you create a new **Deployment** and associate it with a **Stage**. Terraform manages this but has a quirk: `aws_api_gateway_deployment` only re-deploys when its `triggers` change.

In this project, a sha1 hash of all resource IDs is used as the trigger:

```hcl
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.photos.id,
      aws_api_gateway_method.photos_get.id,
      aws_api_gateway_resource.chats.id,
      # ... all resources
    ]))
  }
  lifecycle { create_before_destroy = true }
}
```

If you add a new method but forget to add its ID to `triggers`, the deployment won't update and your new endpoint won't work. This is one of the most common Terraform + API Gateway bugs.

#### Athena Polling in Lambda

Athena is asynchronous: you start a query and get back an `execution_id`, then poll until the state is `SUCCEEDED` or `FAILED`. The `whatsapp_api` Lambda implements this pattern:

```python
MAX_POLLS = 60
POLL_SLEEP = 0.5  # seconds → max 30s timeout

resp = athena.start_query_execution(
    QueryString=sql,
    QueryExecutionContext={'Database': DATABASE},
    WorkGroup=WORKGROUP,
)
execution_id = resp['QueryExecutionId']

for _ in range(MAX_POLLS):
    state = athena.get_query_execution(
        QueryExecutionId=execution_id
    )['QueryExecution']['Status']['State']
    if state == 'SUCCEEDED':
        break
    if state in ('FAILED', 'CANCELLED'):
        raise RuntimeError(f'Athena query {state}')
    time.sleep(POLL_SLEEP)
else:
    raise TimeoutError('Athena query timed out')
```

After `SUCCEEDED`, paginate through results using `get_query_results` and `NextToken`:

```python
kwargs = {'QueryExecutionId': execution_id}
first_page = True
rows = []
while True:
    result = athena.get_query_results(**kwargs)
    data_rows = result['ResultSet']['Rows']
    if first_page:
        data_rows = data_rows[1:]  # skip the header row
        first_page = False
    for row in data_rows:
        values = [d.get('VarCharValue', '') for d in row['Data']]
        rows.append(dict(zip(column_names, values)))
    next_token = result.get('NextToken')
    if not next_token:
        break
    kwargs['NextToken'] = next_token
```

Note: the first page of `get_query_results` includes a header row. You must skip it on the first page only.

#### SQL Injection Prevention

The `whatsapp_api` Lambda builds SQL dynamically from user-supplied query parameters. Never interpolate user input directly into SQL. The mitigation used here:

```python
def _escape_sql_string(value: str) -> str:
    return value.replace("'", "''")

# Safe: single quotes inside the value are escaped
f"LOWER(sender) LIKE '%{_escape_sql_string(sender.lower())}%'"
```

This is sufficient for Athena (which does not support parameterized queries via boto3). For other databases, use parameterized queries (`cursor.execute("WHERE sender = %s", [sender])`).

### Lab: Adding a New API Endpoint

**Goal**: Add a `GET /stats` endpoint that returns the total message count from Athena.

**Step 1 — Write the Lambda handler** (`terraform/lambdas/stats_api/handler.py`)

```python
import json, os, time, boto3

athena = boto3.client('athena')
DATABASE = os.environ['ATHENA_DATABASE']
WORKGROUP = os.environ['ATHENA_WORKGROUP']

CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Allow-Methods': 'GET,OPTIONS',
}

def handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    sql = "SELECT COUNT(*) AS total FROM whatsapp_messages"
    # ... (run query with the same polling pattern as whatsapp_api)
    return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(rows)}
```

**Step 2 — Add Terraform resources** (in `modules/compute/main.tf`)

You need six new resources:
1. `aws_lambda_function.stats_api`
2. `aws_api_gateway_resource.stats` (path `/stats`)
3. `aws_api_gateway_method.stats_get` (Cognito auth)
4. `aws_api_gateway_integration.stats_get` (AWS_PROXY)
5. `aws_api_gateway_method.stats_options` (no auth)
6. `aws_api_gateway_integration.stats_options` (MOCK)
7. Lambda permission for API Gateway
8. Add `stats_get` and `stats_options` method IDs to the deployment `triggers`

If you forget step 8, the deployment will not update and the endpoint will return 404.

**Step 3 — Test**

```bash
terraform apply
# Get the URL
terraform output -raw stats_api_url
# Call from browser (authenticated) or use curl with a token
```

### Trade-offs

**Why REST API Gateway instead of HTTP API Gateway?**

AWS offers two API Gateway flavors:
- **REST API** (v1): full-featured, supports edge-optimized deployments, usage plans, API keys, and detailed per-resource configuration. Higher cost ($3.50/million requests).
- **HTTP API** (v2): simpler, lower latency, cheaper ($1/million), natively supports JWT authorizers.

This project uses REST API because it was already configured when Cognito auth was added, and the feature set (MOCK CORS, Cognito authorizer) is available in both. For a greenfield project today, start with HTTP API.

**Why Cognito instead of something simpler?**

Cognito handles signup, login, MFA, token rotation, and social logins out of the box. For a personal project with one user, it is overkill — you could use a hard-coded API key or Basic Auth header with the same security posture. But Cognito is already provisioned by Amplify and integrates natively with API Gateway, so there is no additional cost or maintenance.

**Why generate pre-signed URLs in the Lambda instead of storing them?**

Pre-signed URLs are time-limited. A URL stored in DynamoDB would expire and become invalid. Generating them fresh on each API call ensures they always work for the configured TTL. The cost is a few extra milliseconds of boto3 call time per photo.

### Exercises

1. **Add rate limiting**: Add a `aws_api_gateway_usage_plan` and `aws_api_gateway_api_key` to limit the API to 100 requests per day. Wire it to the existing stage. Test by calling the API more than 100 times and observe the 429 response.

2. **Pagination**: The current `GET /photos` returns all photos in a single response. Add a `page` and `page_size` query parameter to the Lambda handler. Implement cursor-based pagination using `ExclusiveStartKey` in the DynamoDB scan. Return a `next_cursor` field in the response.

3. **OPTIONS security review**: The current `OPTIONS` MOCK integration returns `Access-Control-Allow-Origin: *`. Change the Lambda CORS headers to only allow your specific S3 website URL. Test that a request from a different origin is blocked.

4. **Error handling**: What happens to the React frontend when the Athena query fails (e.g., the silver table doesn't exist)? Currently it returns 500 with `{"error": "..."}`. Add a user-friendly error response in the React `WhatsAppPage.jsx` that shows the error message instead of crashing.

5. **Athena result caching**: Athena caches results for up to 24 hours. Modify the `whatsapp_api` Lambda to pass `ResultReuseConfiguration` with a `MaxAgeInMinutes` of 60. Run the same query twice and observe the difference in query execution time and cost.

### Check-Yourself Questions

1. What is API Gateway Lambda Proxy integration, and what does the Lambda response must include?
2. What is a CORS preflight request, and why do OPTIONS methods need no auth?
3. Why does this project use a MOCK integration for OPTIONS instead of a Lambda?
4. What is the deployment trigger `sha1(jsonencode([...]))` doing, and what breaks if you forget to update it?
5. Explain how the Athena async polling pattern works. What are the risks if `MAX_POLLS` is too low?
6. Why is single-quote escaping sufficient for SQL injection prevention in Athena?

---

## Module 5 — The Photo Pipeline: Pillow, EXIF, and DynamoDB

### Concepts

#### Image Processing with Pillow

Pillow (PIL fork) is the standard Python image library. In `photo_processor`:

```python
from PIL import Image, ExifTags

with Image.open(io.BytesIO(body)) as img:
    # Convert RGBA → RGB for JPEG compatibility
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')

    # Resize maintaining aspect ratio
    img.thumbnail((300, 300), Image.LANCZOS)

    # Save to in-memory buffer
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    buf.seek(0)
```

`Image.thumbnail()` resizes in-place to fit within the given box while preserving aspect ratio. A 4000×3000 photo becomes 300×225. `LANCZOS` is a high-quality downsampling filter.

#### EXIF Metadata

EXIF (Exchangeable Image File Format) metadata is embedded in JPEG files by cameras and phones. It contains:

- `DateTimeOriginal` (tag 36867): when the shutter was pressed.
- `Make` / `Model` (tags 271, 272): camera brand and model.
- `Flash` (tag 37385): whether flash fired (bitmask, bit 0 = flash status).
- `GPSInfo` (tag 34853): GPS coordinates (nested sub-IFD).

```python
exif = img._getexif()
if exif:
    taken_raw = exif.get(36867) or exif.get(306)  # DateTimeOriginal or DateTime
    if taken_raw:
        taken_at = datetime.strptime(taken_raw, '%Y:%m:%d %H:%M:%S').isoformat()
```

Not all images have EXIF (PNGs don't; screenshots don't). The code handles `None` gracefully.

#### DynamoDB Data Modeling

DynamoDB is a key-value / document store. The primary key for `PhotoMetadata` is just `photo_id` (a UUID). There is no sort key.

A single item looks like:

```json
{
  "photo_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "IMG_1234.jpg",
  "original_key": "photos/originals/IMG_1234.jpg",
  "thumbnail_key": "photos/thumbnails/IMG_1234.jpg",
  "width": 4032,
  "height": 3024,
  "size_bytes": 4200000,
  "taken_at": "2024-03-01T12:34:56",
  "uploaded_at": "2024-03-01T14:00:00Z",
  "camera_make": "Apple",
  "camera_model": "iPhone 15 Pro",
  "tags": ["landscape", "gps"],
  "source_key": "raw-photos/IMG_1234.jpg"
}
```

**Scan vs. Query**: DynamoDB `Query` is fast because it uses the key. DynamoDB `Scan` reads every item in the table. At hundreds of items (personal photo collection), a full scan takes milliseconds and costs fractions of a cent. At millions of items, a scan would be expensive and slow. Adding a **Global Secondary Index** (GSI) on `uploaded_at` would allow `Query` instead of `Scan`, but this project deliberately omits it to keep the schema simple.

**Sparse attributes**: DynamoDB does not require all items to have the same attributes. Items without `taken_at` simply don't have that key. The `photos_api` Lambda handles this with `item.get('taken_at')` (returns `None` if absent).

#### Pre-signed S3 URLs

To serve S3 objects to a browser without making the bucket public, generate a pre-signed URL. This URL embeds the credentials and expiry in the URL itself — anyone with the URL can access the object until it expires.

```python
thumbnail_url = s3.generate_presigned_url(
    'get_object',
    Params={'Bucket': bucket, 'Key': thumbnail_key},
    ExpiresIn=3600,  # 1 hour
)
```

The React app receives these URLs in the API response and uses them directly in `<img src={photo.thumbnail_url}>`.

### Lab: Extending the Photo Pipeline

**Goal**: Add a `dominant_color` field that extracts the most common pixel color from the thumbnail.

**Step 1 — Modify the Lambda** (`terraform/lambdas/photo_processor/handler.py`)

After generating the thumbnail:

```python
# Get dominant color (most common pixel in a 10x10 downsample)
small = img.copy().resize((10, 10))
pixels = list(small.getdata())
dominant = max(set(pixels), key=pixels.count)
dominant_hex = '#{:02x}{:02x}{:02x}'.format(*dominant[:3])
```

Add `dominant_color` to the DynamoDB `put_item` call.

**Step 2 — Update the photos_api response**

The `photos_api` Lambda returns all DynamoDB attributes; no change needed if you just add `dominant_color` to the item.

**Step 3 — Display in React**

In `PhotosPage.jsx`, add a small color swatch next to each photo card using `photo.dominant_color`.

**Step 4 — Test**

```python
# In test_handler.py
def test_dominant_color_extracted():
    # Create a solid red image
    img = Image.new('RGB', (100, 100), color=(255, 0, 0))
    # ... mock boto3, invoke handler
    item = mock_dynamo.put_item.call_args[1]['Item']
    assert item['dominant_color']['S'] == '#ff0000'
```

**Step 5 — Deploy and verify**

```bash
terraform apply
# Upload a new photo
aws s3 cp test.jpg s3://your-bucket/raw-photos/test.jpg
# Check DynamoDB
aws dynamodb get-item --table-name data-engineering-photo-metadata-dev \
  --key '{"photo_id": {"S": "<check CloudWatch for the ID>"}}'
```

### Trade-offs

**Why DynamoDB for photo metadata instead of Parquet/Athena?**

| Dimension | DynamoDB | Parquet on S3 + Athena |
|---|---|---|
| **Latency** | Single-digit ms per item | 1–10 seconds (Athena startup) |
| **Schema flexibility** | Any attribute, any type, per-item | Enforced schema, schema evolution via Glue |
| **Point lookups** | O(1) by `photo_id` | Full scan or partition scan |
| **Cost at small scale** | ~$0/month on-demand | ~$0/month (minimal bytes scanned) |
| **Cost at large scale** | Per read/write unit | Per byte scanned |

For a photo gallery where you show thumbnails and need metadata fast, DynamoDB is the right choice. You are doing many small, keyed lookups (or a single full scan for the gallery). Athena is designed for analytical queries over large datasets, not per-item lookups.

If the photo collection grew to millions of items and you wanted analytics (e.g., "how many photos per month per camera model"), writing metadata to Parquet and querying with Athena would be cheaper than DynamoDB at scale.

**Why copy the original to `photos/originals/` instead of serving from `raw-photos/`?**

Two reasons:
1. `raw-photos/` is a processing trigger prefix. Serving from it would expose raw uploads (which may be re-processed or deleted) to the gallery. `photos/originals/` is the stable, final copy.
2. It separates the landing zone from the serving zone — if you later add a cleanup lifecycle rule to `raw-photos/`, it won't delete originals.

**Why tags derived from geometry instead of an AI model?**

AI image tagging (AWS Rekognition) is accurate and would give you tags like "sunset", "dog", "food". At $1/1000 images it is inexpensive. This project uses geometric derivation (landscape/portrait/square from dimensions, gps/flash from EXIF bits) because:
- It is free and deterministic.
- It demonstrates EXIF metadata extraction without additional AWS dependencies.
- You can add Rekognition later by adding one boto3 call to the Lambda.

### Exercises

1. **Add GPS decoding**: The `photo_processor` Lambda detects *whether* GPS is present but does not extract coordinates. Add code to parse `GPSLatitude`, `GPSLatitudeRef`, `GPSLongitude`, `GPSLongitudeRef` from `exif[34853]` and store `latitude` and `longitude` as DynamoDB Number attributes. Handle the case where GPS sub-IFDs are missing gracefully.

2. **Add a GSI**: Add a Global Secondary Index on `uploaded_at` to the DynamoDB table in Terraform. In `photos_api`, use `query()` instead of `scan()` when sorting by `uploaded_at`. Compare the consumed capacity units between scan and query for the same dataset.

3. **Thumbnail size experiment**: Change the thumbnail target from 300px to 150px and redeploy. Upload a new photo. Compare file sizes in S3 between the old and new thumbnails. What is the tradeoff between thumbnail quality and API response size?

4. **Handle duplicate uploads**: If a user uploads the same filename twice, `photo_processor` creates two DynamoDB items with different UUIDs. Add deduplication: before writing to DynamoDB, check if an item with the same `source_key` already exists and skip writing if so. Write a test for this behavior.

5. **Rekognition integration**: Add a call to `rekognition.detect_labels(Image={'S3Object': {'Bucket': bucket, 'Name': key}}, MaxLabels=5)` in the Lambda. Store the labels as a `rekognition_tags` list in DynamoDB. Add a Rekognition permission to the Lambda IAM policy. Update the React tag filter to include Rekognition tags.

### Check-Yourself Questions

1. What is EXIF metadata and what useful fields does it contain for a photo app?
2. Why does the thumbnail generator convert RGBA images to RGB before saving as JPEG?
3. What is a DynamoDB Scan, and when does it become a problem?
4. When would you add a GSI to this table, and what would it look like?
5. What is a pre-signed S3 URL, and what are its security implications?
6. Why copy originals to a new prefix rather than serving directly from `raw-photos/`?

---

## Module 6 — The Frontend: React, Amplify, and CI/CD

### Concepts

#### React Router v6

React Router enables client-side navigation without full page reloads. In `App.js`:

```jsx
<Routes>
  <Route path="/"                element={<HomePage />} />
  <Route path="/library"         element={<LibraryPage />} />
  <Route path="/library/photos"  element={<PhotosPage />} />
  <Route path="*"                element={<Navigate to="/library" replace />} />
</Routes>
```

The `*` catch-all prevents blank pages when the URL doesn't match any route. `replace` means it replaces the history entry instead of pushing, so the back button doesn't loop.

React Router manages URL state — when a user navigates to `/library/photos`, the `PhotosPage` component mounts, fetches data, and renders. When they click "← Library", the router unmounts `PhotosPage` and mounts `LibraryPage`.

#### Amplify Auth and Storage

AWS Amplify is a frontend SDK for AWS services. This project uses two parts:

**Auth** (`aws-amplify/auth`):

```javascript
const session = await fetchAuthSession();
const token = session.tokens?.idToken?.toString();
```

This retrieves a valid Cognito ID token from local storage (Amplify manages token refresh automatically). The token is then passed to your API Gateway calls.

**Storage** (`aws-amplify/storage`):

```javascript
// Upload a file
await uploadData({
  key: `raw-photos/${file.name}`,
  data: file,
  options: {
    contentType: file.type,
    onProgress: ({ transferredBytes, totalBytes }) => { /* update progress bar */ },
  },
}).result;

// List files in a prefix
const { items } = await list({ prefix: 'misc/' });

// Generate a pre-signed URL (for objects Amplify manages)
const { url } = await getUrl({ key: item.key });
```

Amplify Storage handles multipart uploads, retry logic, and pre-signed URL generation. For `getUrl`, Amplify generates a short-lived URL directly from the browser using the Cognito identity credentials — no Lambda needed for this path.

#### Environment Variables in Create React App

React environment variables are embedded at **build time**, not runtime. They must be prefixed with `REACT_APP_`:

```bash
REACT_APP_PHOTOS_API_URL=https://xyz.execute-api.us-east-1.amazonaws.com/dev/photos
REACT_APP_CHATS_API_URL=https://xyz.execute-api.us-east-1.amazonaws.com/dev/chats
```

In code: `process.env.REACT_APP_PHOTOS_API_URL`

In GitHub Actions, these are set in the build step from GitHub Secrets:

```yaml
- name: Build Project
  env:
    REACT_APP_PHOTOS_API_URL: ${{ secrets.PHOTOS_API_URL }}
    REACT_APP_CHATS_API_URL: ${{ secrets.CHATS_API_URL }}
  run: npm run build --prefix my-cloud-storage-app
```

If you need to change the API URL, you must update the secret and re-run the deployment. There is no way to change it at runtime without a rebuild.

#### GitHub Actions CI/CD

Two workflows:

**`deploy.yml`** — triggered on push to `main` with changes in `my-cloud-storage-app/**`:

```yaml
on:
  push:
    branches: [main]
    paths: ['my-cloud-storage-app/**']
  workflow_dispatch:

jobs:
  deploy:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: echo "$AWS_EXPORTS_CONTENT" > my-cloud-storage-app/src/aws-exports.js
      - run: npm ci --legacy-peer-deps
      - run: npm run build
      - uses: aws-actions/configure-aws-credentials@v4
      - run: aws s3 sync build/ s3://$S3_BUCKET_NAME --delete
```

The `--delete` flag removes files from S3 that no longer exist in `build/`. Without it, old JS bundles accumulate over time, and browsers may cache stale files.

**`terraform.yml`** — triggered on push to `main` with changes in `terraform/**`:

```yaml
- run: terraform plan -out=tfplan
- if: github.event_name == 'pull_request'
  uses: actions/github-script@v7
  # Posts plan as a PR comment
- if: github.ref == 'refs/heads/main' && github.event_name == 'push'
  run: terraform apply -auto-approve
```

The pattern of plan-on-PR, apply-on-merge is standard for infrastructure changes. It lets you review what will change before it happens.

#### Testing React Components

This project uses React Testing Library, which tests components from the user's perspective:

```javascript
test('shows folder section headings grouped by S3 prefix', async () => {
  list
    .mockResolvedValueOnce({ items: [{ key: 'misc/a.pdf', size: 100 }] })
    .mockResolvedValueOnce({ items: [{ key: 'uploads-landing/b.zip', size: 200 }] });
  renderOtherFilesPage();
  expect(await screen.findByText('Misc')).toBeInTheDocument();
  expect(screen.getByText('Uploads Landing')).toBeInTheDocument();
});
```

Key patterns:
- `screen.findByText` — async, waits for the element to appear (handles async state updates).
- `screen.getByText` — synchronous, fails if element is absent.
- `screen.queryByText` — synchronous, returns `null` if absent (for negative assertions).
- `jest.mock('aws-amplify/storage', ...)` — replaces the entire module with a mock.
- `mockResolvedValueOnce` — makes a mock return different values on successive calls.

### Lab: Adding a New Page End-to-End

**Goal**: A `/library/stats` page that shows total message count from the `/stats` endpoint built in Module 4.

**Step 1 — Create the page** (`my-cloud-storage-app/src/pages/StatsPage.jsx`)

```jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';

export default function StatsPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const load = async () => {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      const res = await fetch(process.env.REACT_APP_STATS_API_URL, {
        headers: { Authorization: token },
      });
      setStats(await res.json());
    };
    load();
  }, []);

  return (
    <main>
      <button onClick={() => navigate('/library')}>← Library</button>
      <h1>Stats</h1>
      {stats ? <p>Total messages: {stats[0]?.total}</p> : <p>Loading…</p>}
    </main>
  );
}
```

**Step 2 — Wire routing** (`App.js`)

```jsx
import StatsPage from './pages/StatsPage';
// In Routes:
<Route path="/library/stats" element={<StatsPage />} />
```

**Step 3 — Add nav button** (`LibraryPage.jsx`)

```jsx
<button onClick={() => navigate('/library/stats')}>Stats</button>
```

**Step 4 — Add environment variable**

In `.github/workflows/deploy.yml`:

```yaml
REACT_APP_STATS_API_URL: ${{ secrets.STATS_API_URL }}
```

Set the secret: `gh secret set STATS_API_URL --body "https://..."`

**Step 5 — Write tests**

```javascript
test('renders Stats heading', () => {
  renderStatsPage();
  expect(screen.getByRole('heading', { name: /stats/i })).toBeInTheDocument();
});

test('shows total messages from API', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    json: () => Promise.resolve([{ total: '42' }]),
  });
  renderStatsPage();
  expect(await screen.findByText(/total messages: 42/i)).toBeInTheDocument();
});
```

**Step 6 — Deploy**

```bash
git add . && git commit -m "Add stats page" && git push
# GitHub Actions deploys automatically
```

### Trade-offs

**Why Amplify Storage (`uploadData`) instead of direct S3 SDK calls?**

Amplify Storage handles multipart uploads for large files, retry logic, and Cognito credential injection. The equivalent with raw `@aws-sdk/client-s3` would require:
- Initializing the S3 client with Cognito Identity Pool credentials.
- Implementing multipart upload for files > 5 MB.
- Writing retry logic.

Amplify wraps all of this. The cost is a larger bundle size (~200 KB gzipped) and Amplify's opinionated folder structure.

**Why Create React App instead of Vite?**

CRA was the standard when this project started. Vite is faster (HMR in milliseconds vs seconds), has a smaller output bundle, and is actively maintained. For a new project today, use Vite. The migration from CRA to Vite is roughly an hour of work.

**Why S3 static hosting instead of CloudFront + S3?**

S3 static website hosting is simpler: no CDN to configure, no SSL certificate to provision, no edge locations to invalidate after deployment. For a personal project with one user, the latency from a single AWS region is acceptable.

The downsides: HTTP only (no HTTPS), no edge caching, no custom domain without Route 53 + ACM. Adding CloudFront is a single Terraform resource (`aws_cloudfront_distribution`) and two more (`aws_acm_certificate`, `aws_route53_record`) for a custom domain.

**Why bundle `aws-exports.js` from a GitHub secret instead of committing it?**

`aws-exports.js` contains your Cognito user pool ID, identity pool ID, and S3 bucket name. None of these are credentials per se (they are public-facing identifiers), but committing them associates your account IDs with the repository in git history forever. Using a secret keeps them out of version control and makes the configuration environment-specific.

### Exercises

1. **Dark mode toggle**: Add a dark mode CSS class that swaps background/text colors. Store the preference in `localStorage` so it persists across page reloads. Write a test that verifies the toggle changes the class on the root element.

2. **Infinite scroll**: Modify `PhotosPage.jsx` to load photos in batches of 20. When the user scrolls to the bottom of the page, fetch the next batch (use the `IntersectionObserver` API or the `onScroll` event). Update the `photos_api` Lambda to support a `cursor` query parameter.

3. **Error boundary**: Wrap each page in a React [Error Boundary](https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary). When any page crashes, show a friendly "Something went wrong" message instead of a blank screen. Write a test that renders a component that throws and verifies the fallback appears.

4. **Terraform + GitHub Actions**: Add a new GitHub Actions workflow that runs `npm test` on every PR that touches `my-cloud-storage-app/**`. The PR should not be mergeable if tests fail. (This requires setting a branch protection rule in the repo settings.)

5. **aws-exports.js validation**: The React app silently loads nothing if `aws-exports.js` is malformed. Add a validation step in `App.js` that checks for the required Amplify config keys at startup and shows a clear error message if they are missing.

### Check-Yourself Questions

1. What is the difference between `screen.findByText` and `screen.getByText`? When do you use each?
2. Why are React environment variables embedded at build time, not runtime? What are the implications for CI/CD?
3. What does `--delete` do in `aws s3 sync --delete`? What breaks without it?
4. Why does the GitHub Actions workflow plan on PR but apply only on merge to main?
5. Explain the `useEffect(() => { ... }, [])` pattern in React. What does the empty dependency array mean?
6. What is a stale closure in React? When can it affect API calls in hooks?

---

## Putting It All Together: Rebuild Checklist

Use this sequence when building from a blank AWS account:

```
Phase 1 — Bootstrap (once per account)
  □ terraform/bootstrap: create state bucket and DynamoDB lock table
  □ Configure Amplify CLI: amplify init → amplify add auth → amplify add storage → amplify push
  □ Note the Cognito user pool ARN and S3 bucket name

Phase 2 — Core Infrastructure
  □ Configure terraform/versions.tf with remote backend
  □ Create terraform/variables.tf with bucket name and Cognito ARN
  □ Create modules/storage: DynamoDB table + S3 data source
  □ terraform apply

Phase 3 — Event Pipelines
  □ Write whatsapp_bronze Lambda + tests
  □ Write photo_processor Lambda + tests (including Pillow build step)
  □ Add IAM role and policies in modules/compute
  □ Add S3 bucket notifications in root main.tf
  □ terraform apply
  □ Upload a test .txt file, verify bronze copy appears in S3

Phase 4 — Analytics
  □ Write glue_jobs/whatsapp_silver/job.py
  □ Add Glue job, crawler, Athena workgroup in modules/analytics
  □ terraform apply
  □ Run Glue job manually, verify silver Parquet in S3
  □ Query whatsapp_messages in Athena console

Phase 5 — APIs
  □ Write photos_api Lambda + tests
  □ Write whatsapp_api Lambda + tests
  □ Add API Gateway resources, methods, integrations, Cognito authorizer
  □ Add deployment trigger hashes
  □ terraform apply
  □ Test endpoints with curl + a valid Cognito token

Phase 6 — Frontend
  □ Create React app: npx create-react-app my-cloud-storage-app
  □ Add react-router-dom, aws-amplify, @aws-amplify/ui-react
  □ Create src/aws-exports.js from amplify pull
  □ Build pages: HomePage, LibraryPage, PhotosPage, WhatsAppPage, OtherFilesPage
  □ npm start, verify locally
  □ npm test, verify all tests pass

Phase 7 — CI/CD
  □ Create .github/workflows/deploy.yml
  □ Set GitHub secrets: AWS creds, exports, API URLs, S3 bucket
  □ Create .github/workflows/terraform.yml
  □ Push and verify both workflows succeed
```

---

## Cross-Cutting Design Principles

### 1. Fail loudly at ingestion, quietly at query time

The `whatsapp_bronze` Lambda rejects files that don't match the WhatsApp format. It is better to reject early (with a clear log message) than to let garbage into bronze that corrupts silver. At query time (API), returning an empty array is acceptable — the UI handles it gracefully.

### 2. Event-driven means no wasted compute

Nothing in this system polls or waits. S3 pushes events to Lambda. Lambda runs for milliseconds. The Glue job is only triggered when new data warrants it. At personal scale, the cost for the entire platform is under $10/month including storage.

### 3. Terraform owns infrastructure; Amplify owns identity

The hard boundary: Amplify-managed resources (Cognito, the S3 bucket) are referenced in Terraform as `data` sources, never as `resource` blocks. Crossing this boundary — trying to manage a Cognito User Pool in Terraform while Amplify also touches it — causes state drift and broken deployments.

### 4. Test data processing logic, not AWS

The Glue job has pure Python helper functions (`parse_date_iso`, `parse_file`, `make_message_id`) that are tested with pytest without any Spark or AWS dependencies. Lambda handlers are tested with `unittest.mock` patching boto3. The goal is fast, cheap tests that run in CI without an AWS account.

### 5. Single-table DynamoDB for simple access patterns

`PhotoMetadata` has one access pattern: "get all photos sorted by date" (full scan). One table, no GSI, no complex key design. If a second access pattern emerged (e.g., "find photos by camera model"), add a GSI then — not speculatively upfront.

---

## Quick Reference: Commands

```bash
# Infrastructure
cd terraform
terraform init
terraform plan
terraform apply
terraform output -raw photos_api_url

# Lambda tests
cd terraform/lambdas/whatsapp_bronze && python -m pytest -v
cd terraform/lambdas/photo_processor   && python -m pytest -v
cd terraform/lambdas/photos_api        && python -m pytest -v
cd terraform/lambdas/whatsapp_api      && python -m pytest -v
cd terraform/glue_jobs/whatsapp_silver && python -m pytest -v

# Frontend
cd my-cloud-storage-app
npm install --legacy-peer-deps
npm start
npm test

# Glue (manual run)
aws glue start-job-run \
  --job-name "data-engineering-whatsapp-silver-dev" \
  --region us-east-1

# Re-enable scheduled Glue trigger (set enabled = true, then)
terraform apply -target=aws_glue_trigger.whatsapp_silver_daily
```

---

*End of LEARNING.md*
