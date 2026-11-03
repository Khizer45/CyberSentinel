# Dataset card — UNSW-NB15 (`unsw-nb15-flow-v1`)

| Field | Value |
|---|---|
| Publisher | UNSW Canberra Cyber Range Lab |
| Citation | N. Moustafa, J. Slay, "UNSW-NB15: a comprehensive data set for network intrusion detection systems", MilCIS 2015 |
| Files used | official partition: `UNSW_NB15_training-set.csv` (175,341 rows) and `UNSW_NB15_testing-set.csv` (82,332 rows) |
| Collection | IXIA PerfectStorm traffic generator; features from Argus/Bro-IDS |
| Licence | Research use with citation (check the UNSW website for current terms) |

## Schema handling
* 42 features: 39 numeric + categorical `proto`, `service` (`-` = none), `state`. `id` is a row identifier and is
  dropped. Targets: `attack_cat` (multi-class) and `label` (binary, checked for consistency).
* The publisher's testing partition is kept as the test set; validation is a stratified 15 % of the training
  partition.
* The raw four-file release (49 columns, no header, ~2.5 M rows) uses different names and lacks `rate`; it is
  not accepted as model input (exploration only).

## Labels (`unsw-nb15-labels-v1`)
`Normal → Benign`; `Generic`, `Exploits`, `Fuzzers`, `DoS`, `Reconnaissance`, `Analysis`, `Backdoor`
(`Backdoors` unified), `Shellcode`, `Worms`. Stray whitespace is removed. Empty `attack_cat` is accepted only
when `label = 0`.

## Known quality issues and limitations
* TTL-derived features (`sttl`, `dttl`, `ct_state_ttl`) are known to separate classes through generator artefacts;
  run the shortcut ablation before drawing conclusions.
* Strong class imbalance (`Worms`, `Shellcode`, `Analysis`, `Backdoor` are small).
* Synthetic traffic from 2015; cross-dataset generalization to CIC-IDS2017 (or real networks) is not established
  and the two schemas are deliberately not merged.
