# app.py
import os
import json
import requests
from flask import Flask, request, jsonify
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

app = Flask(__name__)
TOKEN_URI = "https://oauth2.googleapis.com/token"

def load_oauth_config():
    """
    Try in order:
     1) YT_CONFIG env var (JSON string with keys client_id, client_secret, refresh_token)
     2) Individual env vars YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
    """
    cfg_raw = os.environ.get("YT_CONFIG")
    if cfg_raw:
        try:
            cfg = json.loads(cfg_raw)
            return cfg.get("client_id"), cfg.get("client_secret"), cfg.get("refresh_token")
        except Exception as e:
            raise RuntimeError("YT_CONFIG exists but is not valid JSON: " + str(e))

    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    return client_id, client_secret, refresh_token


def get_access_token(client_id, client_secret, refresh_token):
    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError("Missing OAuth config (client_id/client_secret/refresh_token).")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret
    )
    # refresh to get an access token
    creds.refresh(Request())
    return creds.token


@app.route("/upload", methods=["POST"])
def upload_video():
    data = request.get_json(force=True)
    download_url = data.get("download_url")
    title = data.get("title", "Untitled")
    description = data.get("description", "")
    tags = data.get("tags", [])
    privacy = data.get("privacy", "unlisted")
    callback_url = data.get("callback_url")

    if not download_url:
        return jsonify({"status": "error", "error": "Missing download_url"}), 400

    try:
        client_id, client_secret, refresh_token = load_oauth_config()
        access_token = get_access_token(client_id, client_secret, refresh_token)

        # Step 1: initiate resumable session
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
            raise RuntimeError("No upload URL returned from YouTube (missing Location header).")

        # Step 2: stream bytes from GCS (download_url) directly into the resumable session
        with requests.get(download_url, stream=True, timeout=60) as source:
            source.raise_for_status()
            # We stream raw bytes to the upload URL
            upload_resp = requests.put(
                upload_url,
                data=source.raw,
                headers={"Content-Type": "video/*"},
                timeout=3600
            )

        if upload_resp.status_code not in (200, 201):
            # YouTube may return detailed error JSON
            raise RuntimeError(f"Upload failed: {upload_resp.status_code} {upload_resp.text}")

        # get video id
        try:
            body = upload_resp.json()
            video_id = body.get("id")
        except Exception:
            video_id = None

        if not video_id:
            # sometimes returned body might be different; try parsing location or other hints
            raise RuntimeError("Upload completed but couldn't parse video ID from response.")

        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        result = {"status": "ok", "youtube_video_id": video_id, "youtube_url": youtube_url}

        # callback if provided
        if callback_url:
            try:
                requests.post(callback_url, json=result, timeout=10)
            except Exception as cb_e:
                # don't fail the request if callback errors; log to stdout
                print("Callback error:", cb_e)

        return jsonify(result)

    except Exception as e:
        err = {"status": "error", "error": str(e)}
        callback_url = data.get("callback_url")
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
    import logging
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
