# Personal Data Engineering Platform

A personal AWS data platform for storing files, processing photos, and analysing WhatsApp chat exports. Built with a React frontend, event-driven Lambda pipelines, a Glue/Athena data lakehouse, and all infrastructure managed by Terraform.

## What it does

| Capability | Flow |
|---|---|
| **Photo gallery** | Upload image → Lambda generates thumbnail + writes metadata to DynamoDB → React gallery displays thumbnails with pre-signed download links |
| **WhatsApp analytics** | Upload `.txt` export → Lambda validates & archives to bronze layer → daily Glue job parses chats into Parquet (silver) → query with Athena |
| **Cloud storage** | Upload any file → routed to the right S3 prefix by type; storage class (Standard / Intelligent-Tiering / Glacier Deep Archive) chosen at upload time |

## Architecture

```
Browser (React + Cognito)
│
├── S3 upload (Amplify)
│   ├── raw-photos/           → photo_processor Lambda (Pillow thumbnail + DynamoDB)
│   └── raw-whatsapp-uploads/ → whatsapp_bronze Lambda (validate + Hive-partition)
│
├── API Gateway (Cognito authorizer)
│   └── GET /photos           → photos_api Lambda (DynamoDB scan + pre-signed URLs)
│
└── Glue / Athena (WhatsApp lakehouse)
    ├── bronze/whatsapp/year=YYYY/month=MM/     ← raw validated exports
    ├── silver/whatsapp/ (Parquet, date-partitioned) ← daily Glue job
    └── Glue Crawler + Athena workgroup
```

All data lives in a single S3 bucket. DynamoDB `PhotoMetadata` table stores photo metadata. The React app is deployed as a static site to a separate S3 bucket.

## Running locally

```bash
cd my-cloud-storage-app
npm install --legacy-peer-deps
npm start          # dev server at localhost:3000
npm test           # Jest test suite
```

The app requires `src/aws-exports.js` with your Amplify config. In CI this is injected from `AWS_EXPORTS_CONTENT`. Locally, run `amplify pull` or copy the file from a teammate.

The photo gallery also needs `REACT_APP_PHOTOS_API_URL` pointing at the API Gateway endpoint. Set it in your shell or a `.env.local` file:

```
REACT_APP_PHOTOS_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/dev/photos
```

## Deploying

### One-time bootstrap (remote state)

```bash
cd terraform/bootstrap
terraform init && terraform apply
```

Creates the S3 bucket and DynamoDB table used for Terraform state locking.

### Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

CI runs `plan` on every PR and `apply` automatically on pushes to `main` that touch `terraform/**`.

The `photo_processor` Lambda bundles Pillow for `linux/x86_64`. CI installs it before running Terraform. Locally you need to do the same before the first `plan`:

```bash
pip install pillow \
  --platform manylinux_2_28_x86_64 --implementation cp \
  --python-version 312 --abi cp312 --only-binary=:all: \
  --target terraform/lambdas/photo_processor/package
cp terraform/lambdas/photo_processor/handler.py \
   terraform/lambdas/photo_processor/package/handler.py
```

### Frontend

Pushed automatically by the `deploy.yml` workflow on pushes to `main` that touch `my-cloud-storage-app/**`.

Required GitHub secrets:

| Secret | Purpose |
|---|---|
| `AWS_EXPORTS_CONTENT` | Full contents of `src/aws-exports.js` |
| `PHOTOS_API_URL` | API Gateway URL injected as `REACT_APP_PHOTOS_API_URL` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Deploy credentials |
| `S3_BUCKET_NAME` | Website hosting bucket |

## Folder structure

```
.github/workflows/
  deploy.yml          # React build + S3 sync
  terraform.yml       # Terraform plan/apply

my-cloud-storage-app/ # React frontend (CRA)
  amplify/            # Amplify CLI backend config (Cognito + S3)
  src/
    App.js            # Upload UI, photo gallery, file list

terraform/
  bootstrap/          # One-time state bucket + lock table
  modules/
    storage/          # DynamoDB PhotoMetadata table; references Amplify S3 bucket
    compute/          # Lambda functions + IAM + API Gateway
    analytics/        # Glue catalog, Crawler, Athena workgroup
  lambdas/
    photo_processor/  # Pillow thumbnail generation + DynamoDB write
    photos_api/       # DynamoDB scan + pre-signed URL generation
    whatsapp_bronze/  # WhatsApp format validation + bronze archival
  glue_jobs/
    whatsapp_silver/  # Daily chat parser → Parquet silver layer
  main.tf             # Wires modules + S3 bucket notifications
  variables.tf        # Region, project name, bucket name, Cognito pool ARN
```
