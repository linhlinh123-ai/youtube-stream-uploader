# YouTube Uploader Service

Cloud Run service để upload video từ GCS lên YouTube qua Resumable Upload API.

## Deploy

```bash
gcloud run deploy uploader \
  --source . \
  --region=asia-southeast1 \
  --allow-unauthenticated
