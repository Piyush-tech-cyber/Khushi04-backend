import os
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
#  Apyflux Credentials
#  Set these as Environment Variables on Render:
#  APYFLUX_CLIENT_ID  → your Client ID
#  APYFLUX_API_KEY    → your API Key
# ─────────────────────────────────────────────
APYFLUX_CLIENT_ID = os.environ.get("APYFLUX_CLIENT_ID", "")
APYFLUX_API_KEY   = os.environ.get("APYFLUX_API_KEY", "")

APYFLUX_BASE = "https://api.apyflux.com"


# ── Helpers ──────────────────────────────────

def apyflux_headers():
    return {
        "x-apyflux-client-id": APYFLUX_CLIENT_ID,
        "x-apyflux-api-key":   APYFLUX_API_KEY,
        "Content-Type":        "application/json",
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


def no_key_error():
    return jsonify({
        "success": False,
        "error": "Apyflux credentials not configured. Please set APYFLUX_CLIENT_ID and APYFLUX_API_KEY on Render."
    }), 500


def api_error(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


def parse_apyflux_media(data):
    """
    Apyflux /instagram/ endpoint returns JSON.
    Handle all known response shapes and return
    a normalised list of {type, url, thumbnail} dicts.
    """
    media_items = []

    if not isinstance(data, dict):
        return media_items

    # Shape 1: { "data": { "video_url": "...", "display_url": "..." } }
    inner = data.get("data") or data

    # Shape 2: top-level or inner "items" / "media" list (carousel)
    for key in ("items", "media", "carousel_media"):
        if isinstance(inner.get(key), list):
            for item in inner[key]:
                u = (item.get("video_url") or item.get("url") or
                     item.get("display_url") or "")
                t = item.get("display_url") or item.get("thumbnail") or u
                if u:
                    media_items.append({
                        "type": "video" if item.get("video_url") or u.endswith(".mp4") else "image",
                        "url": u,
                        "thumbnail": t,
                    })
            if media_items:
                return media_items

    # Shape 3: single item at top / inner level
    video_url   = inner.get("video_url") or data.get("video_url")
    display_url = inner.get("display_url") or data.get("display_url")
    direct_url  = inner.get("url") or data.get("url")

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
    elif direct_url:
        media_items.append({
            "type": "video" if direct_url.endswith(".mp4") else "image",
            "url": direct_url,
            "thumbnail": inner.get("thumbnail") or data.get("thumbnail") or direct_url,
        })

    return [m for m in media_items if m.get("url")]


# ── Routes ───────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Khushiverse backend is running ✅"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "apyflux_configured": bool(APYFLUX_CLIENT_ID and APYFLUX_API_KEY),
    })


# ── 1. Download Reel / Photo / Video ─────────

@app.route("/download/post", methods=["POST"])
def download_post():
    """
    Works for Reels, photos, carousels, video posts.
    Body JSON: { "url": "https://www.instagram.com/p/..." }
    """
    if not (APYFLUX_CLIENT_ID and APYFLUX_API_KEY):
        return no_key_error()

    body = request.get_json(silent=True) or {}
    url  = (body.get("url") or "").strip()

    if not url:
        return api_error("Instagram URL is required.")

    shortcode = extract_shortcode(url)
    if not shortcode:
        return api_error(
            "Invalid Instagram URL. Example: https://www.instagram.com/p/ABC123/ "
            "or https://www.instagram.com/reel/ABC123/"
        )

    try:
        resp = requests.get(
            f"{APYFLUX_BASE}/instagram/",
            params={"url": url},
            headers=apyflux_headers(),
            timeout=25,
        )
    except requests.exceptions.Timeout:
        return api_error("Request timed out. Please try again.", 504)
    except requests.exceptions.RequestException as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code in (401, 403):
        return api_error(
            "Apyflux credentials are invalid or expired. "
            "Please check APYFLUX_CLIENT_ID and APYFLUX_API_KEY on Render.", 401
        )
    if resp.status_code == 429:
        return api_error("API request limit reached. Please wait and try again.", 429)
    if resp.status_code != 200:
        return api_error(
            f"Downloader API error (HTTP {resp.status_code}). Try again later.",
            resp.status_code
        )

    try:
        data = resp.json()
    except Exception:
        return api_error("Could not parse API response. Try again.", 502)

    media_items = parse_apyflux_media(data)

    if not media_items:
        return api_error(
            "No downloadable media found. "
            "The post may be private, deleted, or age-restricted."
        )

    return jsonify({
        "success": True,
        "shortcode": shortcode,
        "media": media_items,
        "count": len(media_items),
    })


# ── 2. Profile Picture ────────────────────────

@app.route("/download/profile", methods=["POST"])
def download_profile():
    """
    Body JSON: { "username": "natgeo" }
    Uses same Apyflux /instagram/ endpoint with profile URL.
    """
    if not (APYFLUX_CLIENT_ID and APYFLUX_API_KEY):
        return no_key_error()

    body = request.get_json(silent=True) or {}
    raw  = (body.get("username") or "").strip()

    if not raw:
        return api_error("Username is required.")

    username = extract_username(raw)
    if not username:
        return api_error(
            "Invalid username. Only letters, numbers, dots, and underscores allowed."
        )

    profile_url = f"https://www.instagram.com/{username}/"

    try:
        resp = requests.get(
            f"{APYFLUX_BASE}/instagram/",
            params={"url": profile_url},
            headers=apyflux_headers(),
            timeout=25,
        )
    except requests.exceptions.Timeout:
        return api_error("Request timed out. Please try again.", 504)
    except requests.exceptions.RequestException as e:
        return api_error(f"Network error: {str(e)}", 502)

    if resp.status_code in (401, 403):
        return api_error("Apyflux credentials are invalid or expired.", 401)
    if resp.status_code == 429:
        return api_error("API request limit reached. Please wait and try again.", 429)
    if resp.status_code == 404:
        return api_error(f"Instagram user '@{username}' not found.")
    if resp.status_code != 200:
        return api_error(
            f"Profile API error (HTTP {resp.status_code}). Try again later.", 502
        )

    try:
        data = resp.json()
    except Exception:
        return api_error("Could not parse profile data.", 502)

    inner = data.get("data") or data

    pic_url = (
        inner.get("profile_pic_url_hd")
        or inner.get("hd_profile_pic_url_info", {}).get("url")
        or inner.get("profile_pic_url")
        or data.get("profile_pic_url_hd")
        or data.get("profile_pic_url")
    )

    if not pic_url:
        return api_error(
            "Could not retrieve profile picture. "
            "The account may be private or the username is incorrect."
        )

    full_name = (
        inner.get("full_name") or data.get("full_name") or username
    )
    follower_count = (
        inner.get("edge_followed_by", {}).get("count")
        or inner.get("follower_count")
        or inner.get("followers")
        or data.get("follower_count")
    )

    return jsonify({
        "success": True,
        "username": username,
        "full_name": full_name,
        "follower_count": follower_count,
        "profile_pic_url": pic_url,
        "is_private": inner.get("is_private", False),
    })


# ── Run ──────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
