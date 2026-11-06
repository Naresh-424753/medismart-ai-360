# MediSmart AI 360
*Diagnose Early · Treat Precisely · Heal Faster*

Full-stack smart healthcare platform: **FastAPI + MongoDB** backend, **React + Tailwind + Recharts** frontend, scikit-learn risk models, OpenCV image screening, Tesseract OCR report reader, rule-based multilingual (English/Hindi) assistant with optional LLM, ESP32 vitals ingestion and WebSocket live updates.

## Quick start (no database needed)
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # edit it: backend/.env is read automatically at start
python -m ml.train                                     # optional: retrain demo risk models
uvicorn app.main:app --reload --port 8000              # API docs: http://localhost:8000/docs

# Frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                                            # http://localhost:5173
```
**Using MongoDB (recommended for anything beyond a demo)**
1. Install MongoDB 6/7 (or use a free MongoDB Atlas cluster) and create a database user.
2. In `backend/.env` set `MONGO_URL=mongodb://USER:PASSWORD@localhost:27017/?authSource=admin` (Atlas: the `mongodb+srv://...` string it gives you; URL-encode special characters in the password) and `DB_NAME=medismart`.
3. Start the backend. It checks the connection first and stops with a clear message if MongoDB is unreachable, then creates its indexes and the first administrator.
Or run everything with Docker: copy `.env.example` to `.env`, set `MONGO_USER` / `MONGO_PASSWORD`, copy `backend/.env.example` to `backend/.env` (JWT_SECRET, ADMIN_EMAIL...), then `docker compose up --build` (frontend :5173, API :8000; MongoDB is not exposed outside Docker). Data lives in the `mongo_data` volume; back it up with `mongodump`.
With `MONGO_URL=mock` the app uses an in-memory database and everything is lost on restart (demo/tests only). I could not run a real MongoDB server in the build sandbox: the code is exercised against an in-memory stand-in, so run the app once against your MongoDB and report any error.
For image OCR install the Tesseract system package (`apt install tesseract-ocr`); PDFs work without it.

## Windows quick run (included `.env`)

1. Double-click `start-mongo.bat` and keep the window open (edit the paths inside if your MongoDB is elsewhere).
2. Double-click `start-backend.bat` (API on :8000). On first start it creates the administrator from `backend/.env`.
3. Double-click `start-frontend.bat`, open the printed URL and log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`.

`backend/.env` is the only place credentials live (never in code) and is git-ignored. **Do not share the zip with this file inside.** Change the password before any real use.
`MONGO_FALLBACK=1` lets the backend start on a temporary in-memory database if MongoDB is unreachable; a loud log banner says so and all data is lost on restart. Set it to `0` for real deployments.

## Google Cloud storage (optional)

- **Database:** create a free MongoDB Atlas cluster on Google Cloud, add your IP under Network Access, and put its `mongodb+srv://...` string in `MONGO_URL` in `backend/.env`. No code change.
- **Uploaded files:** create a private Cloud Storage bucket, set `GCS_BUCKET=<name>` and `GOOGLE_APPLICATION_CREDENTIALS=<service-account.json>` (role: Storage Object Admin on that bucket only), then `pip install -r requirements.txt`. Files are encrypted before upload, so the bucket only holds ciphertext. Leave `GCS_BUCKET` empty to keep files on local disk.
- Never commit the service-account JSON or the Atlas password.

## Files merged from the "MongoDB-Final" zip

