"""
Streamlit ECG Annotation Platform

Converted from a React component to a Streamlit app for single-file deployment.

Features:
- Simulated ECG signal generator
- File upload support (EDF, WFDB .dat, images, PDF - see README for notes)
- Lead selection and basic image-based lead extraction (simple cropping heuristic)
- Click-to-annotate on waveform (annotation types)
- AI-assisted auto-detection (simulated)
- Export annotations as JSON
- Comments panel and simple quality control flow

Notes:
- EDF parsing uses pyedflib (optional). WFDB parsing uses wfdb (optional).
- PDF processing to extract images requires poppler + pdf2image (optional). For deployment, images and EDF/WFDB are the most straightforward.
- Use `streamlit run app.py` to run locally.
"""

import streamlit as st
import numpy as np
import pandas as pd
import json
import io
import time
from datetime import datetime
from PIL import Image
import plotly.graph_objects as go
#from streamlit_plotly_events import plotly_events
pip install "streamlit-plotly-events\u003e=0.4.2"
# Optional imports - handle gracefully if not installed
try:
    import pyedflib
except Exception:
    pyedflib = None

try:
    import wfdb
except Exception:
    wfdb = None

# --- Helpers and Defaults ---

SAMPLE_RATE_DEFAULT = 500  # Hz
DURATION_DEFAULT = 10      # seconds

LEADS = ['Lead I', 'Lead II', 'Lead III', 'aVR', 'aVL', 'aVF',
         'V1', 'V2', 'V3', 'V4', 'V5', 'V6']

ANNOTATION_TYPES = [
    {"name": "R-Peak", "color": "#ef4444", "symbol": "R"},
    {"name": "P-Wave", "color": "#3b82f6", "symbol": "P"},
    {"name": "PR-Segment", "color": "#a78bfa", "symbol": "PR"},
    {"name": "T-Wave", "color": "#10b981", "symbol": "T"},
    {"name": "QRS-Start", "color": "#f59e0b", "symbol": "Q"},
    {"name": "QRS-End", "color": "#8b5cf6", "symbol": "S"},
    {"name": "J-Point", "color": "#f97316", "symbol": "J"},
    {"name": "ST-Segment", "color": "#06b6d4", "symbol": "ST"},
    {"name": "Arrhythmia", "color": "#ec4899", "symbol": "A"},
]


def generate_ecg_data(duration=DURATION_DEFAULT, sample_rate=SAMPLE_RATE_DEFAULT, seed=None):
    """Generate a simple synthetic ECG-like waveform as time,value pairs."""
    if seed is not None:
        np.random.seed(seed)
    samples = int(duration * sample_rate)
    t = np.linspace(0, duration, samples, endpoint=False)
    values = np.zeros_like(t)

    beat_interval = 0.8
    # Build waveform using simple components
    for i, ti in enumerate(t):
        phase = (ti % beat_interval) / beat_interval
        v = 0.0
        if 0.1 < phase < 0.2:
            v += 0.15 * np.sin((phase - 0.1) * np.pi * 10)
        if 0.25 < phase < 0.35:
            qrs_phase = (phase - 0.25) * 20
            if qrs_phase < 0.3:
                v -= 0.3
            elif qrs_phase < 0.7:
                v += 1.5
            else:
                v -= 0.4
        if 0.45 < phase < 0.65:
            v += 0.3 * np.sin((phase - 0.45) * np.pi * 5)
        v += (np.random.rand() - 0.5) * 0.05
        values[i] = v
    df = pd.DataFrame({"time": t, "value": values})
    return df


def parse_edf_file(buffer: bytes):
    """Basic EDF parsing using pyedflib if available. Returns a DataFrame for first signal."""
    if pyedflib is None:
        st.warning("pyEDFlib not installed - returning simulated data. Install with `pip install pyedflib`.")
        return generate_ecg_data()
    try:
        with io.BytesIO(buffer) as bio:
            # pyedflib needs a filename-like object on filesystem; write to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(buffer)
                tmp.flush()
                fname = tmp.name
            f = pyedflib.EdfReader(fname)
            n = f.signals_in_file
            sigbufs = f.readSignal(0)
            fs = int(f.getSampleFrequency(0))
            f._close()
            # Build dataframe
            t = np.arange(len(sigbufs)) / fs
            values = np.asarray(sigbufs)
            df = pd.DataFrame({"time": t, "value": values})
            return df
    except Exception as e:
        st.error(f"Error parsing EDF: {e}")
        return generate_ecg_data()


