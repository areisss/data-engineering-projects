# Lambda Functions

This document covers the three Lambda functions in `terraform/lambdas/`. All are Python 3.12 and share a single IAM execution role with access to the main S3 bucket and the `PhotoMetadata` DynamoDB table.

---

## whatsapp_bronze

**Source**: `terraform/lambdas/whatsapp_bronze/handler.py`
**Memory / Timeout**: 256 MB / 60 s

### Trigger

S3 `ObjectCreated:*` on the main bucket, filtered to:
- Prefix: `raw-whatsapp-uploads/`
- Suffix: `.txt`

Configured in the root `main.tf` `aws_s3_bucket_notification` resource (not inside the module).

### What it does

For each record in the S3 event:

1. URL-decodes the object key (`urllib.parse.unquote_plus` handles spaces and special characters in filenames)
2. Reads the `.txt` file content from S3
3. Validates it is a WhatsApp export by checking that at least **2 of the first 20 non-empty lines** match the WhatsApp timestamp regex — accepts both US (`1/1/24, 10:00 AM`) and international (`01/01/2024, 10:00`) date formats, with or without square brackets
4. **Valid**: copies the file to `bronze/whatsapp/year=YYYY/month=MM/<filename>.txt` using the current UTC time for partitioning
5. **Invalid**: logs a "Skipped" message and moves on — the file remains in `raw-whatsapp-uploads/` but is never referenced again

### Inputs and outputs

| Direction | Detail |
|---|---|
| Input | S3 event `Records[]`; reads `s3://<bucket>/raw-whatsapp-uploads/<filename>.txt` |
| Output (success) | S3 object at `s3://<bucket>/bronze/whatsapp/year=YYYY/month=MM/<filename>.txt` |
| Output (invalid file) | No S3 write; log line only |

### Error handling and retries

There is no `try/except` in the handler loop. Any AWS SDK error (e.g. `s3:GetObject` or `s3:CopyObject` failure) raises an unhandled exception, which causes Lambda to return a failure status.

S3 invokes Lambda asynchronously from bucket notifications with **2 automatic retries** (3 total attempts) before the event is dropped. Retries are safe: `CopyObject` to the same destination key overwrites the existing object, so re-processing the same file produces the same result.

Invalid files (format mismatch) are silently skipped — they do not cause retries and are not moved or deleted.

---

## photo_processor

**Source**: `terraform/lambdas/photo_processor/handler.py`
**Memory / Timeout**: 512 MB / 60 s
**Architecture**: `x86_64` (required by the Pillow binary wheels)

### Trigger

S3 `ObjectCreated:*` on the main bucket, filtered to:
- Prefix: `raw-photos/`
- No suffix filter — all image formats (`.jpg`, `.jpeg`, `.png`, `.webp`) are accepted

Configured in the root `main.tf` `aws_s3_bucket_notification` resource.

### What it does

For each record in the S3 event:

1. URL-decodes the key and reads the image bytes from S3, also capturing the `ContentType` from the object metadata
2. Copies the original image to `photos/originals/<filename>` (preserves the original unmodified)
3. Generates a thumbnail using Pillow:
   - Resizes to fit within **300 × 300 px** on the longest side (LANCZOS resampling); images already smaller than 300 px are not enlarged
   - Converts `RGBA`, `LA`, or palette-mode images to `RGB` before saving as JPEG to prevent format errors
4. Writes the thumbnail to `photos/thumbnails/<filename>`
5. Records metadata in DynamoDB `PhotoMetadata`:

| Attribute | Value |
|---|---|
| `photo_id` | Random UUID (new on every invocation) |
| `filename` | Basename of the S3 key |
| `original_key` | `photos/originals/<filename>` |
| `thumbnail_key` | `photos/thumbnails/<filename>` |
| `source_key` | Original upload key (`raw-photos/<filename>`) |
| `width` / `height` | Pixel dimensions of the original |
| `size_bytes` | Byte length of the original image data |
| `content_type` | From S3 object metadata |
| `uploaded_at` | UTC ISO-8601 timestamp at processing time |

### Inputs and outputs

| Direction | Detail |
|---|---|
| Input | S3 event `Records[]`; reads `s3://<bucket>/raw-photos/<filename>` |
| Output — S3 original | `s3://<bucket>/photos/originals/<filename>` |
| Output — S3 thumbnail | `s3://<bucket>/photos/thumbnails/<filename>` (≤300 px, same format) |
| Output — DynamoDB | One new item in `PhotoMetadata` per image |

