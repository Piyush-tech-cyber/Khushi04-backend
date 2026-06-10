import os
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "YOUR_RAPIDAPI_KEY_HERE")
RAPIDAPI_HOST = "instagram120.p.rapidapi.com"
BASE_URL      = f"https://{RAPIDAPI_HOST}"

def headers():
    return {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
        "Content-Type":    "application/json",
    }

def extract_shortcode(url):
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None

def extract_username(raw):
    raw = raw.strip().lstrip("@").strip("/")
    if "instagram.com" in raw:
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)/?$", raw)
        return m.group(1) if m else None
    if re.match(r"^[A-Za-z0-9_.]{1,30}$", raw):
        return raw
    return None

def api_error(msg, code=400):
    return jsonify({"success": False, "error": msg}), code

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Backend running ✅"})

@app.route("/download/post", methods=["POST"])
def download_post():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url: return api_error("Instagram URL is required.")
    shortcode = extract_shortcode(url)
    if not shortcode: return api_error("Invalid Instagram URL.")

    try:
        resp = requests.post(f"{BASE_URL}/mediaByShortcode", json={"shortcode": shortcode}, headers=headers(), timeout=25)
    except Exception as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code == 401: return api_error("API key invalid. Check Render Env Variables.", 401)
    if resp.status_code != 200: return api_error(f"API error.", resp.status_code)

    data = resp.json()
    media_items = []
    inner = data.get("data") or data.get("media") or data

    edges = (inner.get("edge_sidecar_to_children") or {}).get("edges", [])
    if edges:
        for edge in edges:
            node = edge.get("node", {})
            u = node.get("video_url") or node.get("display_url", "")
            t = node.get("display_url") or u
            if u: media_items.append({"type": "video" if node.get("video_url") else "image", "url": u, "thumbnail": t})
    else:
        video_url = inner.get("video_url")
        display_url = inner.get("display_url")
        if video_url: media_items.append({"type":"video","url":video_url,"thumbnail":display_url or video_url})
        elif display_url: media_items.append({"type":"image","url":display_url,"thumbnail":display_url})

    if not media_items: return api_error("No media found.")
    return jsonify({"success":True,"shortcode":shortcode,"media":media_items,"count":len(media_items)})

@app.route("/download/profile", methods=["POST"])
def download_profile():
    body = request.get_json(silent=True) or {}
    raw  = (body.get("username") or "").strip()

    if not raw: return api_error("Username is required.")
    username = extract_username(raw)
    
    try:
        resp = requests.post(f"{BASE_URL}/userInfo", json={"username": username}, headers=headers(), timeout=25)
    except Exception as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code == 404: return api_error("User not found.")
    if resp.status_code != 200: return api_error("API error.", 502)

    data = resp.json()
    inner = data.get("data") or data.get("user") or data
    pic_url = inner.get("profile_pic_url_hd") or inner.get("profile_pic_url")

    if not pic_url: return api_error("Could not get profile picture.")
    return jsonify({"success": True, "username": username, "full_name": inner.get("full_name"), "profile_pic_url": pic_url})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