`database/init_mongo.js` (optional, regenerated from the backend's index list), `run_with_mongodb.bat/.sh` (now call the start scripts) and `frontend/.env` (`VITE_API_URL`). Their hardcoded admin password and JWT secret were NOT kept: credentials live only in `backend/.env`.

## OTP verification

OTP is required at account creation (`/auth/register` then `/auth/verify-otp`), for forgot/reset password, optionally at login (two-factor), and now for **changing your password while logged in**: `POST /auth/change-password/request` (checks the old password, sends an OTP) then `POST /auth/change-password` with the `otp`. OTPs are hashed, expire in 10 minutes, allow 5 attempts and are single-use. OTPs are sent by **email only** (SMTP_HOST/SMTP_USER/SMTP_PASS in `backend/.env`, e.g. Gmail with an app password) and are never stored as in-app notifications. The OTP is **never returned to the browser**. With `DEV_MODE=1` and no SMTP it is printed in the backend console only (for local testing); with `DEV_MODE=0` and no SMTP, OTP requests fail with a clear error.

## Contact page and account deletion

- **Contact:** public page at `/contact` (a "Need help? Contact us" button is on every page). Messages are stored, admins are notified and see them in the Admin console under *Contact messages* (Reply by email, Mark resolved). Optional `SUPPORT_EMAIL` / `SUPPORT_PHONE` in `backend/.env` are shown on the page; set `SUPPORT_WHATSAPP` (country code + number, digits only) to add a **Chat on WhatsApp** button that opens WhatsApp with the typed message pre-filled. Limited to 5 messages / 5 min per IP.
- **Delete accounts:** Admin console -> Users -> *Delete*. Admins can delete any non-admin account; only the super admin can delete admins; the super admin account itself and your own account cannot be deleted. Deleting removes the profile, vitals, medicines, orders, documents (including files in the bucket), reports and consents. The tamper-evident ledger and the audit log are kept on purpose. A doctor's future appointments are cancelled.

## Deploy for free

See **DEPLOY.md** (MongoDB Atlas + Render + Vercel/Netlify, with `render.yaml`, `vercel.json` and SPA redirects included).

## Architecture
Layered diagram: `docs/architecture-layers.html` (open in a browser); earlier block diagram: `docs/architecture.svg`.

## First-run administrator and credentials
No e-mail address or password is written in the code. On the first start the backend creates one super-admin from `ADMIN_EMAIL` (and `ADMIN_PASSWORD` if you set it) in `backend/.env`; if the password is empty a random one-time password is printed once in the server log. Only a **salted scrypt hash** is stored in MongoDB. You can also run `python create_admin.py` (hidden password prompt; use it with a real MongoDB, not the in-memory mock). `JWT_SECRET` is also never in code: with `DEV_MODE=1` a development secret is generated into `backend/data/.dev_secret`; with `DEV_MODE=0` the server refuses to start without it. `.env` and `data/` are git-ignored.

## UI
The app shell (navy sidebar, top bar with page search, language picker and notification bell) and the patient dashboard follow the supplied dashboard design. Brand colour is blue (`tailwind.config.js`). The dashboard shows only live data: the Health Score is a simple non-clinical figure computed from your own alerts, risk checks, missed doses and latest vitals (hover text explains it), and the "% from last month" deltas in the mockup are not shown because they would be invented.

## Demo logins (seeded when `SEED_DEMO=1`)
Set `DEMO_EMAIL_DOMAIN` in `backend/.env`. Accounts are `patient@<domain>`, `doctor1..6@<domain>`, `pharmacist@<domain>` (pharmacist is linked to HealthPlus Pharmacy, Delhi, with priced stock), plus your admin. The shared demo password is `DEMO_PASSWORD`, or a random one printed once in the server log if you leave it empty.

Other roles (hospital, lab technician, pharmacist, blood bank, ambulance, family member) register from the signup page; OTPs are shown on screen while `DEV_MODE=1`. Doctors/hospitals/labs/pharmacies need admin approval (Admin dashboard -> Verification).

## Modules
Patient management and Digital Health ID with QR and **downloadable offline emergency card** · AI symptom checker and **9 disease-risk models** (diabetes, heart, kidney, liver, stroke, **blood pressure, thyroid, anemia, cancer-lifestyle**) + multi-disease score, digital twin, second opinion · report analyzer (CBC, LFT, KFT, lipid, thyroid, sugar, urine, vitamins; PDF/image OCR, abnormal highlighting, trends) · **ECG / X-ray / MRI / CT report explainer** · **medical-image AI page** (chest X-ray, brain MRI, skin, retina, cataract, segmentation, auto-generated report; fracture/tumor/pneumonia classification when trained ONNX models are added) · bilingual assistant with voice · medicines (prescriptions, reminders, interactions, allergy alerts, stock, expiry, refill, pharmacy finder, ordering, QR verification) · IoT vitals (ESP32, WebSocket, alerts, fall detection) · emergency SOS with GPS, nearby hospitals, ambulance tracking, accident report, public emergency card, **voice emergency assistant** · doctor portal with appointments, video links, notes, follow-ups, analytics and **doctor-patient messaging** · hospital portal with beds, admissions, billing, queue tokens plus **departments, staff, operation-theatre scheduling, inventory, equipment and admission/bed forecast** · lab and blood-bank portals · nutrition/fitness · mental wellness with **meditation library, sleep-schedule planner and counselor booking** · predictive analytics · **public health kiosk (/kiosk)** · notifications (email/SMS/WhatsApp when configured) · admin/security (RBAC, JWT, 2FA, audit logs, login history, encrypted documents).

## Advanced features
* **Multilingual voice** (en, hi, bn, ta, te, mr, gu, kn, ml, pa): browser speech recognition + speech synthesis in the chat, a floating voice navigator (`VoiceCommander`) and the voice SOS. Quality depends on the browser/OS voices installed (`hasVoiceFor` warns if missing). Emergency words are detected in every language.
* **Record security ledger** (`/security`): per-patient hash-chained, Merkle-anchored ledger of document fingerprints, consent grants/revokes, prescriptions and every third-party access. Verify chain and each document's integrity; revoke access.
* **Video/audio consultation** (`/call/:aid`): WebRTC peer-to-peer with FastAPI WebSocket signaling, restricted to the two appointment parties, in-call chat, audio-only mode.
* **Wearables** (`/wearables`): Health Connect / HealthKit phone-bridge ingest (`POST /wearables/ingest`, device key) and Apple Health `export.zip` import; heart rate, SpO2, steps, sleep charts; recent readings feed the vitals alert engine.
* **Prescription scanner** (`/rx-scan`, `/rx-verify`): OpenCV + Tesseract OCR, drug-database matching, editable table. Reminders are created only after a doctor or pharmacist verifies; editing a verified scan resets verification.

New env vars: `STUN_URLS`, `TURN_URL`, `TURN_USERNAME`, `TURN_CREDENTIAL`, `TELE_ANYTIME` (1 = allow calls any time, for demos). OCR needs the `tesseract-ocr` system package (`apt install tesseract-ocr tesseract-ocr-hin`).

### Limits of the advanced features
* The ledger is **tamper-evident, not a public/decentralized blockchain**: the server operator could rewrite the whole chain unless you publish the anchor (`/ledger/admin/anchor`) somewhere external.
* WebRTC needs a **TURN server** for strict NATs/mobile networks; Agora was not built.
* **Fitbit's Web API shut down on 30 Oct 2026 and Google Fit is retired**, so there is no direct Fitbit/Google Fit connector; Google Health API is not connected. Use the phone bridge or Apple export.
* Regional-language **chat answers need `LLM_API_KEY`**; the rule-based bot covers English/Hindi only (others get a translated emergency message or an English notice). Translated strings in `services/languages.py` need native-speaker review.
* **OCR is unreliable on handwriting**; every item is human-verified before it becomes a reminder.

## Clinical AI additions
* **Early Warning System** (`/early-warning`, `services/ews.py`): runs after every stored vitals reading, including wearable ingests. It computes **NEWS2** (published bedside score), projects each vital 2-4 hours ahead with a damped trend and re-scores it, and runs a per-patient IsolationForest on the patient's own history. Alerts go to the patient (SMS on critical) and, **only if the patient opts in**, to doctors with a current appointment and to the hospital where the patient is admitted. The 2-4 h part is a trend projection, **not a model trained on ICU outcomes or clinically validated**. SMS needs Twilio keys; there is no browser/mobile push service (in-app notifications only). Demo data: `POST /ews/demo/deteriorating`.
* **Regional voice** (`services/stt.py`, `/voice/transcribe`): browser recorder produces 16 kHz WAV, server calls **Whisper** (`WHISPER_API_KEY`) or **Bhashini** (`BHASHINI_USER_ID`, `BHASHINI_API_KEY`) for en/hi/bn/ta/te/mr/gu/kn/ml/pa; used by the voice commander and the voice symptom checker. Neither provider was called from the build sandbox, so test with your own keys. Audio is not stored.
* **Prescription -> pharmacy**: new prescriptions notify the patient with an Order Medicines prompt; `RxOrder` ranks pharmacies by live stock, price and city, blocks out-of-stock items, reserves/restores stock, and the pharmacy rider's position feeds a live tracking view with a rough straight-line ETA. Needs pharmacists who have set up a profile and stock list.
* **Federated learning** (`/federated`, `services/federated.py`, `ml/federated_client.py`): FedAvg over hospitals with per-update clipping and optional noise. Hospitals train on their own CSV and upload only weight updates. **No secure aggregation and no formal differential-privacy guarantee**; models are the synthetic-data demo logistic regressions and are not yet used by the live risk pages. The simulation shows convergence versus local-only and centralised training; on this simple synthetic data a single hospital alone does nearly as well.
* **Second opinion & medical board** (`/second-opinion`, `routers/board.py`): complex cases (>=2 high risks, critical lab values, a rare-condition keyword, critical vitals with high risk) open an AI review automatically, at most one per week. Three independent *methods* run: ML risk models, a rule engine over labs/vitals/symptoms, and an LLM if `LLM_API_KEY` is set (otherwise the report says only 2 of 3 ran). Specialists receive the case **only after the patient consents**, and only as an anonymised packet. Doctors submit verdicts; the report (ranked tests, vote tally, dissent, SHA-256 fingerprint also written to the patient's ledger) is generated when all respond or the patient closes it after two. Rare-disease detection is a short keyword list, not exhaustive. Everything is decision support for a clinician, not a diagnosis.

## Medicine order, UPI payment and delivery
Patient orders medicines -> price comes from the pharmacy's stock list (or the pharmacist sets it) -> **UPI QR** (standard `upi://pay` link, scan with GPay/PhonePe/Paytm/BHIM) or cash on delivery -> patient enters the 12-digit UPI reference -> pharmacist confirms the money arrived -> packed -> out for delivery (patient gets a 4-digit **delivery code**) -> delivered only when the pharmacist enters that code.
* **There is no payment gateway.** Money goes directly from the patient to the pharmacy's UPI ID (set in the pharmacist's profile), and the app cannot see your bank, so the pharmacist confirms each payment by hand. For automatic confirmation integrate Razorpay/PhonePe/Cashfree webhooks.
* A pharmacy without a UPI ID shows a clearly labelled DEMO QR (placeholder handle that cannot receive money) when `DEV_MODE=1`; with `DEV_MODE=0` that pharmacy is COD-only.
* No courier tracking or refunds are built; a rejected paid order is only marked `refund_due`.

## Honest limitations (read before presenting)
* **Risk models are DEMO models** trained on synthetic data (`backend/app/services/ml.py`). Swap in real datasets (Pima, UCI heart, CKD, Framingham) for real use.
* **Image analysis** (Image AI page) uses classical OpenCV analysis that highlights regions for a doctor to review, unless you add trained ONNX weights (`ml/train_image_classifier.py`). Fracture, tumor-type and pneumonia *classification* need trained models and say so otherwise. Outputs are screening support, not diagnoses.
* **New risk models** (blood pressure, thyroid, anemia, cancer-lifestyle) are demo models on synthetic data like the others; the cancer score is a lifestyle/history screen, not a detector.
* **Report explainer** matches known report phrases only; it does not read images or ECG traces.
* Not built: per-user fine-grained permission editor (access is by role)/auto-reconciliation (video calls: WebRTC page, Jitsi link kept as backup).
* **Chatbot** is rule-based; set `LLM_API_KEY` to enable the LLM path. It is not medical advice.
* Email/SMS/WhatsApp, Google Maps and video consultation need your own provider keys; without them the app logs/skips those channels.
* Set `DEV_MODE=0`, a strong `JWT_SECRET` and a `DATA_KEY` for any real deployment, and never use the demo accounts there.

## ESP32
`hardware/esp32/medismart_esp32.ino` posts vitals to `/vitals/ingest`. Register a device in the Vitals page to get its key. Sensor reads are simulated until you plug in real sensor code.

## Tests
`cd backend && pytest` (service tests + API tests; API tests need fastapi/mongomock-motor installed).

## Status of this build
Built in a sandbox that could not install FastAPI or npm packages. What was verified there: all service tests pass (25), the new endpoint handlers passed a scripted end-to-end run against an in-memory database (messaging access control, hospital ops, theatre clash detection, forecast, kiosk, explainer, sleep planner, counselors, new risk models), the image analysis ran on test images for every task, and the whole React app bundles without errors in esbuild. **Not verified:** real HTTP calls through FastAPI (`pytest` runs them), and the Vite + Tailwind production build. Run Quick start and `pytest` on your machine and send me any error.


Clinical AI additions (EWS, voice STT, order flow, federated learning, board review) were verified with scripted end-to-end runs of their handlers on the in-memory database; the Whisper, Bhashini, SMS and LLM provider calls were not exercised. Advanced features were verified the same way: scripted end-to-end run on handlers (ledger tamper detection, WebRTC signaling relay, wearable idempotent ingest, prescription verify-before-activate gate) and esbuild bundling. Real browser WebRTC calls, real Tesseract OCR on photos, and the FastAPI HTTP layer were **not** run here.