### Error handling and retries

There is no `try/except` in the handler. An unhandled exception (S3 read/write error, Pillow decode error for a corrupt file, DynamoDB write error) causes the invocation to fail.

S3 invokes Lambda asynchronously with **2 automatic retries**. **Retries are partially idempotent**: the two S3 writes (`CopyObject` for the original, `PutObject` for the thumbnail) overwrite the same keys safely. However, the DynamoDB `put_item` uses a freshly generated UUID on each attempt — a retry after a partial failure (S3 succeeded, DynamoDB failed) will create a **duplicate DynamoDB record** for the same image. At personal scale this is an accepted trade-off; resolving it would require a deterministic ID (e.g. a hash of the source key).

If a batch event contains multiple records and one fails mid-loop, records already processed in the same invocation are not rolled back.

---

## photos_api

**Source**: `terraform/lambdas/photos_api/handler.py`
**Memory / Timeout**: 256 MB / 30 s

### Trigger

API Gateway REST API — `GET /photos` and `OPTIONS /photos` on the `dev` stage. The `GET` method is protected by a `COGNITO_USER_POOLS` authorizer; the `OPTIONS` preflight uses a `MOCK` integration and requires no authentication.

The React app calls this endpoint with the Cognito `idToken` in the `Authorization` header.

### What it does

**OPTIONS request** (CORS preflight):
- Returns `200` immediately with `Access-Control-Allow-*` headers
- No DynamoDB or S3 calls

**GET request**:
1. Scans the entire `PhotoMetadata` DynamoDB table using paginated `scan()` calls (follows `LastEvaluatedKey` until exhausted)
2. Sorts results by `uploaded_at` descending (newest first)
3. For each item, generates two pre-signed S3 URLs:
   - `thumbnail_url` — expires in **1 hour** (`photos/thumbnails/<filename>`)
   - `original_url` — expires in **24 hours** (`photos/originals/<filename>`)
4. Returns a JSON array with all item fields plus the two URLs; DynamoDB `Decimal` values are serialised as integers or floats

### Inputs and outputs

| Direction | Detail |
|---|---|
| Input | API Gateway event; `httpMethod` determines GET vs OPTIONS path |
| Output | JSON array of photo objects, each with all DynamoDB attributes plus `thumbnail_url` and `original_url` |

**Example response item:**
```json
{
  "photo_id": "9d819f2b-...",
  "filename": "photo.jpg",
  "original_key": "photos/originals/photo.jpg",
  "thumbnail_key": "photos/thumbnails/photo.jpg",
  "width": 3024,
  "height": 4032,
  "size_bytes": 2979,
  "content_type": "image/jpeg",
  "uploaded_at": "2026-02-25T10:34:09.144830+00:00",
  "source_key": "raw-photos/photo.jpg",
  "thumbnail_url": "https://<bucket>.s3.amazonaws.com/photos/thumbnails/photo.jpg?...",
  "original_url": "https://<bucket>.s3.amazonaws.com/photos/originals/photo.jpg?..."
}
```

### Error handling and retries

There is no `try/except` in the handler. An unhandled exception propagates to the Lambda runtime, which returns a `200` envelope with an error payload to API Gateway; API Gateway translates this to a **502 Bad Gateway** response to the browser.

This Lambda is invoked **synchronously** by API Gateway — there are no automatic Lambda retries. The browser (or React app) must retry on 5xx if needed.

CORS headers are included on the `OPTIONS` response via the `MOCK` integration response configured in Terraform, and on the `GET` response via the Lambda itself, ensuring CORS works even if the Lambda returns an error.

---

## Running tests locally

Each Lambda has a `test_handler.py` alongside it. Tests use only the stdlib `unittest` / `pytest` and mock all AWS clients — no live AWS calls are made.

```bash
# whatsapp_bronze and photo_processor use unittest
python -m pytest terraform/lambdas/whatsapp_bronze/test_handler.py
python -m pytest terraform/lambdas/photo_processor/test_handler.py

# photos_api uses pytest
python -m pytest terraform/lambdas/photos_api/test_handler.py
```

`photo_processor` tests require Pillow to be installed locally:
```bash
pip install pillow
```
