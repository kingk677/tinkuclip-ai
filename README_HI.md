# TinkuClip AI — starter project

## Is build mein kya kaam karta hai?
- Phone/browser se video upload
- FFmpeg se requested count ke vertical 9:16 MP4 segments
- Har generated clip ka download link

## Abhi kya nahi bana hai?
- YouTube URL se video download (YouTube Data API direct downloadable video file nahi deti; unauthorized downloading avoid karein)
- AI se semantic/viral moment ranking
- Hindi/English speech-to-text aur burned-in captions
- Unlimited duration / unlimited free processing

Current clip selection evenly spaced segments hai, AI highlight detection nahi. Yeh limitation jaan-boojhkar clear rakhi gayi hai.

## Local run
1. Python 3.11+ aur FFmpeg install karein.
2. `pip install -r requirements.txt`
3. `uvicorn app:app --host 0.0.0.0 --port 8000`
4. Browser mein `http://localhost:8000` kholein.

## Deploy
Docker support wale host par is folder/repository ko deploy karein. Start command Dockerfile se mil jayega. Public deploy se pehle:
- Authentication / per-user quotas lagayein
- Upload size, processing time aur storage limits set karein
- Temporary files ki scheduled cleanup add karein
- HTTPS aur private storage use karein

Free hosting plans aksar long-running jobs, RAM, disk aur execution time limit karte hain. Isliye 1–3 hour videos ya unlimited free processing ki guarantee nahi.

## Important
Sirf wahi videos upload/process karein jinhe use karne ka adhikar aapke paas hai.
