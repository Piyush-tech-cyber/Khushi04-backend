import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "6b7dc4806emsh65c412b8ad1ed5ep18eb8djsn9d9a0d459d2b")
RAPIDAPI_HOST = "instagram-downloader-download-instagram-stories-videos4.p.rapidapi.com"

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "KhushiSundari Premium Backend Live ✅"})

@app.route("/download/post", methods=["POST"])
def download_post():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url: 
        return jsonify({"success": False, "error": "Instagram URL is required."}), 400

    target_url = f"https://{RAPIDAPI_HOST}/convert"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    params = {"url": url}

    try:
        resp = requests.get(target_url, headers=headers, params=params, timeout=25)
        
        if resp.status_code in (401, 403):
            return jsonify({"success": False, "error": "API key invalid or expired."}), 403
            
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"Server returned error code {resp.status_code}"}), resp.status_code

        return jsonify({"success": True, "data": resp.json()})

    except Exception as e:
        return jsonify({"success": False, "error": f"Server connection error: {str(e)}"}), 502
        