def parse_wfdb_dat(buffer: bytes):
    """Try to parse WFDB .dat using wfdb package if available. Returns DataFrame or simulated data."""
    if wfdb is None:
        st.warning("wfdb package not installed - returning simulated data. Install with `pip install wfdb`.")
        return generate_ecg_data()
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(buffer)
            tmp.flush()
            fname = tmp.name
        # wfdb.rdsamp expects a recordname (without .dat) + path; this is a best-effort approach:
        # Use wfdb.rdrecord for raw files - but this simplistic approach may not work for all wfdb dat formats.
        record = wfdb.rdrecord(fname.replace('.dat', ''), physical=False, pn_dir=None)
        sig = record.p_signal[:, 0]
        fs = record.fs if hasattr(record, "fs") else 360
        t = np.arange(len(sig)) / fs
        df = pd.DataFrame({"time": t, "value": sig})
        return df
    except Exception as e:
        st.error(f"Error parsing WFDB data: {e}")
        return generate_ecg_data()


def extract_leads_from_image_pil(image: Image.Image):
    """
    Very simple heuristic extraction: split image into a 4x4 grid and map common 12-lead positions.
    This is a naive approach and will work only for standard 12-lead layouts with consistent margins.
    """
    w, h = image.size
    lead_h = h // 4
    lead_w = w // 4
    positions = {
        'Lead I': (0, 0, lead_w, lead_h),
        'Lead II': (lead_w, 0, lead_w * 2, lead_h),
        'Lead III': (lead_w * 2, 0, lead_w * 3, lead_h),
        'aVR': (lead_w * 3, 0, lead_w * 4, lead_h),
        'aVL': (0, lead_h, lead_w, lead_h * 2),
        'aVF': (lead_w, lead_h, lead_w * 2, lead_h * 2),
        'V1': (lead_w * 2, lead_h, lead_w * 3, lead_h * 2),
        'V2': (lead_w * 3, lead_h, lead_w * 4, lead_h * 2),
        'V3': (0, lead_h * 2, lead_w, lead_h * 3),
        'V4': (lead_w, lead_h * 2, lead_w * 2, lead_h * 3),
        'V5': (lead_w * 2, lead_h * 2, lead_w * 3, lead_h * 3),
        'V6': (lead_w * 3, lead_h * 2, lead_w * 4, lead_h * 3),
    }
    extracted = {}
    for lead, (x1, y1, x2, y2) in positions.items():
        crop = image.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        extracted[lead] = buf.getvalue()
    return extracted


def run_ai_detection_simulation(df: pd.DataFrame, selected_lead: str, existing_annotations: list):
    """Simulate AI detection of R-peaks every ~beat interval. Returns list of annotations (dicts)."""
    # Find peaks by thresholding the value (naive)
    annotations = []
    beat_interval = 0.8
    times = np.arange(0, DURATION_DEFAULT, beat_interval)
    base_id = int(time.time() * 1000)
    for i, t0 in enumerate(times):
        # place an R-peak near the expected time (offset)
        ann_time = float(np.clip(t0 + 0.28, 0, df['time'].iloc[-1]))
        annotations.append({
            "id": base_id + i,
            "time": ann_time,
            "type": "R-Peak",
            "lead": selected_lead,
            "aiGenerated": True,
            "confidence": round(0.9 + 0.1 * np.random.rand(), 3)
        })
    # Merge with existing, avoid duplicates
    return annotations


# --- Session State Initialization ---
if "ecg_df" not in st.session_state:
    st.session_state.ecg_df = generate_ecg_data()

if "annotations" not in st.session_state:
    st.session_state.annotations = []

if "uploaded_file_name" not in st.session_state:
    st.session_state.uploaded_file_name = ""

if "extracted_leads" not in st.session_state:
    st.session_state.extracted_leads = {}

if "comments" not in st.session_state:
    st.session_state.comments = []

if "quality_status" not in st.session_state:
    st.session_state.quality_status = "pending"

# --- Layout ---
st.set_page_config(page_title="ECG Annotation Platform", layout="wide", initial_sidebar_state="expanded")
st.title("ECG Annotation Platform (Streamlit)")

