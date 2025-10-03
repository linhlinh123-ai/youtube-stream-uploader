# YouTube Uploader Service (Container B)

Service chạy trên Cloud Run để upload video từ GCS lên YouTube.  
Nó nhận access_token từ n8n, do đó không cần lưu refresh_token hay client_secret trong container.

---

## Deploy

```bash
gcloud run deploy youtube-uploader \
  --source . \
  --region=asia-southeast1 \
  --allow-unauthenticated
