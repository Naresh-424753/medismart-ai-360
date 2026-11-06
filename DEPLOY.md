# Free deployment guide

Three free pieces: **MongoDB Atlas** (database), **Render** (backend API) and **Vercel / Netlify / Cloudflare Pages** (frontend). Nothing secret goes in the code or in git: passwords live only in each host's "Environment variables" screen.

## 1. Database: MongoDB Atlas (free M0)
1. mongodb.com/atlas -> create a free **M0** cluster.
2. Database Access -> add a user with a strong password.
3. Network Access -> add `0.0.0.0/0` (Render's free IPs change; the password protects it).
4. Connect -> Drivers -> copy the `mongodb+srv://USER:PASSWORD@cluster.../` string. This is `MONGO_URL`.

## 2. Backend: Render (free web service)
1. Push this folder to a GitHub repo (`backend/.env` is git-ignored, do not force-add it).
2. render.com -> New -> **Blueprint** -> pick the repo (it reads `render.yaml`). Or New -> Web Service -> Docker, root directory `backend`.
3. Fill the variables Render asks for:

| Variable | Value |
|---|---|
| `MONGO_URL` | the Atlas string from step 1 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | the first admin (password 12+ chars). Created on first start |
| `DATA_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`. Keep a copy: without it uploaded documents cannot be decrypted |
| `CORS_ORIGINS` | your frontend URL from step 3 (you can add it after the first deploy) |
| `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Gmail address and a Gmail **App Password**. Needed: with `DEV_MODE=0` OTP is email only |
| `GCS_BUCKET` + `GOOGLE_APPLICATION_CREDENTIALS` | optional, see README "Google Cloud storage". Without it uploaded files are lost whenever the free service restarts |

4. Deploy. When it is live, `https://<name>.onrender.com/health` must return `{"status":"ok"}`.

## 3. Frontend: Vercel (or Netlify / Cloudflare Pages)
1. Import the same repo, **root directory `frontend`**, framework Vite (build `npm run build`, output `dist`).
2. Environment variable: `VITE_API_URL=https://<name>.onrender.com`.
3. Deploy, then put the resulting URL into the backend's `CORS_ORIGINS` and redeploy the backend.
4. `vercel.json` / `public/_redirects` already make page refreshes work.

## 4. Check
Open the frontend URL -> log in as the admin -> register a test patient (the OTP arrives by email) -> Contact page.

## Limits of the free tier (be upfront in a demo)
- **Render free sleeps after ~15 min idle**; the first request then takes ~30-60 s. Open the site a minute before presenting. A free uptime pinger on `/health` avoids this.
- **512 MB RAM** on Render free is tight for scikit-learn + OpenCV. If the service is killed for memory, use Hugging Face Spaces (Docker Space, more RAM, free) for the backend with the same `backend/Dockerfile` and the same variables (the app listens on `$PORT`, set `app_port` accordingly).
- **Atlas M0 is 512 MB.** Fine for a demo, not for production.
- The free disk is **not persistent**: use `GCS_BUCKET` for documents and never rely on local files.
- Video calls use browser WebRTC with a public STUN server. Calls between different networks may fail without a TURN server (`TURN_URL`, `TURN_USERNAME`, `TURN_CREDENTIAL`).
- Camera/microphone/voice need HTTPS, which all these hosts provide.
- Not for real patients: this is demo software, not a certified medical device, and has not had a security audit.