# Sidebar: upload, lead selection, annotation type, controls
with st.sidebar:
    st.header("Files & Controls")
    uploaded_file = st.file_uploader("Upload ECG file (edf, dat, jpg, png, pdf)", type=['edf', 'dat', 'jpg', 'jpeg', 'png', 'pdf'])
    if uploaded_file is not None:
        fname = uploaded_file.name
        st.session_state.uploaded_file_name = fname
        ext = fname.split('.')[-1].lower()

        if ext in ['jpg', 'jpeg', 'png']:
            img = Image.open(uploaded_file).convert("RGB")
            st.session_state.extracted_leads = {}
            st.info("Extracting leads from image (heuristic)...")
            extracted = extract_leads_from_image_pil(img)
            st.session_state.extracted_leads = extracted
            # For demo, still use simulated ECG signals
            st.session_state.ecg_df = generate_ecg_data()
            st.success(f"Image {fname} loaded. {len(extracted)} lead images extracted (bytes stored).")
        elif ext == 'edf':
            buffer = uploaded_file.read()
            df = parse_edf_file(buffer)
            st.session_state.ecg_df = df
            st.success(f"EDF file {fname} loaded. Samples: {len(df)}")
        elif ext in ['dat', 'wfdb']:
            buffer = uploaded_file.read()
            df = parse_wfdb_dat(buffer)
            st.session_state.ecg_df = df
            st.success(f"WFDB-like file {fname} processed. Samples: {len(df)}")
        elif ext == 'pdf':
            # PDF handling is complex in-browser; show placeholder
            st.warning("PDF processing requires extra dependencies (pdf2image + poppler). For now loading simulated data.")
            st.session_state.ecg_df = generate_ecg_data()
            st.success(f"PDF {fname} received (not fully processed).")
        else:
            st.error("Unsupported file format - using simulated ECG.")

    st.markdown("---")
    selected_lead = st.selectbox("Select Lead", LEADS, index=1)
    st.session_state.selected_lead = selected_lead

    ann_mode = st.selectbox("Annotation Type", [a["name"] for a in ANNOTATION_TYPES], index=0)
    st.session_state.annotation_mode = ann_mode

    st.markdown("### View")
    show_grid = st.checkbox("Show Grid", value=True)
    zoom = st.slider("Zoom (x)", min_value=0.5, max_value=4.0, value=1.0, step=0.5)
    st.session_state.show_grid = show_grid
    st.session_state.zoom = zoom

    st.markdown("### AI Assistance")
    if st.button("Auto-Detect (AI)"):
        with st.spinner("Running AI detection (simulated)..."):
            ai_annotations = run_ai_detection_simulation(st.session_state.ecg_df, selected_lead, st.session_state.annotations)
            # append using session_state
            st.session_state.annotations = st.session_state.annotations + ai_annotations
            st.success(f"AI suggested {len(ai_annotations)} annotations.")

    st.markdown("---")
    st.markdown("### Quality Control")
    st.write(f"Status: **{st.session_state.quality_status}**")
    if st.button("Submit for Review", disabled=(st.session_state.quality_status != "pending")):
        st.session_state.quality_status = "under-review"
        st.experimental_rerun()  # quick feedback; reviewed will be set below

    # approve simulation
    if st.session_state.quality_status == "under-review":
        # immediately approve after a small delay (simulate)
        time.sleep(1.0)
        st.session_state.quality_status = "approved"
        st.experimental_rerun()

    st.markdown("---")
    if st.button("Export Annotations (.json)"):
        export = {
            "metadata": {
                "fileName": st.session_state.uploaded_file_name or "simulated-ecg",
                "lead": st.session_state.selected_lead if "selected_lead" in st.session_state else selected_lead,
                "exportDate": datetime.utcnow().isoformat() + "Z",
                "annotator": "Streamlit User",
            },
            "annotations": [
                {
                    "time": float(a["time"]),
                    "type": a["type"],
                    "aiGenerated": bool(a.get("aiGenerated", False)),
                    "confidence": float(a.get("confidence", 0.0))
                } for a in st.session_state.annotations
            ]
        }
        b = json.dumps(export, indent=2).encode("utf-8")
        st.download_button("Download JSON", b, file_name="ecg-annotations.json", mime="application/json")


