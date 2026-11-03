# data — datasets (git-ignored)

Download the official files yourself (licences require citation; see the dataset cards in `docs/dataset_cards/`):

| Family | Place files in | Files |
|---|---|---|
| CIC-IDS2017 | `data/raw/cicids2017/` | the eight `MachineLearningCVE/*.pcap_ISCX.csv` files (the `TrafficLabelling` variant also works) |
| UNSW-NB15 | `data/raw/unsw_nb15/` | `UNSW_NB15_training-set.csv` and `UNSW_NB15_testing-set.csv` (official partition) |

`data/processed/<family>/` is written by `notebooks/02_preprocessing.ipynb` (Parquet splits, fitted preprocessor,
preprocessing report). Nothing under `data/` is committed.
