# Architecture

This document describes the system design of the personal data engineering platform: how data moves through the pipeline, what each AWS resource does, and the trade-offs behind key decisions.

## System overview

```
┌─────────────────────────────────────────────────────┐
│                  React App (S3 static)              │
│  Cognito auth │ file upload │ photo gallery         │
└────────┬──────────────┬──────────────────┬──────────┘
         │              │                  │
         ▼              ▼                  ▼
    Cognito UP     S3 (Amplify)      API Gateway
                        │            (GET /photos)
          ┌─────────────┤                  │
          │             │                  ▼
   raw-whatsapp-  raw-photos/       photos_api Lambda
   uploads/             │                  │
          │             │                  ▼
          ▼             ▼              DynamoDB
  whatsapp_bronze  photo_processor   PhotoMetadata
     Lambda           Lambda
          │         ┌──┴──────────┐
          ▼         ▼             ▼
  bronze/whatsapp/ photos/     photos/
  (partitioned)   originals/  thumbnails/
          │
          ▼
   Glue Python Shell job (daily)
          │
          ▼
   silver/whatsapp/ (Parquet)
          │
          ▼
   Glue Crawler → Glue Catalog → Athena
```

---

## Data flows

### WhatsApp pipeline

```
1. User uploads .txt export via React app
        │
        ▼
2. Amplify Storage puts object at s3://main-bucket/raw-whatsapp-uploads/<filename>.txt
        │
        ▼  (S3 ObjectCreated event)
3. whatsapp_bronze Lambda
   - Reads the file; checks ≥2 lines match WhatsApp timestamp regex
   - If valid: copies to bronze/whatsapp/year=YYYY/month=MM/<filename>.txt
   - If invalid: logs and skips (file stays in raw-whatsapp-uploads/ unreferenced)
        │
        ▼  (daily Glue job, 05:00 UTC)
4. whatsapp_silver Glue Python Shell job
   - Scans all .txt files under bronze/whatsapp/
   - Parses each line with regex into (date, time, sender, message)
   - Concatenates all files into a single DataFrame
   - Writes Parquet to silver/whatsapp/ partitioned by date
   - Registers/updates the whatsapp_messages table in the Glue catalog
   - Mode: overwrite_partitions (re-processes existing dates on re-run)
        │
        ▼  (Glue Crawler, 06:00 UTC)
5. Glue Crawler refreshes partition metadata in the catalog
        │
        ▼
6. Athena queries silver/whatsapp/ via the data catalog
```

### Photo pipeline

```
1. User uploads image (.jpg/.jpeg/.png/.webp) via React app
        │
        ▼
2. Amplify Storage puts object at s3://main-bucket/raw-photos/<filename>
        │
        ▼  (S3 ObjectCreated event)
3. photo_processor Lambda (Python + Pillow, linux/x86_64 layer)
   - Reads the image bytes
   - Copies original to photos/originals/<filename>
   - Resizes to ≤300px on the longest side (LANCZOS), converts RGBA→RGB for JPEG
   - Writes thumbnail to photos/thumbnails/<filename>
   - Writes item to DynamoDB PhotoMetadata:
       photo_id (UUID), filename, original_key, thumbnail_key,
       width, height, size_bytes, content_type, uploaded_at, source_key
        │
        ▼
4. React app calls GET /photos (API Gateway → photos_api Lambda)
   - Lambda scans PhotoMetadata table (paginated)
   - Generates pre-signed S3 URLs: thumbnail (1h TTL), original (24h TTL)
   - Returns JSON array sorted by uploaded_at descending
        │
        ▼
5. React gallery renders thumbnails; Download link uses original pre-signed URL
```

---

## AWS resources

### S3 (two buckets)

**Main data bucket** (Amplify-managed, referenced by Terraform as a `data` source):

| Prefix | Contents | Written by |
|---|---|---|
| `raw-whatsapp-uploads/` | Original .txt uploads | React app (Amplify) |
| `raw-photos/` | Original image uploads | React app (Amplify) |
| `uploads-landing/` | ZIP files | React app (Amplify) |
| `misc/` | All other file types | React app (Amplify) |
| `bronze/whatsapp/year=Y/month=MM/` | Validated WhatsApp exports | whatsapp_bronze Lambda |
| `silver/whatsapp/` | Parquet, partitioned by date | whatsapp_silver Glue job |
| `photos/originals/` | Full-size copies | photo_processor Lambda |
| `photos/thumbnails/` | Resized thumbnails (≤300px) | photo_processor Lambda |

**Website hosting bucket**: serves the compiled React app as a public static site.

### Lambda functions

| Function | Trigger | Runtime | Key dependencies |
|---|---|---|---|
| `whatsapp_bronze` | S3 ObjectCreated on `raw-whatsapp-uploads/*.txt` | Python 3.12 | boto3 (stdlib) |
| `photo_processor` | S3 ObjectCreated on `raw-photos/*` | Python 3.12 | Pillow (bundled), boto3 |
| `photos_api` | API Gateway GET /photos | Python 3.12 | boto3 |