# Main: ECG viewer and annotation list
col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"Viewer — {st.session_state.uploaded_file_name or 'Simulated ECG'} — {st.session_state.selected_lead}")
    df = st.session_state.ecg_df.copy()
    # apply zoom by taking portion of data; zoom>1 means shorter visible duration
    visible_duration = DURATION_DEFAULT / st.session_state.zoom
    # center view around 0..visible_duration by default
    x_min = 0.0
    x_max = visible_duration

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['value'],
        mode='lines',
        line=dict(color='#22c55e'),
        name='ECG'
    ))

    # Add annotation shapes (vertical lines) and markers
    shapes = []
    ann_markers_x = []
    ann_markers_y = []
    ann_texts = []
    for ann in st.session_state.annotations:
        if x_min <= ann["time"] <= x_max:
            shapes.append(dict(
                type="line",
                x0=ann["time"],
                x1=ann["time"],
                y0=df['value'].min() - 0.5,
                y1=df['value'].max() + 0.5,
                line=dict(color='#a855f7' if ann.get("aiGenerated") else "#FF9900", width=2, dash="dash" if not ann.get("aiGenerated") else "dot")
            ))
            ann_markers_x.append(ann["time"])
            # find y at that time (closest)
            closest_idx = int((np.abs(df['time'] - ann["time"])).idxmin())
            ann_markers_y.append(df['value'].iloc[closest_idx])
            ann_texts.append(ann.get("type", "") + (" (AI)" if ann.get("aiGenerated") else ""))

    if ann_markers_x:
        fig.add_trace(go.Scatter(
            x=ann_markers_x,
            y=ann_markers_y,
            mode='markers+text',
            marker=dict(size=8, color='red'),
            text=ann_texts,
            textposition="top center",
            showlegend=False
        ))

    fig.update_layout(
        shapes=shapes,
        margin=dict(l=40, r=20, t=20, b=40),
        template="plotly_dark",
        xaxis=dict(range=[x_min, x_max], title="Time (s)"),
        yaxis=dict(title="Amplitude (mV)"),
        height=450
    )

    # Render interactive Plotly chart and capture clicks with plotly_events
    # plotly_events returns list of dicts for clicked points (x,y)
    ev = plotly_events(fig, click_event=True, hover_event=True, select_event=False, override_height=450)

    # When user clicks on canvas (point), add annotation at clicked x
    if ev:
        # Plotly click event produces list; handle first
        e0 = ev[0]
        if 'x' in e0:
            clicked_x = float(e0['x'])
            # Add annotation at clicked time
            new_ann = {
                "id": int(time.time() * 1000),
                "time": clicked_x,
                "type": st.session_state.annotation_mode,
                "lead": st.session_state.selected_lead,
                "aiGenerated": False,
                "user": "Current User"
            }
            st.session_state.annotations.append(new_ann)
            st.experimental_rerun()

with col2:
    st.subheader("Annotations")
    if len(st.session_state.annotations) == 0:
        st.info("No annotations yet. Click on the waveform to add one, or use Auto-Detect.")
    else:
        for ann in sorted(st.session_state.annotations, key=lambda a: a["time"]):
            row = st.container()
            with row:
                cols = st.columns([0.15, 0.6, 0.25])
                ann_symbol = next((a["symbol"] for a in ANNOTATION_TYPES if a["name"] == ann["type"]), "?")
                cols[0].markdown(f"**{ann_symbol}**")
                cols[1].markdown(f"{ann['type']}  \n**{ann['time']:.3f}s**{'  \n**(AI)**' if ann.get('aiGenerated') else ''}")
                if cols[2].button("Remove", key=f"rm_{ann['id']}"):
                    st.session_state.annotations = [a for a in st.session_state.annotations if a["id"] != ann["id"]]
                    st.experimental_rerun()

st.markdown("---")
# Comments panel
st.subheader("Comments")
c1, c2 = st.columns([4, 1])
with c1:
    comment_text = st.text_area("Add comment", key="comment_box", height=80)
with c2:
    if st.button("Post"):
        if comment_text and comment_text.strip():
            st.session_state.comments.append({
                "id": int(time.time() * 1000),
                "user": "Current User",
                "text": comment_text.strip(),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            st.session_state.comment_box = ""
            st.experimental_rerun()

if st.session_state.comments:
    for c in reversed(st.session_state.comments[-50:]):
        st.markdown(f"**{c['user']}** • {c['timestamp']}")
        st.write(c["text"])
        st.markdown("---")

# Small status & instructions
st.sidebar.markdown("### App Status")
st.sidebar.write(f"Annotations: {len(st.session_state.annotations)}")
st.sidebar.write(f"Comments: {len(st.session_state.comments)}")
st.sidebar.write(f"Quality: {st.session_state.quality_status}")

st.info("This Streamlit demo uses simulated AI and simplified file parsing. See README for instructions to enable EDF/WFDB/PDF processing and extra dependencies.")
