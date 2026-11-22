import os, uuid, shutil, subprocess, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
WORK = Path(os.getenv("WORK_DIR", "/tmp/tinkuclip"))
WORK.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="TinkuClip AI")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2500:])
    return p.stdout

def has_tool(name):
    return shutil.which(name) is not None

@app.get("/health")
def health():
    return {"ok": True, "ffmpeg": has_tool("ffmpeg")}

@app.post("/api/process")
async def process_video(video: UploadFile = File(...), clips: int = Form(5), language: str = Form("Hindi")):
    if not has_tool("ffmpeg") or not has_tool("ffprobe"):
        raise HTTPException(500, "Server par FFmpeg install nahi hai.")
    if not video.filename or not video.filename.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v")):
        raise HTTPException(400, "MP4, MOV, MKV ya WEBM video upload karein.")
    clips = max(1, min(int(clips), 20))
    job = WORK / uuid.uuid4().hex
    job.mkdir(parents=True)
    source = job / "source" + Path(video.filename).suffix if False else job / ("source" + Path(video.filename).suffix)
    size = 0
    with source.open("wb") as out:
        while chunk := await video.read(1024 * 1024):
            size += len(chunk)
            if size > 1024 * 1024 * 1024:
                raise HTTPException(413, "Upload limit 1 GB hai. Chhota video try karein.")
            out.write(chunk)
    try:
        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(source)])
        duration = float(probe.strip())
        if duration < 8:
            raise HTTPException(400, "Video kam se kam 8 seconds ka hona chahiye.")
        # Divide the full video into evenly spaced candidate sections.
        # A later transcript/semantic ranking service can replace this baseline.
        count = min(clips, max(1, int(duration // 15)))
        segment_len = min(45.0, max(15.0, duration / max(count, 1)))
        outputs = []
        for i in range(count):
            start = max(0.0, min(duration - segment_len, i * (duration - segment_len) / max(count - 1, 1)))
            out = job / f"clip_{i+1:02d}.mp4"
            # Center-crop to vertical 9:16 and burn a simple, editable title slate.
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            run(["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(segment_len),
                 "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
            outputs.append({"name": out.name, "url": f"/api/download/{job.name}/{out.name}", "start_seconds": round(start), "duration_seconds": round(segment_len)})
        return {"job_id": job.name, "clips": outputs,
                "message": "Basic clip generation complete. Smart AI moment detection and automatic captions are not enabled in this starter build."}
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