All three Lambdas share a single IAM role scoped to the main S3 bucket and the PhotoMetadata DynamoDB table.

### DynamoDB — `PhotoMetadata`

- Partition key: `photo_id` (UUID string)
- No sort key; queries are full-table scans (acceptable at personal scale)
- `photos_api` Lambda paginates scans automatically via `LastEvaluatedKey`

### API Gateway

- Single resource: `GET /photos`
- Authorization: `COGNITO_USER_POOLS` authorizer backed by the same Cognito User Pool as the React app — only authenticated users can call the API
- CORS handled in the Lambda response (`OPTIONS` returns 200 immediately)

### Glue

- **Database**: one catalog database for the project
- **Python Shell job** (`whatsapp_silver`): runs on a single DPU (0.0625 DPU minimum), uses `awswrangler` for Parquet + catalog registration
- **Crawler**: runs at 06:00 UTC (one hour after the job) to pick up any new partitions the job did not register itself

### Athena

- Dedicated workgroup with results written to S3
- Queries the Glue catalog table `whatsapp_messages` directly over `silver/whatsapp/`

### Amplify / Cognito

- Amplify CLI manages the Cognito User Pool and S3 bucket via CloudFormation (outside Terraform scope)
- The React app uses `@aws-amplify/ui-react` for the hosted sign-in/sign-up UI
- Storage uploads go through Amplify's `uploadData()` which attaches SigV4 credentials from the Cognito Identity Pool
- The Cognito User Pool ARN is passed into Terraform as a variable to wire up the API Gateway authorizer

---

## How the React app interacts with the backend

```
User action            React call              AWS service
─────────────────────────────────────────────────────────
Sign in/up         →   Amplify Authenticator  → Cognito User Pool
Upload file        →   uploadData()           → S3 (via Identity Pool credentials)
View photo gallery →   fetch(PHOTOS_API_URL,  → API Gateway → photos_api Lambda
                         Authorization: idToken)   → DynamoDB scan
                                                   → S3 presigned URLs
Download photo     →   <a href={original_url}>→ S3 presigned URL (direct, no Lambda)
List all files     →   list()                 → S3 ListObjectsV2 (Amplify)
Delete file        →   remove()               → S3 DeleteObject (Amplify)
```

The `idToken` (not `accessToken`) is sent in the `Authorization` header because API Gateway's Cognito authorizer validates ID tokens by default.

---

## Trade-offs and assumptions

### Partitioning strategy
Bronze is partitioned by `year=` / `month=` — coarse enough that the daily Glue job can list all files with a single prefix scan. Silver is partitioned by `date` (daily), which matches the most common Athena query pattern ("messages on a given day" or "messages in a date range"). A finer partition (e.g. by sender) would require schema foreknowledge and complicate re-processing.

### Glue job re-processing
`mode=overwrite_partitions` means re-running the job on the same day overwrites only the affected date partitions, leaving older partitions intact. This is safe for append-only chat data but means edits to already-processed files will not propagate unless the partition is manually dropped.

### DynamoDB scan vs. query
`PhotoMetadata` uses a full-table scan because the access pattern is always "return all photos". At personal scale (hundreds to low thousands of photos) this is fast and cheap. A GSI on `uploaded_at` would be needed if the table grew large or if per-user filtering were added.

### Single S3 bucket
Keeping all data (uploads, bronze, silver, photos) in one bucket simplifies IAM — the Lambda role needs access to one ARN. The trade-off is that a misconfigured policy could expose unrelated prefixes. A multi-bucket design would provide better blast-radius isolation but adds cross-bucket IAM complexity.

### Pillow bundled per-deploy
Pillow is compiled for `manylinux_2_28_x86_64` / `cp312` and zipped into the Lambda deployment package. This avoids Lambda Layers but means the CI step must re-install Pillow before every `terraform plan` (the `archive_file` data source zips the package directory at plan time). A Lambda Layer would decouple the library from the function code but adds a separate versioning concern.

### Pre-signed URL TTLs
Thumbnail URLs expire in 1 hour (short, since they are loaded immediately on page open). Original download URLs expire in 24 hours (long, to support deferred downloads). Both TTLs are constants in `photos_api/handler.py` — they are not configurable at runtime.

### No CloudFront
The React app is served directly from S3 without a CDN. This keeps costs near zero for personal use but means latency varies by geography and there is no HTTPS termination at the edge (the S3 website endpoint is HTTP). Adding CloudFront would require TLS certificate management via ACM.

### Cognito managed by Amplify CLI, not Terraform
The Cognito User Pool and S3 bucket were created by `amplify push` and are intentionally left outside Terraform to avoid conflicts with Amplify's own CloudFormation stacks. Terraform references them as `data` sources or via variable ARNs. The implication is that destroying the Terraform state does not destroy auth infrastructure.
