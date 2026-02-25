# Terraform

All infrastructure is defined in the `terraform/` directory using Terraform ≥ 1.5 with the AWS provider `~> 5.0`.

Remote state is stored in S3 (`artur-file-processor-tf-state`, key `terraform/terraform.tfstate`) with locking via DynamoDB (`terraform-locks`). Both were created by the `bootstrap/` one-time setup.

---

## Module layout

```
terraform/
├── bootstrap/          # One-time: creates remote state bucket + lock table
├── modules/
│   ├── storage/        # DynamoDB table; S3 bucket reference
│   ├── compute/        # Lambda functions, IAM, API Gateway
│   └── analytics/      # Glue job, Crawler, Athena workgroup
├── lambdas/            # Python source for each Lambda
├── glue_jobs/          # Python source for the Glue job
├── main.tf             # Root: wires modules + S3 bucket notifications
├── variables.tf        # Region, project name, bucket name, Cognito pool ARN
├── outputs.tf          # Surfaces key resource names/URLs after apply
└── versions.tf         # Provider constraints + S3 backend config
```

---

## modules/storage

### What it creates

| Resource | Type | Notes |
|---|---|---|
| `data.aws_s3_bucket.main` | Data source (read-only) | References the existing Amplify-managed S3 bucket; Terraform does not own or destroy it |
| `aws_dynamodb_table.photo_metadata` | DynamoDB table | `PAY_PER_REQUEST` billing; partition key `photo_id` (String); no sort key |

### Variables

| Variable | Description |
|---|---|
| `project_name` | Prefix for resource names (default: `data-engineering`) |
| `environment` | Deployment environment (default: `dev`) |
| `existing_bucket_name` | Name of the Amplify S3 bucket to reference |

### Outputs

| Output | Value |
|---|---|
| `bucket_id` | S3 bucket name |
| `bucket_arn` | S3 bucket ARN |
| `photo_metadata_table_name` | DynamoDB table name |
| `photo_metadata_table_arn` | DynamoDB table ARN |

---

## modules/compute

### What it creates

**IAM**
- One shared Lambda execution role (`AWSLambdaBasicExecutionRole` + inline policy granting `s3:GetObject/PutObject/DeleteObject/ListBucket` on the main bucket and full CRUD on the DynamoDB table)

**Lambda functions**

| Function | Memory | Timeout | Trigger | Notable |
|---|---|---|---|---|
| `whatsapp_bronze` | 256 MB | 60 s | S3 `ObjectCreated` on `raw-whatsapp-uploads/*.txt` | Single-file zip (no extra deps) |
| `photo_processor` | 512 MB | 60 s | S3 `ObjectCreated` on `raw-photos/*` | Pillow bundled; re-built via `null_resource` when `handler.py` changes (detected by MD5) |
| `photos_api` | 256 MB | 30 s | API Gateway `GET /photos` | Single-file zip |

The `photo_processor` build works as follows: a `null_resource` runs `pip install pillow` targeting `lambdas/photo_processor/package/` using the `manylinux_2_28_x86_64` / `cp312` platform wheels (compatible with Amazon Linux 2023). An `archive_file` data source then zips the entire `package/` directory. The trigger is the MD5 of `handler.py`, so Pillow is only re-installed when the handler changes.

**API Gateway**
- REST API with a single resource `/photos`
- `GET /photos`: `AWS_PROXY` integration → `photos_api` Lambda; protected by a `COGNITO_USER_POOLS` authorizer
- `OPTIONS /photos`: `MOCK` integration returning CORS headers (no auth required); handles browser preflight requests
- Stage named after `var.environment` (e.g. `dev`); deployment is automatically re-triggered when any method or integration changes

### Variables

| Variable | Description |
|---|---|
| `bucket_id` | S3 bucket name (injected into Lambda env vars) |
| `bucket_arn` | S3 bucket ARN (used in IAM policy + S3 notification permission) |
| `dynamodb_arn` | DynamoDB table ARN (IAM policy) |
| `dynamodb_table_name` | DynamoDB table name (injected into Lambda env vars) |
| `cognito_user_pool_arn` | Cognito User Pool ARN for the API Gateway authorizer |

### Outputs

| Output | Value |
|---|---|
| `lambda_role_arn` | Shared Lambda IAM role ARN |
| `lambda_role_name` | Shared Lambda IAM role name |
| `whatsapp_bronze_lambda_arn` | ARN of the whatsapp_bronze function |
| `photo_processor_lambda_arn` | ARN of the photo_processor function |
| `photos_api_url` | Full URL of the `GET /photos` endpoint (e.g. `https://<id>.execute-api.us-east-1.amazonaws.com/dev/photos`) |

