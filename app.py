import os, uuid, shutil, subprocess, re, ipaddress, socket
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
WORK = Path(os.getenv("WORK_DIR", "/tmp/tinkuclip"))
WORK.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(1024 * 1024 * 1024)))
app = FastAPI(title="TinkuClip AI")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-3000:])
    return p.stdout

def has_tool(name):
    return shutil.which(name) is not None

@app.get("/health")
def health():
    return {"ok": True, "ffmpeg": has_tool("ffmpeg"), "ffprobe": has_tool("ffprobe")}

def safe_public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, "Valid public http/https direct video URL dein.")
    host = parsed.hostname
    try:
        addresses = socket.getaddrinfo(host, None)
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                raise HTTPException(400, "Private/local network URLs allowed nahi hain.")
    except socket.gaierror:
        raise HTTPException(400, "URL host resolve nahi hua.")
    # YouTube watch/share pages are not direct media files and are intentionally not downloaded.
    if host.lower().endswith(("youtube.com", "youtu.be", "m.youtube.com")):
        raise HTTPException(400, "YouTube watch link se video download supported nahi hai. Apni video file upload karein ya public direct .mp4 URL dein.")
    return url

async def save_upload(video: UploadFile, target: Path):
    if not video.filename or not video.filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v")):
        raise HTTPException(400, "MP4, MOV, MKV ya WEBM video upload karein.")
    total = 0
    with target.open("wb") as out:
        while chunk := await video.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                raise HTTPException(413, f"Upload limit {MAX_BYTES // (1024*1024)} MB hai.")
            out.write(chunk)

def download_direct(url: str, target: Path):
    safe_public_url(url)
    req = Request(url, headers={"User-Agent": "TinkuClipAI/1.0"})
    total = 0
    try:
        with urlopen(req, timeout=30) as response, target.open("wb") as out:
            ctype = response.headers.get("Content-Type", "").lower()
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise HTTPException(413, "Direct video URL file limit se badi hai.")
            if ctype and not (ctype.startswith("video/") or "octet-stream" in ctype):
                raise HTTPException(400, "URL video file nahi lag raha. Direct MP4/MOV link dein.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(413, "Direct video URL file limit se badi hai.")
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Video URL fetch nahi hua: {e}")

def transcribe(video_path: Path, language: str, job: Path):
    try:
        from faster_whisper import WhisperModel
    except Exception:
        raise RuntimeError("Auto captions ke liye faster-whisper install nahi hua.")
    model_name = os.getenv("WHISPER_MODEL", "tiny")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    lang_code = {"Hindi": "hi", "English": "en", "Auto detect": None}.get(language)
    segments, info = model.transcribe(str(video_path), language=lang_code, vad_filter=True)
    result = []
    for seg in segments:
        result.append((float(seg.start), float(seg.end), seg.text.strip()))
    return result

def srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

@app.post("/api/process")
async def process_video(
    video: UploadFile = File(None),
    video_url: str = Form(""),
    clips: int = Form(5),
    language: str = Form("Hindi"),
    captions: str = Form("on")
):
    if not has_tool("ffmpeg") or not has_tool("ffprobe"):
        raise HTTPException(500, "Server par FFmpeg install nahi hai.")
    if (video is None or not video.filename) and not video_url.strip():
        raise HTTPException(400, "Video upload karein ya direct video URL dein.")
    clips = max(1, min(int(clips), 20))
    job = WORK / uuid.uuid4().hex
    job.mkdir(parents=True)
    source = job / "source.mp4"
    try:
        if video is not None and video.filename:
            await save_upload(video, source)
        else:
            download_direct(video_url.strip(), source)

        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                     "default=noprint_wrappers=1:nokey=1", str(source)])
        duration = float(probe.strip())
        if duration < 8:
            raise HTTPException(400, "Video kam se kam 8 seconds ka hona chahiye.")

        transcript = []
        if captions == "on":
            transcript = transcribe(source, language, job)

        count = min(clips, max(1, int(duration // 15)))
        segment_len = min(60.0, max(15.0, duration / max(count, 1)))
        outputs = []
        for i in range(count):
            start = max(0.0, min(duration - segment_len, i * (duration - segment_len) / max(count - 1, 1)))
            out = job / f"clip_{i+1:02d}.mp4"
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            if captions == "on":
                selected = [(a, b, t) for a, b, t in transcript if b > start and a < start + segment_len and t]
                srt = job / f"clip_{i+1:02d}.srt"
                with srt.open("w", encoding="utf-8") as f:
                    for n, (a, b, t) in enumerate(selected, 1):
                        local_a = max(0, a - start)
                        local_b = min(segment_len, b - start)
                        f.write(f"{n}\n{srt_time(local_a)} --> {srt_time(local_b)}\n{t}\n\n")
                # SRT path is generated from a server-controlled UUID folder.
                subtitle_filter = "subtitles=" + str(srt).replace("\\", "/").replace(":", r"\:")
                vf += "," + subtitle_filter + ":force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=110'"
            run(["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(segment_len),
                 "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
            outputs.append({"name": out.name, "url": f"/api/download/{job.name}/{out.name}",
                             "start_seconds": round(start), "duration_seconds": round(segment_len)})
        msg = "Clips ready. Auto captions burned into video." if captions == "on" else "Clips ready. Captions off."
        return {"job_id": job.name, "clips": outputs, "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Processing error: {str(e)}")

@app.get("/api/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or not re.fullmatch(r"clip_\d{2}\.mp4", filename):
        raise HTTPException(400, "Invalid file path")
    path = WORK / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Clip nahi mila. Server temporary files clean kar sakta hai.")
    return FileResponse(path, media_type="video/mp4", filename=filename)
        
