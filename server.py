import os
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "YAHAN_APNI_PURI_NAYI_API_KEY_PASTE_KAREIN") 
RAPIDAPI_HOST = "instagram-cheapest.p.rapidapi.com"

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "KhushiSundari Premium Backend Live ✅ (Updated API)"})

@app.route("/download/post", methods=["POST"])
def download_post():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url: 
        return jsonify({"success": False, "error": "Instagram URL is required."}), 400

    match = re.search(r'(?:p|reel|tv)/([^/?#&]+)', url)
    if not match:
        return jsonify({"success": False, "error": "Invalid Instagram URL format."}), 400
        
    shortcode = match.group(1)

    target_url = f"https://{RAPIDAPI_HOST}/api/v1/instagram/media_by_code2"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    params = {"code": shortcode}

    try:
        resp = requests.get(target_url, headers=headers, params=params, timeout=25)
        
        if resp.status_code in (401, 403):
            return jsonify({"success": False, "error": "API key invalid, expired, or not subscribed."}), 403
            
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"Server returned error code {resp.status_code}"}), resp.status_code

        return jsonify({"success": True, "data": resp.json()})

    except Exception as e:
        return jsonify({"success": False, "error": f"Server connection error: {str(e)}"}), 502
