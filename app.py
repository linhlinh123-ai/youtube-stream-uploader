import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/upload", methods=["POST"])
def upload_video():
    data = request.get_json(force=True)

    download_url = data.get("download_url")
    access_token = data.get("access_token")   # n8n truyền access_token vào
    title = data.get("title", "Untitled")
    description = data.get("description", "")
    tags = data.get("tags", [])
    privacy = data.get("privacy", "unlisted")
    callback_url = data.get("callback_url")

    if not download_url or not access_token:
        return jsonify({"status": "error", "error": "Missing download_url or access_token"}), 400

    try:
        # Step 1: tạo phiên upload resumable
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*"
        }
        body = {
            "snippet": {"title": title, "description": description, "tags": tags},
            "status": {"privacyStatus": privacy}
        }

        init_resp = requests.post(init_url, headers=headers, json=body, timeout=30)
        if init_resp.status_code not in (200, 201):
            raise RuntimeError(f"Init upload failed: {init_resp.status_code} {init_resp.text}")

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            raise RuntimeError("No upload URL returned from YouTube")

        # Step 2: stream dữ liệu từ GCS sang YouTube
        with requests.get(download_url, stream=True, timeout=60) as source:
            source.raise_for_status()
            upload_resp = requests.put(
                upload_url,
                data=source.raw,
                headers={"Content-Type": "video/*"},
                timeout=3600
            )

        if upload_resp.status_code not in (200, 201):
            raise RuntimeError(f"Upload failed: {upload_resp.status_code} {upload_resp.text}")

        video_id = upload_resp.json().get("id")
        if not video_id:
            raise RuntimeError("Upload finished but no video ID returned")

        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        result = {"status": "ok", "youtube_video_id": video_id, "youtube_url": youtube_url}

        # Callback nếu có
        if callback_url:
            try:
                requests.post(callback_url, json=result, timeout=10)
            except Exception as cb_e:
                print("Callback error:", cb_e)

        return jsonify(result)

    except Exception as e:
        err = {"status": "error", "error": str(e)}
        if callback_url:
            try:
                requests.post(callback_url, json=err, timeout=10)
            except:
                pass
        return jsonify(err), 500


@app.route("/")
def health():
    return "Uploader is running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
