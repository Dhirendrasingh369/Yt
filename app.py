from flask import Flask, request, jsonify, send_file, render_template, Response
import yt_dlp
import os
import uuid
import json
import threading

app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


def get_video_info(url):
    """Fetch video metadata without downloading."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "view_count": info.get("view_count"),
            "formats": [
                {
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f.get("resolution") or f.get("format_note", "audio only"),
                    "filesize": f.get("filesize"),
                }
                for f in info.get("formats", [])
                if f.get("ext") in ["mp4", "webm", "m4a", "mp3"]
            ],
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/info", methods=["POST"])
def video_info():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        info = get_video_info(url)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()
    url = data.get("url", "").strip()
    fmt = data.get("format", "best[ext=mp4]/best")
    audio_only = data.get("audio_only", False)

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    filename = str(uuid.uuid4())
    ext = "mp3" if audio_only else "mp4"
    filepath = os.path.join(DOWNLOAD_FOLDER, f"{filename}.{ext}")

    if audio_only:
        options = {
            "outtmpl": filepath,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
        }
    else:
        options = {
            "outtmpl": filepath,
            "format": fmt if fmt else "best[ext=mp4]/best",
            "quiet": True,
        }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        # Find the actual downloaded file (yt-dlp may adjust extension)
        actual_file = filepath
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.startswith(filename):
                actual_file = os.path.join(DOWNLOAD_FOLDER, f)
                break

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
        download_name = f"{safe_title}.{ext}"

        def generate():
            with open(actual_file, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk
            os.remove(actual_file)

        return Response(
            generate(),
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"'
            },
        )
    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
