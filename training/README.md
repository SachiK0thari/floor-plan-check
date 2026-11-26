# Training (milestone M3)

The segmentation model is trained on [CubiCasa5K](https://zenodo.org/records/2613548)
(Kalervo et al., 2019; CC BY-NC-SA 4.0, see [data sources](../docs/data_sources.md)). Runs happen
on Kaggle's free GPU tier, inside the author's Kaggle account; no dataset file, mask or weight
file is stored in this repository.

| File | What it does |
|---|---|
| `cubicasa_prep.py` | Converts every `model.svg` into a room mask and an icon mask, resizes each plan to a long side of at most 2048 px, and writes `index.jsonl` (split, source, original size, scale) and `vocab.json` (label ids and counts). |
| `train_seg.py` | Trains a U-Net with a ResNet-34 encoder on five classes (background, wall, door, window, room), fits a temperature on the validation split, and evaluates the test split: per-class IoU, pixel accuracy, calibration error before and after scaling, a reliability diagram and the worst plans by wall IoU. |
| `kaggle_push.py` | Uploads one of the scripts to Kaggle as a private kernel and starts it: `prep`, `train`, or `resume` (continue a stopped training run). |

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
its whole duration (about 30 hours a week are available). Every epoch's log line records host
memory available and the process's resident size.

### Resuming a stopped run

`model_last.pt` is written after every epoch, with the optimizer, schedule and loss-scaler state
(checkpoints from before November 24, 2026 hold weights only; the schedule is then advanced to the
epoch and the optimizer starts fresh, which `metrics.json` records under `resumed`). Kaggle will
not attach the output of a run that ended in an error, so upload the checkpoint as a private
dataset first:

```bash
kaggle kernels output <kaggle-user>/plancheck-seg-train -p <dir>
# in <dir>: keep model_last.pt and add dataset-metadata.json with
#   "id": "<kaggle-user>/plancheck-seg-checkpoint", "licenses": [{"name": "CC-BY-NC-SA-4.0"}]
kaggle datasets create -p <dir>          # private unless --public is given
uv run python -m training.kaggle_push resume --owner <kaggle-user>
```

Resume with the original `--epochs` and `--batch`; a full checkpoint with a different schedule
length is refused. The checkpoint derives from CubiCasa5K, so the dataset stays private and is
licensed CC BY-NC-SA 4.0.

### Run log

- **November 24, 2026, first run.** 2 × T4, 4.3 min per epoch. Killed for memory during epoch 46
  of 60 after 3.3 h, before evaluation; validation mean foreground IoU had risen at every check, to
  0.800 at epoch 45.
- **November 24, 2026, resumed run** (epochs 46 to 60 from the epoch-45 weights, fresh optimizer
  state, 1.1 h). The memory log showed the main process growing by about 0.6 GB per epoch (3.7 GB
  after epoch 46, 11.9 GB after epoch 60) even with workers restarted every epoch, so restarting
  them was not the fix and was reverted; the cause is open. Best validation checkpoint: epoch 55
  (0.8015). Test split, 400 plans at the stored resolution:

  | | background | wall | door | window | room | mean of the four foreground classes |
  |---|---|---|---|---|---|---|
  | IoU | 0.926 | 0.792 | 0.699 | 0.788 | 0.914 | 0.798 |

  Pixel accuracy 0.951. Temperature 1.25, fitted on validation pixels; expected calibration error
  on 8 million sampled test pixels 0.0208 before scaling and 0.0060 after (negative
  log-likelihood 0.164 and 0.154). This is a pixel-level figure dominated by easy background pixels;
  per-class calibration of wall pixels has not been measured.

  Worst plans by wall IoU: a grey, noisy photocopy on which the model finds only fragments of walls
  (wall IoU 0.18), and plans whose room fill spills into hatched or dashed areas outside the
  building outline. The largest confusions are between room and background (12.1 million
  background pixels predicted room, 8.6 million the other way) and wall predicted as room (2.7
  million).

  For reference, the CubiCasa5K paper (Kalervo et al. 2019, Table 4, raw segmentation, test split)
  reports wall 0.730, door 0.536 and window 0.668. That is not a like-for-like comparison: the paper
  predicts 12 room and 11 icon classes with a multi-task network, and its wall class is not reduced
  by the openings inside it, whereas here doors and windows take those pixels.

## Labels

- Room mask: 0 background, 1 wall, 2 railing, 3 and up a space type from `vocab.json`.
- Icon mask: 0 none, 1 door, 2 window, 3 and up a fixed-furniture type from `vocab.json`.
- Training classes: railings and outdoor spaces are background; any other space is room; doors and
  windows override the wall they sit in.

The full room and furniture vocabularies are kept so that a later run can use CubiCasa's own
class set, which is what the published baseline reports.
