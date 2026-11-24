# Training (milestone M3)

The segmentation model is trained on [CubiCasa5K](https://zenodo.org/records/2613548)
(Kalervo et al., 2019; CC BY-NC-SA 4.0, see [data sources](../docs/data_sources.md)). Runs happen
on Kaggle's free GPU tier, inside the author's Kaggle account; no dataset file, mask or weight
file is stored in this repository.

| File | What it does |
|---|---|
| `cubicasa_prep.py` | Converts every `model.svg` into a room mask and an icon mask, resizes each plan to a long side of at most 2048 px, and writes `index.jsonl` (split, source, original size, scale) and `vocab.json` (label ids and counts). |
| `train_seg.py` | Trains a U-Net with a ResNet-34 encoder on five classes (background, wall, door, window, room), fits a temperature on the validation split, and evaluates the test split: per-class IoU, pixel accuracy, calibration error before and after scaling, a reliability diagram and the worst plans by wall IoU. |
| `kaggle_push.py` | Uploads one of the two scripts to Kaggle as a private kernel and starts it. |

Both scripts are self-contained so they run unchanged on Kaggle. `kaggle_push.py` replaces only
their final `__main__` block with a driver that supplies Kaggle's paths.

## Running

One-time setup: a Kaggle account with phone verification, the `kaggle` command-line tool
(`uv tool install kaggle`), and an API token in `~/.kaggle/access_token`.

```bash
uv run python -m training.kaggle_push prep --owner <kaggle-user>   # CPU, ~1 h; writes cubicasa_masks.tar
uv run python -m training.kaggle_push train --owner <kaggle-user>  # T4 GPU, stops within 10 h
kaggle kernels status <kaggle-user>/plancheck-seg-train
kaggle kernels output <kaggle-user>/plancheck-seg-train -p <dir>   # metrics.json, reliability.png, failures/
```

The training kernel reads the prep kernel's latest output. Each training run uses GPU quota for
its whole duration (about 30 hours a week are available).

## Labels

- Room mask: 0 background, 1 wall, 2 railing, 3 and up a space type from `vocab.json`.
- Icon mask: 0 none, 1 door, 2 window, 3 and up a fixed-furniture type from `vocab.json`.
- Training classes: railings and outdoor spaces are background; any other space is room; doors and
  windows override the wall they sit in.

The full room and furniture vocabularies are kept so that a later run can use CubiCasa's own
class set, which is what the published baseline reports.
