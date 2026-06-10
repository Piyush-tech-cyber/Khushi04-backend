import os
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "6b7dc4806emsh65c412b8ad1ed5ep18eb8djsn9d9a0d459d2b")
RAPIDAPI_HOST = "instagram-api-media-downloader.p.rapidapi.com"
BASE_URL      = f"https://{RAPIDAPI_HOST}/v1"


def headers():
    return {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
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
    return jsonify({"status": "KhushiSundari backend running ✅"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/debug", methods=["POST"])
def debug():
    """Debug endpoint to see raw API response"""
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()
    shortcode = extract_shortcode(url)
    
    # Try multiple endpoint formats
    endpoints = [
        f"{BASE_URL}/media/{shortcode}",
        f"{BASE_URL}/media/by/shortcode?shortcode={shortcode}",
        f"https://{RAPIDAPI_HOST}/v1/media?shortcode={shortcode}",
    ]
    
    results = {}
    for ep in endpoints:
        try:
            r = requests.get(ep, headers=headers(), timeout=10)
            results[ep] = {"status": r.status_code, "body": r.text[:300]}
        except Exception as e:
            results[ep] = {"error": str(e)}
    
    return jsonify(results)


# ── 1. Post / Reel / Video ─────────────────────
@app.route("/download/post", methods=["POST"])
def download_post():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url:
        return api_error("Instagram URL is required.")

    shortcode = extract_shortcode(url)
    if not shortcode:
        return api_error("Invalid Instagram URL.")

    # Try shortcode endpoint
    try:
        resp = requests.get(
            f"{BASE_URL}/media/by/shortcode",
            params={"shortcode": shortcode},
            headers=headers(),
            timeout=25,
        )
        
        # If 404, try alternate endpoint
        if resp.status_code == 404:
            resp = requests.get(
                f"{BASE_URL}/media/{shortcode}/info",
                headers=headers(),
                timeout=25,
            )
        
        # If still 404, try posts endpoint
        if resp.status_code == 404:
            resp = requests.get(
                f"https://{RAPIDAPI_HOST}/v1/media",
                params={"shortcode": shortcode},
                headers=headers(),
                timeout=25,
            )

    except requests.exceptions.Timeout:
        return api_error("Request timed out. Please try again.", 504)
    except requests.exceptions.RequestException as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code in (401, 403):
        return api_error("API key invalid or expired.", 401)
    if resp.status_code == 429:
        return api_error("Monthly API limit reached.", 429)
    if resp.status_code == 404:
        return api_error("Post not found. Check the link and try again.")
    if resp.status_code != 200:
        return api_error(f"API error (HTTP {resp.status_code}).", resp.status_code)

    try:
        data = resp.json()
    except Exception:
        return api_error("Could not parse API response.", 502)

    media_items = []
    inner = data.get("data") or data.get("media") or data

    # Carousel
    edges = (inner.get("edge_sidecar_to_children") or {}).get("edges", [])
    if edges:
        for edge in edges:
            node = edge.get("node", {})
            u = node.get("video_url") or node.get("display_url", "")
            t = node.get("display_url") or u
            if u:
                media_items.append({
                    "type": "video" if node.get("video_url") else "image",
                    "url": u, "thumbnail": t,
                })
    else:
        video_url   = inner.get("video_url")
        display_url = inner.get("display_url")
        media_url   = inner.get("media_url") or inner.get("url")

        if video_url:
            media_items.append({"type":"video","url":video_url,"thumbnail":display_url or video_url})
        elif display_url:
            media_items.append({"type":"image","url":display_url,"thumbnail":display_url})
        elif media_url:
            media_items.append({
                "type":"video" if media_url.endswith(".mp4") else "image",
                "url":media_url,"thumbnail":inner.get("thumbnail") or media_url
            })

    media_items = [m for m in media_items if m.get("url")]

    if not media_items:
        return api_error("No media found. Post may be private or deleted.")

    return jsonify({"success":True,"shortcode":shortcode,"media":media_items,"count":len(media_items)})


# ── 2. Profile Picture ─────────────────────────
@app.route("/download/profile", methods=["POST"])
def download_profile():
    body = request.get_json(silent=True) or {}
    raw  = (body.get("username") or "").strip()

    if not raw:
        return api_error("Username is required.")

    username = extract_username(raw)
    if not username:
        return api_error("Invalid username.")

    try:
        resp = requests.get(
            f"{BASE_URL}/users/by/username",
            params={"username": username},
            headers=headers(),
            timeout=25,
        )
        if resp.status_code == 404:
            resp = requests.get(
                f"{BASE_URL}/users/{username}",
                headers=headers(),
                timeout=25,
            )
    except requests.exceptions.Timeout:
        return api_error("Request timed out.", 504)
    except requests.exceptions.RequestException as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code in (401, 403):
        return api_error("API key invalid or expired.", 401)
    if resp.status_code == 429:
        return api_error("Monthly API limit reached.", 429)
    if resp.status_code in (404, 400):
        return api_error(f"User '@{username}' not found.")
    if resp.status_code != 200:
        return api_error(f"API error (HTTP {resp.status_code}).", 502)

    try:
        data = resp.json()
    except Exception:
        return api_error("Could not parse response.", 502)

    inner = data.get("data") or data.get("user") or data

    pic_url = (
        inner.get("profile_pic_url_hd")
        or inner.get("hd_profile_pic_url_info", {}).get("url")
        or inner.get("profile_pic_url")
    )

    if not pic_url:
        return api_error("Could not get profile picture.")

    return jsonify({
        "success": True,
        "username": username,
        "full_name": inner.get("full_name") or username,
        "follower_count": inner.get("edge_followed_by", {}).get("count") or inner.get("follower_count"),
        "profile_pic_url": pic_url,
        "is_private": inner.get("is_private", False),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
