"""CIC-IDS2017 feature schema (``cicids2017-flow-v1``).

Source: Canadian Institute for Cybersecurity, CIC-IDS2017 "MachineLearningCVE" CSV files (78 feature
columns + ``Label``) and the "TrafficLabelling" variant, which additionally carries ``Flow ID``,
``Source IP``, ``Source Port``, ``Destination IP``, ``Protocol`` and ``Timestamp``.

Dataset-specific facts handled here:

* Headers contain leading spaces and punctuation (``" Flow Bytes/s"``); names are normalized to snake_case.
* ``Fwd Header Length`` appears **twice**. The second copy is a known, identical duplicate: the reader
  verifies equality and drops it. Any other duplicated header is rejected (RTM FR-04).
* Some rows contain ``Infinity``/``NaN`` in ``Flow Bytes/s`` and ``Flow Packets/s``; cleaning maps non-finite
  values to missing and the trained imputer fills them (same code at training and inference).
* ``Protocol`` exists only in the TrafficLabelling variant, so it is treated as flow context, not as a model
  feature, to keep one feature contract for both variants.
* Web-attack labels contain an en dash that is often mis-decoded (``"Web Attack � XSS"``); label
  normalization is punctuation-insensitive.
"""

from __future__ import annotations

from app.ml.constants import BENIGN_LABEL, DatasetFamily
from app.ml.datasets.base import DatasetSchema, FeatureSpec

_FEATURE_NAMES: tuple[str, ...] = (
    "destination_port",
    "flow_duration",
    "total_fwd_packets",
    "total_backward_packets",
    "total_length_of_fwd_packets",
    "total_length_of_bwd_packets",
    "fwd_packet_length_max",
    "fwd_packet_length_min",
    "fwd_packet_length_mean",
    "fwd_packet_length_std",
    "bwd_packet_length_max",
    "bwd_packet_length_min",
    "bwd_packet_length_mean",
    "bwd_packet_length_std",
    "flow_bytes_s",
    "flow_packets_s",
    "flow_iat_mean",
    "flow_iat_std",
    "flow_iat_max",
    "flow_iat_min",
    "fwd_iat_total",
    "fwd_iat_mean",
    "fwd_iat_std",
    "fwd_iat_max",
    "fwd_iat_min",
    "bwd_iat_total",
    "bwd_iat_mean",
    "bwd_iat_std",
    "bwd_iat_max",
    "bwd_iat_min",
    "fwd_psh_flags",
    "bwd_psh_flags",
    "fwd_urg_flags",
    "bwd_urg_flags",
    "fwd_header_length",
    "bwd_header_length",
    "fwd_packets_s",
    "bwd_packets_s",
    "min_packet_length",
    "max_packet_length",
    "packet_length_mean",
    "packet_length_std",
    "packet_length_variance",
    "fin_flag_count",
    "syn_flag_count",
    "rst_flag_count",
    "psh_flag_count",
    "ack_flag_count",
    "urg_flag_count",
    "cwe_flag_count",
    "ece_flag_count",
    "down_up_ratio",
    "average_packet_size",
    "avg_fwd_segment_size",
    "avg_bwd_segment_size",
    "fwd_avg_bytes_bulk",
    "fwd_avg_packets_bulk",
    "fwd_avg_bulk_rate",
    "bwd_avg_bytes_bulk",
    "bwd_avg_packets_bulk",
    "bwd_avg_bulk_rate",
    "subflow_fwd_packets",
    "subflow_fwd_bytes",
    "subflow_bwd_packets",
    "subflow_bwd_bytes",
    "init_win_bytes_forward",
    "init_win_bytes_backward",
    "act_data_pkt_fwd",
    "min_seg_size_forward",
    "active_mean",
    "active_std",
    "active_max",
    "active_min",
    "idle_mean",
    "idle_std",
    "idle_max",
    "idle_min",
)

# Raw label -> (fine-grained canonical label, evaluation category).
# Keys are punctuation/case-insensitive (see app.ml.preprocessing.labels.label_key).
CIC_LABEL_MAP: dict[str, tuple[str, str]] = {
    "benign": (BENIGN_LABEL, BENIGN_LABEL),
    "dos hulk": ("DoS Hulk", "DoS"),
    "dos goldeneye": ("DoS GoldenEye", "DoS"),
    "dos slowloris": ("DoS Slowloris", "DoS"),
    "dos slowhttptest": ("DoS Slowhttptest", "DoS"),
    "ddos": ("DDoS", "DDoS"),
    "portscan": ("PortScan", "PortScan"),
    "ftp patator": ("FTP-Patator", "BruteForce"),
    "ssh patator": ("SSH-Patator", "BruteForce"),
    "bot": ("Bot", "Bot"),
    "web attack brute force": ("Web Attack - Brute Force", "WebAttack"),
    "web attack xss": ("Web Attack - XSS", "WebAttack"),
    "web attack sql injection": ("Web Attack - SQL Injection", "WebAttack"),
    "infiltration": ("Infiltration", "Infiltration"),
    "heartbleed": ("Heartbleed", "Heartbleed"),
}

CIC_CATEGORIES: tuple[str, ...] = (
    BENIGN_LABEL,
    "DoS",
    "DDoS",
    "PortScan",
    "BruteForce",
    "WebAttack",
    "Bot",
    "Infiltration",
    "Heartbleed",
)

CICIDS2017_SCHEMA = DatasetSchema(
    family=DatasetFamily.CICIDS2017,
    schema_version="cicids2017-flow-v1",
    display_name="CIC-IDS2017 (CICFlowMeter flow features)",
    features=tuple(FeatureSpec(name) for name in _FEATURE_NAMES),
    label_columns=("label",),
    identifier_columns=("flow_id", "source_ip", "source_port", "destination_ip", "protocol", "timestamp"),
    context_columns={
        "source_ip": "src_ip",
        "destination_ip": "dst_ip",
        "source_port": "src_port",
        "destination_port": "dst_port",
        "protocol": "protocol",
        "timestamp": "timestamp",
    },
    ip_context_keys=frozenset({"src_ip", "dst_ip"}),
    column_aliases={
        "src_ip": "source_ip",
        "dst_ip": "destination_ip",
        "src_port": "source_port",
        "dst_port": "destination_port",
    },
    known_duplicate_columns={"fwd_header_length": "fwd_header_length_1"},
    shortcut_feature_candidates=("destination_port", "init_win_bytes_forward", "init_win_bytes_backward"),
    label_mapping_version="cicids2017-labels-v1",
    source="CIC-IDS2017, Canadian Institute for Cybersecurity, University of New Brunswick (Sharafaldin et al., 2018)",
    notes=(
        "Flow ID embeds IP addresses and is never stored.",
        "Protocol is available only in the TrafficLabelling variant and is used as flow context, not as a feature.",
        "Known label-quality issues are documented by Engelen et al. (2021); see docs/dataset_cards/cicids2017.md.",
    ),
)
