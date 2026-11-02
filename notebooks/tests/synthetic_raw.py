"""Synthetic raw-format fixtures for **smoke-testing the notebooks only**.

The files mimic the *format* of the official releases (header spelling, duplicated CIC header, cp1252 en dash
in web-attack labels, ``Infinity`` values, exact and conflicting duplicates, an ultra-rare class, UNSW
``attack_cat`` whitespace/``Backdoors`` variants) so that every code path of the notebooks executes.

The values are random draws with class-dependent shifts. They carry no information about real network
traffic, and any metric computed on them is meaningless. Never place these files in ``data/raw``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CIC_HEADER = [
    " Destination Port", " Flow Duration", " Total Fwd Packets", " Total Backward Packets",
    "Total Length of Fwd Packets", " Total Length of Bwd Packets", " Fwd Packet Length Max",
    " Fwd Packet Length Min", " Fwd Packet Length Mean", " Fwd Packet Length Std", "Bwd Packet Length Max",
    " Bwd Packet Length Min", " Bwd Packet Length Mean", " Bwd Packet Length Std", "Flow Bytes/s",
    " Flow Packets/s", " Flow IAT Mean", " Flow IAT Std", " Flow IAT Max", " Flow IAT Min", "Fwd IAT Total",
    " Fwd IAT Mean", " Fwd IAT Std", " Fwd IAT Max", " Fwd IAT Min", "Bwd IAT Total", " Bwd IAT Mean",
    " Bwd IAT Std", " Bwd IAT Max", " Bwd IAT Min", "Fwd PSH Flags", " Bwd PSH Flags", " Fwd URG Flags",
    " Bwd URG Flags", " Fwd Header Length", " Bwd Header Length", "Fwd Packets/s", " Bwd Packets/s",
    " Min Packet Length", " Max Packet Length", " Packet Length Mean", " Packet Length Std",
    " Packet Length Variance", "FIN Flag Count", " SYN Flag Count", " RST Flag Count", " PSH Flag Count",
    " ACK Flag Count", " URG Flag Count", " CWE Flag Count", " ECE Flag Count", " Down/Up Ratio",
    " Average Packet Size", " Avg Fwd Segment Size", " Avg Bwd Segment Size", " Fwd Header Length",
    "Fwd Avg Bytes/Bulk", " Fwd Avg Packets/Bulk", " Fwd Avg Bulk Rate", " Bwd Avg Bytes/Bulk",
    " Bwd Avg Packets/Bulk", "Bwd Avg Bulk Rate", "Subflow Fwd Packets", " Subflow Fwd Bytes",
    " Subflow Bwd Packets", " Subflow Bwd Bytes", "Init_Win_bytes_forward", " Init_Win_bytes_backward",
    " act_data_pkt_fwd", " min_seg_size_forward", "Active Mean", " Active Std", " Active Max", " Active Min",
    "Idle Mean", " Idle Std", " Idle Max", " Idle Min", " Label",
]
CIC_DUPLICATE_POSITIONS = (34, 55)  # both " Fwd Header Length"

# Label -> (rows, mean shift applied to the log-scale of a class-specific feature block)
CIC_LABELS = {
    "BENIGN": (3200, 0.0),
    "DoS Hulk": (300, 1.5),
    "DoS GoldenEye": (150, 1.6),
    "DoS slowloris": (120, 1.7),
    "DoS Slowhttptest": (120, 1.8),
    "DDoS": (350, 2.2),
    "PortScan": (350, -1.5),
    "FTP-Patator": (150, 1.0),
    "SSH-Patator": (150, 1.1),
    "Bot": (120, -1.0),
    "Web Attack – Brute Force": (60, 0.8),
    "Web Attack – XSS": (50, 0.85),
    "Web Attack – Sql Injection": (25, 0.9),
    "Infiltration": (30, 2.5),
    "Heartbleed": (4, 3.0),
}
CIC_PORTS = {"BENIGN": 443, "PortScan": 0, "FTP-Patator": 21, "SSH-Patator": 22, "Bot": 8080}


def _cic_rows(rng: np.random.Generator) -> pd.DataFrame:
    frames = []
    n_features = len(CIC_HEADER) - 1
    for k, (label, (count, shift)) in enumerate(CIC_LABELS.items()):
        base = rng.normal(loc=2.0, scale=1.0, size=(count, n_features))
        block = slice((k * 5) % 60, (k * 5) % 60 + 10)
        base[:, block] += shift
        values = np.round(np.exp(base), 3)
        values[:, 0] = CIC_PORTS.get(label, 80) if label != "BENIGN" else rng.choice([443, 80, 53], size=count)
        frame = pd.DataFrame(values, columns=[f"f{i}" for i in range(n_features)])
        frame["label"] = label
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    dup_a, dup_b = CIC_DUPLICATE_POSITIONS
    data[f"f{dup_b}"] = data[f"f{dup_a}"]
    data = data.astype(object)
    data.loc[rng.choice(len(data), 40, replace=False), "f14"] = "Infinity"  # Flow Bytes/s
    data.loc[rng.choice(len(data), 25, replace=False), "f15"] = "NaN"  # Flow Packets/s
    exact_dupes = data.sample(60, random_state=1)
    conflicting = data[data["label"] == "BENIGN"].sample(5, random_state=2).assign(label="PortScan")
    return pd.concat([data, exact_dupes, conflicting], ignore_index=True).sample(frac=1.0, random_state=3)


def write_cicids2017(directory: Path, seed: int = 0) -> list[Path]:
    """Write three CIC-IDS2017-format files (cp1252, original headers, duplicated header)."""
    rng = np.random.default_rng(seed)
    directory.mkdir(parents=True, exist_ok=True)
    data = _cic_rows(rng)
    names = [
        "Monday-WorkingHours.pcap_ISCX.csv",
        "Wednesday-workingHours.pcap_ISCX.csv",
        "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    ]
    paths = []
    bounds = np.linspace(0, len(data), len(names) + 1).astype(int)
    for i in range(len(names)):
        part = data.iloc[bounds[i] : bounds[i + 1]]
        lines = [",".join(CIC_HEADER)]
        for row in part.itertuples(index=False):
            lines.append(",".join(str(v) for v in row))
        path = directory / names[i]
        path.write_bytes(("\n".join(lines) + "\n").encode("cp1252"))
        paths.append(path)
    return paths


UNSW_FEATURES = [
    "dur", "proto", "service", "state", "spkts", "dpkts", "sbytes", "dbytes", "rate", "sttl", "dttl", "sload",
    "dload", "sloss", "dloss", "sinpkt", "dinpkt", "sjit", "djit", "swin", "stcpb", "dtcpb", "dwin", "tcprtt",
    "synack", "ackdat", "smean", "dmean", "trans_depth", "response_body_len", "ct_srv_src", "ct_state_ttl",
    "ct_dst_ltm", "ct_src_dport_ltm", "ct_dst_sport_ltm", "ct_dst_src_ltm", "is_ftp_login", "ct_ftp_cmd",
    "ct_flw_http_mthd", "ct_src_ltm", "ct_srv_dst", "is_sm_ips_ports",
]
UNSW_CATEGORIES = {
    "Normal": (0.0, 2600),
    "Generic": (1.8, 500),
    "Exploits": (1.2, 450),
    "Fuzzers": (0.7, 300),
    "DoS": (1.5, 200),
    "Reconnaissance": (-0.8, 200),
    "Analysis": (0.9, 60),
    "Backdoor": (1.1, 50),
    "Shellcode": (2.0, 40),
    "Worms": (2.6, 20),
}
TEST_VARIANTS = {"Fuzzers": " Fuzzers ", "Backdoor": "Backdoors", "Reconnaissance": " Reconnaissance"}


def _unsw_split(rng: np.random.Generator, scale: float, variants: bool) -> pd.DataFrame:
    frames = []
    numeric = [f for f in UNSW_FEATURES if f not in {"proto", "service", "state"}]
    for k, (category, (shift, count)) in enumerate(UNSW_CATEGORIES.items()):
        n = max(8, int(count * scale))
        values = np.exp(rng.normal(1.0, 1.0, size=(n, len(numeric))))
        values[:, (k * 3) % len(numeric): (k * 3) % len(numeric) + 6] *= np.exp(shift)
        frame = pd.DataFrame(np.round(values, 4), columns=numeric)
        frame["proto"] = rng.choice(["tcp", "udp", "unas"] if category != "Normal" else ["tcp", "udp", "arp"], size=n)
        frame["service"] = rng.choice(["-", "http", "dns", "ftp"], size=n)
        frame["state"] = rng.choice(["FIN", "INT", "CON", "REQ"], size=n)
        label = TEST_VARIANTS.get(category, category) if variants else category
        frame["attack_cat"] = label
        frame["label"] = 0 if category == "Normal" else 1
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True).sample(frac=1.0, random_state=int(scale * 100))
    data.insert(0, "id", np.arange(1, len(data) + 1))
    return data[["id", *UNSW_FEATURES, "attack_cat", "label"]]


def write_unsw_nb15(directory: Path, seed: int = 0) -> list[Path]:
    """Write UNSW-NB15 partition-format training and testing files."""
    rng = np.random.default_rng(seed)
    directory.mkdir(parents=True, exist_ok=True)
    train = _unsw_split(rng, 1.0, variants=False)
    test = _unsw_split(rng, 0.5, variants=True)
    paths = [directory / "UNSW_NB15_training-set.csv", directory / "UNSW_NB15_testing-set.csv"]
    train.to_csv(paths[0], index=False)
    test.to_csv(paths[1], index=False)
    return paths
