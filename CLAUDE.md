# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

Monorepo with two top-level directories:
- `my-cloud-storage-app/` — React frontend backed by AWS Amplify (Cognito + S3)
- `terraform/` — Infrastructure as Code (Terraform ≥ 1.5, AWS provider ~5.0)

## Commands

### Frontend (`my-cloud-storage-app/`)

```bash
npm start                        # Dev server at localhost:3000
npm run build                    # Production build to /build
npm test                         # Run Jest tests (watch mode)
CI=true npm test -- --watchAll=false  # Run tests once (CI mode)
npm install --legacy-peer-deps   # Install deps (flag required due to peer dep conflicts)
```

### Terraform (`terraform/`)

```bash
AWS_PROFILE=personal terraform plan
AWS_PROFILE=personal terraform apply
AWS_PROFILE=personal terraform apply -target=<resource>  # partial apply
```

Always use `AWS_PROFILE=personal` — the default profile uses short-lived STS tokens that expire.

## Architecture

### Frontend

React 19 (Create React App), `react-router-dom` v6, AWS Amplify UI. Routing is defined in `App.js` with a catch-all `<Navigate to="/library">` for unknown paths.

Pages:
- `/` → `HomePage` — intro, file upload, Open Library button
- `/library` → `LibraryPage` — section cards (Photos, WhatsApp Messages, Other Files)
- `/library/photos` → `PhotosPage` — photo gallery with sort/tag filters, Cognito-authenticated fetch from `REACT_APP_PHOTOS_API_URL`
- `/library/whatsapp` → `WhatsAppPage` — chat messages with sender/search/date filters, fetch from `REACT_APP_CHATS_API_URL`
- `/library/files` → `OtherFilesPage` — lists `misc/` and `uploads-landing/` S3 prefixes via Amplify `list`/`getUrl`

**Authentication**: Cognito via `<Authenticator>` in `App.js`. All pages are behind auth.

**Storage uploads** route by file extension:
- `.zip` → `uploads-landing/`
- `.txt` → `raw-whatsapp-uploads/`
- `.jpg/.jpeg/.png/.webp` → `raw-photos/`
- Everything else → `misc/`

**AWS config**: `src/aws-exports.js` is gitignored and injected from the `AWS_EXPORTS_CONTENT` GitHub secret at build time. Amplify backend (Cognito, S3) lives under `amplify/backend/`.

### Backend Lambdas (`terraform/lambdas/`)

| Lambda | Trigger | Purpose |
|--------|---------|---------|
| `whatsapp_bronze` | S3 `raw-whatsapp-uploads/*.txt` | Copies text to bronze layer |
| `photo_processor` | S3 `raw-photos/` | Extracts EXIF, writes thumbnails, stores metadata in DynamoDB |
| `photos_api` | API GW `GET /photos` | Scans DynamoDB, returns pre-signed S3 URLs, supports `sort_by` and `tag` filters |
| `whatsapp_api` | API GW `GET /chats` | Queries Athena `whatsapp_messages` silver table, supports `date`/`sender`/`search`/`limit` params |

All Lambdas share one IAM role. `photos_api` and `whatsapp_api` are behind a Cognito User Pools authorizer; OPTIONS methods use MOCK CORS integration.

`photo_processor` is built with a cross-compiled Pillow layer (manylinux, x86_64) via a `null_resource` build step before packaging.

### Data Pipeline

WhatsApp `.txt` exports flow:
1. Upload → `raw-whatsapp-uploads/` (S3)
2. `whatsapp_bronze` Lambda → `bronze/whatsapp/`
3. Glue PySpark job (`whatsapp_silver`) → parses messages, writes Snappy Parquet to `silver/whatsapp/` partitioned by `date`, registers `whatsapp_messages` in Glue catalog
4. Athena queries via `whatsapp_api` Lambda

**Silver schema**: `message_id, time, sender, message, word_count, source_file, date (partition)`

### Terraform Module Layout

- `modules/storage` — references existing Amplify S3 bucket (data source) + DynamoDB `PhotoMetadata` table
- `modules/compute` — Lambda role/policies, all Lambda functions, API Gateway REST API with `/photos` and `/chats` resources
- `modules/analytics` — Glue catalog DB, Glue job, Glue trigger (currently disabled), Glue crawler (no schedule), Athena workgroup

Remote state: S3 + DynamoDB, bootstrapped from `terraform/bootstrap/`.

### Scheduled Jobs (currently disabled)

The Glue trigger and crawler schedules are disabled to avoid costs. To re-enable:
- **Glue trigger** (`modules/analytics/main.tf`): change `enabled = false` → `enabled = true`
- **Glue crawler** (`modules/analytics/main.tf`): uncomment `schedule = "cron(0 6 * * ? *)"`

Then `terraform apply`.

To run the Glue job manually:
```bash
AWS_PROFILE=personal aws glue start-job-run --job-name "data-engineering-whatsapp-silver-dev" --region us-east-1
```

## CI/CD

GitHub Actions (`.github/workflows/deploy.yml`) triggers on push to `main` (paths: `my-cloud-storage-app/**`) and `workflow_dispatch`. Pipeline: injects `aws-exports.js` from secrets → `npm install --legacy-peer-deps` → `npm run build` → `aws s3 sync build/ s3://$S3_BUCKET_NAME --delete`.

Required GitHub secrets: `AWS_EXPORTS_CONTENT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `PHOTOS_API_URL`, `CHATS_API_URL`.

**Known gotcha**: the global `~/.npmrc` on the dev machine points to a Nubank CodeArtifact registry. The project-level `my-cloud-storage-app/.npmrc` overrides this to `registry.npmjs.org` for CI.

## Testing

Frontend tests use `@testing-library/react` with `MemoryRouter`. Mocks live in `src/__mocks__/`:
- `amplifyAuthMock.js` — mapped to `aws-amplify/auth` via `jest.moduleNameMapper`
- `styleMock.js` — mapped to `*.css`

`aws-amplify/storage` and `@aws-amplify/ui-react` are mocked inline in `App.test.js`.

Backend Lambda tests use `pytest` with `unittest.mock`. Run from each Lambda's directory:
```bash
cd terraform/lambdas/<name> && python -m pytest test_handler.py -v
```
