# ECG Annotation Platform — Streamlit Edition

This repository contains a Streamlit-based ECG annotation demo converted from a React component. The app demonstrates an interactive ECG waveform viewer with annotation tools, simulated AI-assisted detection, simple image-based lead extraction, and basic file upload support.

This is intended as a developer-friendly demo and starting point for production work. Many parts (EDF/WFDB parsing, PDF → image extraction, AI digitization) are simplified or simulated.

---

## Features

- Simulated ECG signal generation (default).
- File upload support:
  - EDF (.edf) — parsed with `pyedflib` (optional).
  - WFDB-like (.dat or .wfdb) — best-effort with `wfdb` (optional).
  - Images (.jpg, .jpeg, .png) — basic heuristic cropping into 12 leads.
  - PDF (.pdf) — placeholder (real extraction requires `pdf2image` + `poppler`).
- Click on the waveform to add annotations (various types).
- AI Auto-Detect button (simulated) to add R-peak annotations.
- Export annotations as JSON.
- Comments panel and basic quality control flow.

---

## Files

- `app.py` — main Streamlit application file.
- `requirements.txt` — Python dependencies.
- `README.md` — this documentation.

---

## Requirements

Basic (for the demo UI):

- Python 3.9+
- pip

Python packages (provided in `requirements.txt`):

- streamlit
- numpy
- pandas
- plotly
- pillow
- streamlit-plotly-events

Optional (enable EDF / WFDB parsing and PDF processing):

- pyedflib — for EDF files
- wfdb — WFDB record access (PhysioNet)
- pdf2image and poppler — to convert PDF pages to images (poppler binary required)

Notes:
- `pdf2image` requires the Poppler utilities installed on the system. On macOS: `brew install poppler`. On Ubuntu: `sudo apt-get install poppler-utils`.
- `pyedflib` and `wfdb` may have binary dependencies; install with pip and consult their docs if installation fails.

---

## Install & Run

1. Create and activate a Python virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
.venv\Scripts\activate     # Windows (PowerShell)
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

Open the provided localhost URL in your browser (usually `http://localhost:8501`).

---

## Deployment

- Streamlit Cloud: create a new app and point to this repository; make sure `requirements.txt` is present.
- Docker: You can create a Dockerfile with the streamlit image and `requirements.txt`.

---

## Notes & Next Steps

- The image-based lead extraction uses a crude 4x4 grid split. For real-world scanned ECGs, use a proper computer-vision pipeline:
  - detect gridlines
  - find lead bounding boxes
  - perform waveform deskewing and tracing
- For production EDF/WFDB parsing, validate file headers and sample rates precisely. Use `pyedflib` to read EDF headers and signals, and `wfdb` for PhysioNet records.
- AI digitization: integrate a model (or cloud API) to convert raster ECG images or PDF traces to sampled waveforms.
- Consider storing annotations and comments in a backend (database) for collaboration.
- Add authentication for multi-user annotation and real-time sync.

---

If you want, I can:
- Add example EDF and WFDB sample files to test.
- Add a richer PDF -> image pipeline with instructions for poppler installation.
- Wire the app to a small Flask/FastAPI backend for persistence.
