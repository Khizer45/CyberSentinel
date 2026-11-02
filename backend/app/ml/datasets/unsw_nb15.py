"""UNSW-NB15 feature schema (``unsw-nb15-flow-v1``).

Canonical source: the official training/testing partition published by UNSW Canberra
(``UNSW_NB15_training-set.csv`` 175,341 rows and ``UNSW_NB15_testing-set.csv`` 82,332 rows): ``id``,
42 features, ``attack_cat`` and ``label``.

The raw four-file release (UNSW-NB15_1..4.csv, 49 columns, no header row) uses different column names and
lacks ``rate``; it is not accepted as model input (see conflict C-16). Aliases below map the raw spellings
that *do* correspond, which helps the exploration notebook.

Dataset-specific facts handled here:

* ``proto``, ``service`` and ``state`` are categorical; ``service`` uses ``-`` for "no service".
* ``attack_cat`` values carry stray whitespace and the spelling ``Backdoors`` in some releases; label
  normalization strips and unifies them. Normal traffic may have an empty ``attack_cat`` in raw files.
* ``id`` is a row identifier and is dropped (leakage risk).
* TTL-derived features (``sttl``, ``dttl``, ``ct_state_ttl``) are known shortcut candidates.
"""

from __future__ import annotations

from app.ml.constants import BENIGN_LABEL, DatasetFamily
from app.ml.datasets.base import DatasetSchema, FeatureSpec

_FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec("dur"),
    FeatureSpec("proto", "categorical", "transaction protocol"),
    FeatureSpec("service", "categorical", "application service ('-' = none)"),
    FeatureSpec("state", "categorical", "connection state"),
    FeatureSpec("spkts"),
    FeatureSpec("dpkts"),
    FeatureSpec("sbytes"),
    FeatureSpec("dbytes"),
    FeatureSpec("rate"),
    FeatureSpec("sttl"),
    FeatureSpec("dttl"),
    FeatureSpec("sload"),
    FeatureSpec("dload"),
    FeatureSpec("sloss"),
    FeatureSpec("dloss"),
    FeatureSpec("sinpkt"),
    FeatureSpec("dinpkt"),
    FeatureSpec("sjit"),
    FeatureSpec("djit"),
    FeatureSpec("swin"),
    FeatureSpec("stcpb"),
    FeatureSpec("dtcpb"),
    FeatureSpec("dwin"),
    FeatureSpec("tcprtt"),
    FeatureSpec("synack"),
    FeatureSpec("ackdat"),
    FeatureSpec("smean"),
    FeatureSpec("dmean"),
    FeatureSpec("trans_depth"),
    FeatureSpec("response_body_len"),
    FeatureSpec("ct_srv_src"),
    FeatureSpec("ct_state_ttl"),
    FeatureSpec("ct_dst_ltm"),
    FeatureSpec("ct_src_dport_ltm"),
    FeatureSpec("ct_dst_sport_ltm"),
    FeatureSpec("ct_dst_src_ltm"),
    FeatureSpec("is_ftp_login"),
    FeatureSpec("ct_ftp_cmd"),
    FeatureSpec("ct_flw_http_mthd"),
    FeatureSpec("ct_src_ltm"),
    FeatureSpec("ct_srv_dst"),
    FeatureSpec("is_sm_ips_ports"),
)

# Normalized attack_cat -> (fine-grained label, category). Fine and category coincide for UNSW-NB15.
UNSW_LABEL_MAP: dict[str, tuple[str, str]] = {
    "normal": (BENIGN_LABEL, BENIGN_LABEL),
    "generic": ("Generic", "Generic"),
    "exploits": ("Exploits", "Exploits"),
    "fuzzers": ("Fuzzers", "Fuzzers"),
    "dos": ("DoS", "DoS"),
    "reconnaissance": ("Reconnaissance", "Reconnaissance"),
    "analysis": ("Analysis", "Analysis"),
    "backdoor": ("Backdoor", "Backdoor"),
    "backdoors": ("Backdoor", "Backdoor"),
    "shellcode": ("Shellcode", "Shellcode"),
    "worms": ("Worms", "Worms"),
}

UNSW_CATEGORIES: tuple[str, ...] = (
    BENIGN_LABEL,
    "Generic",
    "Exploits",
    "Fuzzers",
    "DoS",
    "Reconnaissance",
    "Analysis",
    "Backdoor",
    "Shellcode",
    "Worms",
)

UNSW_NB15_SCHEMA = DatasetSchema(
    family=DatasetFamily.UNSW_NB15,
    schema_version="unsw-nb15-flow-v1",
    display_name="UNSW-NB15 (official training/testing partition)",
    features=_FEATURES,
    label_columns=("attack_cat", "label"),
    identifier_columns=("id",),
    context_columns={},
    ip_context_keys=frozenset(),
    column_aliases={
        "smeansz": "smean",
        "dmeansz": "dmean",
        "res_bdy_len": "response_body_len",
        "sintpkt": "sinpkt",
        "dintpkt": "dinpkt",
    },
    known_duplicate_columns={},
    shortcut_feature_candidates=("sttl", "dttl", "ct_state_ttl"),
    label_mapping_version="unsw-nb15-labels-v1",
    source="UNSW-NB15, UNSW Canberra Cyber Range Lab (Moustafa & Slay, 2015)",
    notes=(
        "Use the official training/testing partition files; the raw 49-column release is not accepted for inference.",
        "attack_cat is the multi-class target; label is the binary target and is checked for consistency.",
    ),
)
