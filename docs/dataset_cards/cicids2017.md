# Dataset card — CIC-IDS2017 (`cicids2017-flow-v1`)

| Field | Value |
|---|---|
| Publisher | Canadian Institute for Cybersecurity (CIC), University of New Brunswick |
| Citation | I. Sharafaldin, A. H. Lashkari, A. A. Ghorbani, "Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization", ICISSP 2018 |
| Files used | `MachineLearningCVE/*.pcap_ISCX.csv` (78 feature columns + `Label`); the `TrafficLabelling` variant (adds Flow ID, IPs, ports, protocol, timestamp) is also accepted |
| Collection | 5 days (3–7 July 2017) of lab traffic; flows extracted with CICFlowMeter |
| Licence | Research use with citation (check the CIC website for current terms) |

## Schema handling
* 77 canonical numeric features (snake_case). `Fwd Header Length` appears twice; the copy is verified identical
  and dropped. Any other duplicated header is rejected.
* `Flow ID` embeds IP addresses and is never stored. Source/destination IPs (TrafficLabelling only) are
  HMAC-pseudonymized when `IP_PSEUDONYMIZATION_KEY` is set, otherwise dropped.
* `Protocol` exists only in the TrafficLabelling variant → stored as flow context, not used as a model feature.
* Files may be Windows-1252 encoded (en dash in web-attack labels); UTF-8 and Windows-1252 are accepted.

## Labels (`cicids2017-labels-v1`)

| Raw label(s) | Category |
|---|---|
| BENIGN | Benign |
| DoS Hulk, DoS GoldenEye, DoS slowloris, DoS Slowhttptest | DoS |
| DDoS | DDoS |
| PortScan | PortScan |
| FTP-Patator, SSH-Patator | BruteForce |
| Web Attack – Brute Force / XSS / Sql Injection | WebAttack |
| Bot | Bot |
| Infiltration | Infiltration |
| Heartbleed | Heartbleed |

Unknown labels (e.g. "– Attempted" labels of corrected re-releases) are rejected until the mapping is extended
explicitly with a new mapping version.

## Known quality issues and limitations
* Labelling and flow-construction errors have been documented (Engelen, Rimmer, Joosen, "Troubleshooting an
  Intrusion Detection Dataset: the CICIDS2017 Case Study", IEEE S&P Workshops 2021). Treat reported scores as
  upper bounds.
* Large numbers of exact duplicates; `Infinity`/`NaN` in rate features; several constant columns.
* Extreme imbalance: Heartbleed, Infiltration and SQL injection have very few rows.
* Destination port and initial window sizes can act as lab-specific shortcuts (ablation in notebook 03).
* Traffic is synthetic lab traffic from 2017; it does not represent current enterprise traffic.
