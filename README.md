# GovDoc Verify — Synthetic Demo

DEMO VIDEO LINK: https://drive.google.com/file/d/1q6M89-hq9l0Ws0Ha3Eiyri5fZFm8kG2j/view?usp=sharing

A college/demo application for transparent three-document integrity assessment. It uses **only fictional, clearly non-real identifiers** and never connects to government systems.

## What it does

- seeds exactly 5 fictional citizens, each with linked Aadhaar-like, PAN-like, and passport-like records (15 reference cards plus 4 controlled test variants);
- creates a persistent case with a backend-generated Case ID and access PIN; users can upload or replace Aadhaar-like, PAN-like, and passport-like PNG/JPEG/PDF documents individually (up to 10 MB each);
- uses a local OCR engine on the visible card text, then applies Aadhaar-like, PAN-like, and passport-like field parsers before any database lookup;
- exposes raw OCR text, confidence, recognized bounding-box count, extracted fields, and database field comparison in the officer review view;
- compares every document against the SQLite synthetic database and then checks that all three resolve to the same synthetic citizen;
- reports ELA, local-noise, compression/edge, and metadata as *Forensic Risk Indicators*;
- produces a transparent 0–100 risk explanation, persistent audit timeline, protected officer queue, and downloadable local PDF report for the legacy three-document endpoint.

## Run locally (macOS)

```bash
chmod +x start.sh
./start.sh
```

Open `http://localhost:5173`. The backend API is at `http://localhost:8000/docs`.

Create a verification case in the User Portal and save its Case ID + PIN. Upload any of the generated cards, then return later using those credentials. Use the Officer Portal to review cases needing verification. The officer ID and universal demo PIN are backend-only settings: set `OFFICER_ID` and `OFFICER_ACCESS_PIN` in the backend environment (see `.env.example`). Mixing cards from different fixtures demonstrates cross-document inconsistency. Controlled cards also demonstrate database mismatch, unknown document, low-quality input, and configured tampering evidence. The third fictional person's passport is expired.

For separate terminals:

```bash
python3 -m pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

## Demo data

The seeded database holds invented identifiers such as `DEM-AAR-1001`, `DEMAME001X`, and `DMP100001`. These formats are not official IDs and must never be interpreted as such.

It also includes approved fictional `repo_b`-provenance records in the same reference database and realistic test images. They follow the same upload, OCR, reference lookup, forensic, risk, and cross-verification flow as the original synthetic fixtures. One supplied Repo B PAN image has its PAN number redacted, so it is deliberately detected as PAN but cannot be reference-matched without fabricating OCR output. Additional Repo B Aadhaar and Passport samples from the linked source repository are available in `data/repo_b/documents`.

## Design limits

On Apple Silicon, the app first attempts macOS Vision OCR through the local Swift toolchain. It falls back to local Tesseract when Vision is unavailable; install it with `brew install tesseract` before starting the app. OCR confidence and computer-vision signals are not evidence that a document is fraudulent. The application is intentionally designed for education and presentations, not production identity decisions.

Optional forensic signals (localized ELA, copy-move, resampling, JPEG blocks, and edge inconsistency) are enabled by default and only support officer review. Disable one with an environment variable such as `FORENSICS_COPY_MOVE_ENABLED=false`; the corresponding names are `LOCALIZED_ELA`, `COPY_MOVE`, `RESAMPLING`, `JPEG_BLOCKS`, and `EDGE_INCONSISTENCY`.

