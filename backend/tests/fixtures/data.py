"""Synthetic CSV builders for tests (format fixtures only — values carry no meaning)."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from app.ml.datasets.cicids2017 import CICIDS2017_SCHEMA
from app.ml.datasets.unsw_nb15 import UNSW_NB15_SCHEMA

UNSW_CATEGORIES = ["Normal", "Generic", "Exploits", "DoS"]
CIC_LABELS = ["BENIGN", "DoS Hulk", "PortScan", "Web Attack – XSS"]


def unsw_frame(rows: int = 300, seed: int = 0, *, with_labels: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cats = rng.choice(len(UNSW_CATEGORIES), size=rows, p=[0.6, 0.15, 0.15, 0.1])
    data: dict[str, object] = {"id": np.arange(1, rows + 1)}
    for i, name in enumerate(UNSW_NB15_SCHEMA.numeric_features):
        shift = (cats == (i % 4)).astype(float) * 1.5
        data[name] = np.round(np.exp(rng.normal(1.0 + shift, 0.8)), 4)
    data["proto"] = np.where(cats == 3, "udp", rng.choice(["tcp", "udp", "arp"], rows))
    data["service"] = rng.choice(["-", "http", "dns"], rows)
    data["state"] = rng.choice(["FIN", "INT", "CON"], rows)
    frame = pd.DataFrame(data)
    if with_labels:
        frame["attack_cat"] = [UNSW_CATEGORIES[c] for c in cats]
        frame["label"] = (cats != 0).astype(int)
    columns = ["id", *UNSW_NB15_SCHEMA.feature_names] + (["attack_cat", "label"] if with_labels else [])
    return frame[columns]


def unsw_csv(rows: int = 300, seed: int = 0, *, with_labels: bool = True) -> bytes:
    return unsw_frame(rows, seed, with_labels=with_labels).to_csv(index=False).encode("utf-8")


RAW_CIC_FEATURE_HEADERS = [
    " Destination Port",
    " Flow Duration",
    " Total Fwd Packets",
    " Total Backward Packets",
    "Total Length of Fwd Packets",
    " Total Length of Bwd Packets",
    " Fwd Packet Length Max",
    " Fwd Packet Length Min",
    " Fwd Packet Length Mean",
    " Fwd Packet Length Std",
    "Bwd Packet Length Max",
    " Bwd Packet Length Min",
    " Bwd Packet Length Mean",
    " Bwd Packet Length Std",
    "Flow Bytes/s",
    " Flow Packets/s",
    " Flow IAT Mean",
    " Flow IAT Std",
    " Flow IAT Max",
    " Flow IAT Min",
    "Fwd IAT Total",
    " Fwd IAT Mean",
    " Fwd IAT Std",
    " Fwd IAT Max",
    " Fwd IAT Min",
    "Bwd IAT Total",
    " Bwd IAT Mean",
    " Bwd IAT Std",
    " Bwd IAT Max",
    " Bwd IAT Min",
    "Fwd PSH Flags",
    " Bwd PSH Flags",
    " Fwd URG Flags",
    " Bwd URG Flags",
    " Fwd Header Length",
    " Bwd Header Length",
    "Fwd Packets/s",
    " Bwd Packets/s",
    " Min Packet Length",
    " Max Packet Length",
    " Packet Length Mean",
    " Packet Length Std",
    " Packet Length Variance",
    "FIN Flag Count",
    " SYN Flag Count",
    " RST Flag Count",
    " PSH Flag Count",
    " ACK Flag Count",
    " URG Flag Count",
    " CWE Flag Count",
    " ECE Flag Count",
    " Down/Up Ratio",
    " Average Packet Size",
    " Avg Fwd Segment Size",
    " Avg Bwd Segment Size",
    " Fwd Header Length",
    "Fwd Avg Bytes/Bulk",
    " Fwd Avg Packets/Bulk",
    " Fwd Avg Bulk Rate",
    " Bwd Avg Bytes/Bulk",
    " Bwd Avg Packets/Bulk",
    "Bwd Avg Bulk Rate",
    "Subflow Fwd Packets",
    " Subflow Fwd Bytes",
    " Subflow Bwd Packets",
    " Subflow Bwd Bytes",
    "Init_Win_bytes_forward",
    " Init_Win_bytes_backward",
    " act_data_pkt_fwd",
    " min_seg_size_forward",
    "Active Mean",
    " Active Std",
    " Active Max",
    " Active Min",
    "Idle Mean",
    " Idle Std",
    " Idle Max",
    " Idle Min",
]
assert len(RAW_CIC_FEATURE_HEADERS) == 78


def cic_frame(rows: int = 300, seed: int = 0) -> pd.DataFrame:
    """Canonical-feature frame (77 features) + label, for training fixture models."""
    rng = np.random.default_rng(seed)
    cats = rng.choice(len(CIC_LABELS), size=rows, p=[0.6, 0.15, 0.15, 0.1])
    data = {}
    for i, name in enumerate(CICIDS2017_SCHEMA.feature_names):
        shift = (cats == (i % 4)).astype(float) * 1.2
        data[name] = np.round(np.exp(rng.normal(2.0 + shift, 0.7)), 3)
    frame = pd.DataFrame(data)
    frame["label"] = [CIC_LABELS[c] for c in cats]
    return frame


def cic_traffic_labelling_csv(rows: int = 200, seed: int = 0, *, infinity_rows: int = 3) -> bytes:
    """Raw TrafficLabelling format: identifiers with IPs, original headers, duplicate column, cp1252 labels."""
    frame = cic_frame(rows, seed)
    rng = np.random.default_rng(seed + 1)
    header = [
        " Flow ID",
        " Source IP",
        " Source Port",
        " Destination IP",
        *RAW_CIC_FEATURE_HEADERS[:1],
        " Protocol",
        " Timestamp",
        *RAW_CIC_FEATURE_HEADERS[1:],
        " Label",
    ]
    lines = [",".join(header)]
    features = CICIDS2017_SCHEMA.feature_names
    for i, row in frame.iterrows():
        values = [str(row[f]) for f in features]
        if i < infinity_rows:
            values[features.index("flow_bytes_s")] = "Infinity"
        # Insert the duplicate Fwd Header Length copy at its original position (after avg_bwd_segment_size).
        dup_at = features.index("avg_bwd_segment_size") + 1
        values.insert(dup_at, values[features.index("fwd_header_length")])
        src = f"192.168.10.{rng.integers(1, 250)}"
        dst = f"10.0.0.{rng.integers(1, 250)}"
        ident = [f"{src}-{dst}-{rng.integers(1024, 65000)}-80-6", src, str(rng.integers(1024, 65000)), dst]
        line = ident + values[:1] + ["6", "3/7/2017 9:00"] + values[1:] + [row["label"]]
        lines.append(",".join(line))
    return ("\n".join(lines) + "\n").encode("cp1252")


def to_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")
