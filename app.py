from flask import Flask, request, jsonify
import requests
import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

app = Flask(__name__)

# Load OAuth2 config
with open("config.json", "r") as f:
    oauth_config = json.load(f)

CLIENT_ID = oauth_config["client_id"]
CLIENT_SECRET = oauth_config["client_secret"]
REFRESH_TOKEN = oauth_config["refresh_token"]

TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_access_token():
    """Refresh access token from refresh_token."""
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    creds.refresh(Request())
    return creds.token


@app.route("/upload", methods=["POST"])
def upload_video():
    data = request.json
    download_url = data.get("download_url")
    title = data.get("title", "Untitled Video")
    description = data.get("description", "")
    tags = data.get("tags", [])
    privacy = data.get("privacy", "unlisted")
    callback_url = data.get("callback_url")

    if not download_url:
        return jsonify({"status": "error", "error": "Missing download_url"}), 400

    try:
        access_token = get_access_token()

        # Step 1: Initiate resumable upload
        init_url = (
            "https://www.googleapis.com/upload/youtube/v3/videos"
            "?uploadType=resumable&part=snippet,status"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
        }
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
            },
            "status": {"privacyStatus": privacy},
        }

        init_resp = requests.post(init_url, headers=headers, json=body)
        if init_resp.status_code not in [200, 201]:
            raise Exception(f"Init upload failed: {init_resp.text}")

        upload_url = init_resp.headers["Location"]

        # Step 2: Stream video from GCS to YouTube
        with requests.get(download_url, stream=True) as r:
            r.raise_for_status()
            upload_resp = requests.put(
                upload_url,
                data=r.raw,
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/*"},
            )

        if upload_resp.status_code not in [200, 201]:
            raise Exception(f"Upload failed: {upload_resp.text}")

        video_id = upload_resp.json()["id"]
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        result = {"status": "ok", "youtube_video_id": video_id, "youtube_url": youtube_url}

        # Callback nếu có
        if callback_url:
            try:
                requests.post(callback_url, json=result, timeout=10)
            except Exception as cb_err:
                print(f"Callback error: {cb_err}")

        return jsonify(result)

    except Exception as e:
        error_result = {"status": "error", "error": str(e)}
        if callback_url:
            try:
                requests.post(callback_url, json=error_result, timeout=10)
            except:
                pass
        return jsonify(error_result), 500


@app.route("/")
def health():
    return "Uploader Service is running!"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
