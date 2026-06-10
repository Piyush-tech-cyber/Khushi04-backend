import os
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
#  RapidAPI Credentials
#  instagram120.p.rapidapi.com
# ─────────────────────────────────────────────
RAPIDAPI_KEY  = os.environ.get("RAPIDAPI_KEY", "6b7dc4806emsh65c412b8ad1ed5ep18eb8djsn9d9a0d459d2b")
RAPIDAPI_HOST = "instagram120.p.rapidapi.com"
BASE_URL      = f"https://{RAPIDAPI_HOST}"


def headers():
    return {
        "x-rapidapi-key":  RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
        "Content-Type":    "application/json",
    }


def extract_shortcode(url: str):
    m = re.search(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def extract_username(raw: str):
    raw = raw.strip().lstrip("@").strip("/")
    if "instagram.com" in raw:
        m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)/?$", raw)
        return m.group(1) if m else None
    if re.match(r"^[A-Za-z0-9_.]{1,30}$", raw):
        return raw
    return None


def api_error(msg, code=400):
    return jsonify({"success": False, "error": msg}), code


# ── Health ────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Khushiverse backend running ✅"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ── 1. Post / Reel / Video ────────────────────

@app.route("/download/post", methods=["POST"])
def download_post():
    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url:
        return api_error("Instagram URL is required.")

    shortcode = extract_shortcode(url)
    if not shortcode:
        return api_error("Invalid Instagram URL. Example: https://www.instagram.com/p/ABC123/")

    try:
        # instagram120 uses POST /posts with JSON body
        resp = requests.post(
            f"{BASE_URL}/posts",
            json={"url": url},
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
        return api_error("Monthly API limit reached. Please try again next month.", 429)
    if resp.status_code != 200:
        return api_error(f"API error (HTTP {resp.status_code}). Try again later.", resp.status_code)

    try:
        data = resp.json()
    except Exception:
        return api_error("Could not parse API response.", 502)

    media_items = []

    # instagram120 /posts response shape:
    # { "data": { "video_url": "...", "display_url": "...", "edge_sidecar_to_children": { "edges": [...] } } }
    inner = data.get("data") or data

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
                    "url": u,
                    "thumbnail": t,
                })
    else:
        # Single item
        video_url   = inner.get("video_url")
        display_url = inner.get("display_url")
        if video_url:
            media_items.append({
                "type": "video",
                "url": video_url,
                "thumbnail": display_url or video_url,
            })
        elif display_url:
            media_items.append({
                "type": "image",
                "url": display_url,
                "thumbnail": display_url,
            })

    media_items = [m for m in media_items if m.get("url")]

    if not media_items:
        return api_error("No media found. Post may be private or deleted.")

    return jsonify({
        "success": True,
        "shortcode": shortcode,
        "media": media_items,
        "count": len(media_items),
    })


# ── 2. Profile Picture ────────────────────────

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
        # instagram120 uses POST /userInfo
        resp = requests.post(
            f"{BASE_URL}/userInfo",
            json={"username": username},
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
    if resp.status_code == 404:
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
        return api_error("Could not get profile picture. Account may be private.")

    return jsonify({
        "success": True,
        "username": username,
        "full_name": inner.get("full_name") or username,
        "follower_count": (
            inner.get("edge_followed_by", {}).get("count")
            or inner.get("follower_count")
        ),
        "profile_pic_url": pic_url,
        "is_private": inner.get("is_private", False),
    })


# ── Run ──────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
