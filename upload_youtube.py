import os
import sys
import json
import glob
import argparse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def authenticate():
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    with open("token.json", "w") as f:
        f.write(creds.to_json())
    print("Saved token.json")


def get_credentials():
    token_json = os.environ.get("YT_TOKEN_JSON")
    if token_json:
        try:
            data = json.loads(token_json)
        except json.JSONDecodeError:
            import base64
            data = json.loads(base64.b64decode(token_json))
        creds = Credentials.from_authorized_user_info(data, SCOPES)
    else:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    return creds


def upload(video_path, title, description):
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["shorts", "history", "historyfacts", "didyouknow"],
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public"},
    }
    media = MediaFileUpload(video_path, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print(f"Uploaded! Video ID: {response['id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true")
    args = parser.parse_args()

    if args.auth:
        authenticate()
        sys.exit(0)

    meta_files = sorted(glob.glob("output/meta_*.json"))
   if not meta_files:
       print("No meta file found")
       sys.exit(1)
   for mf in meta_files:
       meta = json.load(open(mf))
       try:
           upload(meta["file"], meta["title"], meta["description"])
       except Exception as e:
           print(f"Upload failed for {mf}: {e}")
