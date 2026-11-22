TinkuClip AI – Updated starter
Features
Video file upload
Public direct video-file URL input (MP4/MOV etc.)
9:16 vertical clips
Optional Hindi/English/auto-detect speech captions using faster-whisper
MP4 clip downloads
Important limitations
YouTube watch/share URLs are not downloaded. Use your own video file or a public direct video-file URL. Only process videos you own or have permission to use.
Clips are selected at evenly spaced intervals. AI viral-moment/highlight ranking is not included.
No service can honestly promise free unlimited hosting/processing. Hosting, storage, bandwidth, CPU/RAM and provider limits apply.
First caption request downloads the Whisper tiny model and can take time. Larger/longer videos may exceed free-host resource limits.
Deploy
Use a Docker-capable host. Set the start command from Dockerfile or build from this folder. Health check: /health