---

## modules/analytics

### What it creates

**IAM**
- One Glue service role (`AWSGlueServiceRole` + inline policy granting `s3:GetObject/PutObject/ListBucket` on the main bucket)

**Glue**

| Resource | Description |
|---|---|
| `aws_glue_catalog_database` | Catalog database named `<project>_<env>` |
| `aws_s3_object` (script) | Uploads `glue_jobs/whatsapp_silver/job.py` to `s3://<bucket>/glue-scripts/whatsapp_silver/job.py`; re-uploaded when the file changes (etag-tracked) |
| `aws_glue_job` | Python Shell job, Glue 3.0, Python 3.9, 0.0625 DPU (minimum); `awswrangler` installed via `--additional-python-modules`; 60-minute timeout |
| `aws_glue_trigger` | Scheduled trigger: runs the Glue job daily at **05:00 UTC** |
| `aws_glue_crawler` | Targets `s3://<bucket>/silver/whatsapp/`; runs daily at **06:00 UTC** (one hour after the job) to refresh partition metadata |

**Athena**
- Workgroup named `<project>-<env>`; query results written to `s3://<bucket>/athena-results/`

### Variables

| Variable | Description |
|---|---|
| `bucket_id` | S3 bucket name (script location, Athena results, Glue job argument) |
| `bucket_arn` | S3 bucket ARN (IAM policy) |

### Outputs

| Output | Value |
|---|---|
| `glue_database_name` | Glue catalog database name |
| `glue_job_name` | Glue job name |
| `glue_crawler_name` | Glue crawler name |
| `athena_workgroup_name` | Athena workgroup name |
| `glue_role_arn` | Glue IAM role ARN |

---

## Root module

`main.tf` at the root wires the three modules together and owns the `aws_s3_bucket_notification` resource. S3 bucket notifications are defined here (not inside `modules/compute`) because AWS only allows one notification configuration per bucket — defining both triggers in the root module avoids a conflict when multiple Lambdas need the same bucket.

`outputs.tf` surfaces the most useful values after `terraform apply`:
- `photos_api_url` — paste this into the `PHOTOS_API_URL` GitHub secret
- `photo_metadata_table_name`, `glue_database_name`, `athena_workgroup_name`, `lambda_role_arn`, `glue_job_name`

---

## Typical workflows

### First-time setup

```bash
# 1. Create remote state infrastructure (once per AWS account)
cd terraform/bootstrap
terraform init
terraform apply
# Creates: artur-file-processor-tf-state S3 bucket + terraform-locks DynamoDB table

# 2. Pre-build the Pillow package (required before plan on a clean checkout)
pip install pillow \
  --platform manylinux_2_28_x86_64 \
  --implementation cp \
  --python-version 312 \
  --abi cp312 \
  --only-binary=:all: \
  --target terraform/lambdas/photo_processor/package
cp terraform/lambdas/photo_processor/handler.py \
   terraform/lambdas/photo_processor/package/handler.py

# 3. Initialise and apply
cd terraform
terraform init
terraform plan
terraform apply
```

After apply, retrieve the API URL:

```bash
terraform output photos_api_url
```

Set this as the `PHOTOS_API_URL` GitHub Actions secret to wire it into the React frontend.

### Updating infrastructure safely

```bash
cd terraform

# See what will change before touching anything
terraform plan

# Apply only after reviewing the plan output
terraform apply
```

Things to watch for in the plan output:

- **`aws_api_gateway_deployment` replacement** — any change to a method or integration forces a new deployment. This is expected and handled by `create_before_destroy = true`; there is no downtime.
- **`null_resource.build_photo_processor` replacement** — triggered when `handler.py` changes. Terraform will re-run `pip install pillow` locally before zipping. CI does this automatically; locally you can also let Terraform handle it.
- **`aws_s3_bucket_notification` update** — modifying either S3 trigger briefly replaces the whole notification config on the bucket. Both triggers are always re-applied atomically.
- **`aws_dynamodb_table` changes** — billing mode and attribute changes may require replacement. Check the plan carefully before applying.

### CI behaviour

The `terraform.yml` workflow runs on pushes and PRs that affect `terraform/**`:
- On PRs: runs `fmt -check`, `validate`, and `plan`; posts the plan as a PR comment
- On push to `main`: runs `apply` automatically after plan succeeds

The CI job pre-builds the Pillow package before `terraform init` so that `archive_file` can zip it during `plan`.
