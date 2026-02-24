# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a monorepo. The primary application lives in `my-cloud-storage-app/`, a React app backed by AWS Amplify (Cognito + S3).

## Commands

All commands run from `my-cloud-storage-app/`:

```bash
npm start           # Dev server at localhost:3000
npm run build       # Production build to /build
npm test            # Run Jest tests
npm install --legacy-peer-deps  # Install deps (flag required due to peer dep conflicts)
```

## Architecture

**Frontend**: React 19 (Create React App) with AWS Amplify UI components for authentication.

**Authentication**: AWS Cognito via `<Authenticator>` wrapper in `App.js`. Email verification is required.

**Storage**: AWS S3 via Amplify's `uploadData()` API. Files are routed to different S3 prefixes based on extension:
- `.zip` → `uploads-landing/`
- `.txt` → `raw-whatsapp-uploads/`
- `.jpg/.jpeg/.png/.webp` → `raw-photos/`
- Everything else → `misc/`

S3 storage tier (Standard, Intelligent Tiering, Glacier Deep Archive) is selected by the user and attached as object metadata.

**AWS Config**: `src/aws-exports.js` is auto-generated and injected from the `AWS_EXPORTS_CONTENT` GitHub secret during CI. It is gitignored. The Amplify backend infrastructure (CloudFormation stacks) is defined under `amplify/backend/` — auth (Cognito) in `amplify/backend/auth/` and storage (S3) in `amplify/backend/storage/`.

## CI/CD

GitHub Actions (`.github/workflows/deploy.yml`) deploys on pushes to `main` that affect `my-cloud-storage-app/**`. The pipeline: generates `aws-exports.js` from secrets → builds → syncs build output to S3 with `--delete`.

Required GitHub secrets: `AWS_EXPORTS_CONTENT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`.
