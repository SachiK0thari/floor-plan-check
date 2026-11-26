"""Train and evaluate the floor-plan segmentation model on CubiCasa5K masks.

Input is the output of ``cubicasa_prep.py``. The model predicts five classes per pixel
(specification §8.1): background, wall, door, window and room interior. Railings and outdoor
spaces count as background. Doors and windows take precedence over the wall they sit in.

The network is a U-Net with an ImageNet-pretrained ResNet-34 encoder (torchvision). It trains
on random crops with scale, flip and 90° rotation augmentation, keeps the checkpoint with the
best validation mean IoU over the four foreground classes, then:

1. fits a temperature on the validation split (calibration, specification §8.1 step 2);
2. evaluates the test split at the stored resolution: per-class IoU, pixel accuracy, and the
   expected calibration error before and after temperature scaling, with reliability-diagram
   bins;
3. writes ``metrics.json``, ``per_image_test.jsonl``, ``reliability.png`` and overlays of the
   test plans with the lowest wall IoU.

Self-contained (torch, torchvision, numpy, Pillow; matplotlib optional) so it runs unchanged as
a Kaggle script. A wall-clock budget stops training early enough to evaluate before Kaggle's
12-hour limit.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset

CLASSES = ("background", "wall", "door", "window", "room")
BACKGROUND, WALL, DOOR, WINDOW, ROOM = range(5)
FOREGROUND = (WALL, DOOR, WINDOW, ROOM)
IGNORE = 255
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Values written by cubicasa_prep.py
ROOM_WALL, ROOM_RAILING = 1, 2
ICON_DOOR, ICON_WINDOW = 1, 2


# ---------------------------------------------------------------------------
# Labels and data
# ---------------------------------------------------------------------------


def label_tables(vocab: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Lookup tables from the room and icon mask values to the five training classes.

    The icon table holds IGNORE where the icon mask does not override the room class.
    Every space whose type starts with "Outdoor" (balcony, terrace, porch, ...) is background.
    """
    room = np.full(256, BACKGROUND, dtype=np.uint8)
    room[ROOM_WALL] = WALL
    for key, name in vocab["room"].items():
        if not name.startswith("space:"):
            continue
        if name.removeprefix("space:").split()[0] != "Outdoor":
            room[int(key)] = ROOM
    icon = np.full(256, IGNORE, dtype=np.uint8)
    icon[ICON_DOOR] = DOOR
    icon[ICON_WINDOW] = WINDOW
    return room, icon


def to_target(
    room: np.ndarray, icon: np.ndarray, tables: tuple[np.ndarray, np.ndarray]
) -> np.ndarray:
    target = tables[0][room]
    over = tables[1][icon]
    keep = over != IGNORE
    target[keep] = over[keep]
    return target


def load_index(masks: Path, split: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (masks / "index.jsonl").read_text().splitlines()]
    return [r for r in rows if r["split"] == split]


def load_plan(
    masks: Path, pid: str, tables: tuple[np.ndarray, np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    image = np.asarray(Image.open(masks / "images" / f"{pid}.png").convert("RGB"))
    room = np.asarray(Image.open(masks / "room" / f"{pid}.png"))
    icon = np.asarray(Image.open(masks / "icon" / f"{pid}.png"))
    return image, to_target(room, icon, tables)


def normalize(image: np.ndarray) -> torch.Tensor:
    x = (image.astype(np.float32) / 255.0 - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1).copy())


class CropDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Random augmented crops; ``crops`` crops per decoded plan to spread the PNG decode cost."""

    def __init__(
        self,
        masks: Path,
        rows: list[dict[str, Any]],
        tables: tuple[np.ndarray, np.ndarray],
        crop: int,
        crops: int,
        scale_range: tuple[float, float] = (0.6, 1.25),
    ) -> None:
        self.masks, self.rows, self.tables = masks, rows, tables
        self.crop, self.crops, self.scale_range = crop, crops, scale_range

    def __len__(self) -> int:
        return len(self.rows)

    def _one(self, image: np.ndarray, target: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
        h, w = target.shape
        s = math.exp(random.uniform(*map(math.log, self.scale_range)))
        side = max(8, round(self.crop / s))
        y0 = random.randint(0, max(0, h - side))
        x0 = random.randint(0, max(0, w - side))
        img = np.full((side, side, 3), 255, dtype=np.uint8)
        tgt = np.full((side, side), IGNORE, dtype=np.uint8)
        part_i = image[y0 : y0 + side, x0 : x0 + side]
        part_t = target[y0 : y0 + side, x0 : x0 + side]
        img[: part_i.shape[0], : part_i.shape[1]] = part_i
        tgt[: part_t.shape[0], : part_t.shape[1]] = part_t
        if side != self.crop:
            img = np.asarray(
                Image.fromarray(img).resize((self.crop, self.crop), Image.Resampling.BILINEAR)
            )
            tgt = np.asarray(
                Image.fromarray(tgt).resize((self.crop, self.crop), Image.Resampling.NEAREST)
            )
        k = random.randint(0, 3)
        img, tgt = np.rot90(img, k), np.rot90(tgt, k)
        if random.random() < 0.5:
            img, tgt = img[:, ::-1], tgt[:, ::-1]
        return normalize(img), torch.from_numpy(tgt.astype(np.int64))

    def __getitem__(self, i: int) -> tuple[torch.Tensor, torch.Tensor]:
        image, target = load_plan(self.masks, self.rows[i]["id"], self.tables)
        pairs = [self._one(image, target) for _ in range(self.crops)]
        return torch.stack([p[0] for p in pairs]), torch.stack([p[1] for p in pairs])


def collate(batch: list[tuple[torch.Tensor, torch.Tensor]]) -> tuple[torch.Tensor, torch.Tensor]:
    return torch.cat([b[0] for b in batch]), torch.cat([b[1] for b in batch])


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class Block(nn.Sequential):
    def __init__(self, cin: int, cout: int) -> None:
        super().__init__(
            nn.Conv2d(cin, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
            nn.Conv2d(cout, cout, 3, padding=1, bias=False),
            nn.BatchNorm2d(cout),
            nn.ReLU(inplace=True),
        )


class UNet(nn.Module):
    """U-Net decoder on a torchvision ResNet-34 encoder."""

    def __init__(self, classes: int, pretrained: bool) -> None:
        super().__init__()
        from torchvision.models import ResNet34_Weights, resnet34

        enc = resnet34(weights=ResNet34_Weights.IMAGENET1K_V1 if pretrained else None)
        self.stem = nn.Sequential(enc.conv1, enc.bn1, enc.relu)  # /2, 64
        self.pool = enc.maxpool
        self.layers = nn.ModuleList([enc.layer1, enc.layer2, enc.layer3, enc.layer4])
        skips = (256, 128, 64, 64)  # layer3, layer2, layer1, stem
        widths = (256, 128, 64, 32, 16)
        cin = 512
        self.decoder = nn.ModuleList()
        for i, cout in enumerate(widths):
            skip = skips[i] if i < len(skips) else 0
            self.decoder.append(Block(cin + skip, cout))
            cin = cout
        self.head = nn.Conv2d(cin, classes, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        s0 = self.stem(x)
        f = self.pool(s0)
        feats = []
        for layer in self.layers:
            f = layer(f)
            feats.append(f)
        skips = [feats[2], feats[1], feats[0], s0]
        y = feats[3]
        for i, block in enumerate(self.decoder):
            y = F.interpolate(y, scale_factor=2, mode="nearest")
            if i < len(skips):
                y = torch.cat([y, skips[i]], dim=1)
            y = block(y)
        return self.head(y)


def dice_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    valid = (target != IGNORE).unsqueeze(1)
    prob = logits.float().softmax(1) * valid
    onehot = F.one_hot(target.clamp(max=len(CLASSES) - 1), len(CLASSES)).permute(0, 3, 1, 2)
    onehot = onehot * valid
    inter = (prob * onehot).sum((0, 2, 3))
    denom = prob.sum((0, 2, 3)) + onehot.sum((0, 2, 3))
    return 1 - ((2 * inter + 1) / (denom + 1)).mean()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@torch.no_grad()
def predict_logits(model: nn.Module, image: np.ndarray, device: torch.device) -> torch.Tensor:
    """Logits (C, H, W) for a whole plan, padded to a multiple of 32 and cropped back."""
    h, w = image.shape[:2]
    padded = np.pad(image, ((0, (-h) % 32), (0, (-w) % 32), (0, 0)), constant_values=255)
    x = normalize(padded).unsqueeze(0).to(device)
    with torch.autocast(device.type, enabled=device.type == "cuda"):
        y = model(x)
    return y[0, :, :h, :w].float()


def confusion(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    keep = target != IGNORE
    n = len(CLASSES)
    idx = target[keep] * n + pred[keep]
    return torch.bincount(idx, minlength=n * n).reshape(n, n).cpu()


def iou_from(conf: torch.Tensor) -> list[float | None]:
    tp = conf.diag().double()
    union = conf.sum(0).double() + conf.sum(1).double() - tp
    return [float(t / u) if u > 0 else None for t, u in zip(tp, union, strict=True)]


def mean_foreground(ious: list[float | None]) -> float:
    vals = [v for c in FOREGROUND if (v := ious[c]) is not None]
    return sum(vals) / len(vals) if vals else 0.0


def ece_bins(
    conf: torch.Tensor, correct: torch.Tensor, bins: int = 15
) -> tuple[float, list[dict[str, float]]]:
    edges = torch.linspace(0, 1, bins + 1)
    total = len(conf)
    ece = 0.0
    rows = []
    for lo, hi in itertools.pairwise(edges):
        m = (conf > lo) & (conf <= hi)
        n = int(m.sum())
        if n == 0:
            rows.append(
                {"lo": float(lo), "hi": float(hi), "count": 0, "confidence": 0.0, "accuracy": 0.0}
            )
            continue
        c, a = float(conf[m].mean()), float(correct[m].float().mean())
        ece += n / total * abs(c - a)
        rows.append({"lo": float(lo), "hi": float(hi), "count": n, "confidence": c, "accuracy": a})
    return ece, rows


def evaluate(
    model: nn.Module,
    masks: Path,
    rows: list[dict[str, Any]],
    tables: tuple[np.ndarray, np.ndarray],
    device: torch.device,
    sample_pixels: int = 0,
) -> dict[str, Any]:
    """Confusion matrix over a split; optionally a random pixel sample of logits and labels."""
    model.eval()
    total = torch.zeros(len(CLASSES), len(CLASSES), dtype=torch.long)
    per_image = []
    logits_s, labels_s = [], []
    gen = torch.Generator().manual_seed(0)
    for row in rows:
        image, target_np = load_plan(masks, row["id"], tables)
        logits = predict_logits(model, image, device)
        target = torch.from_numpy(target_np.astype(np.int64)).to(device)
        conf = confusion(logits.argmax(0), target)
        total += conf
        per_image.append({"id": row["id"], "iou": dict(zip(CLASSES, iou_from(conf), strict=True))})
        if sample_pixels:
            flat_t = target.flatten()
            valid = (flat_t != IGNORE).nonzero().flatten().cpu()
            if len(valid):
                pick = valid[
                    torch.randint(len(valid), (min(sample_pixels, len(valid)),), generator=gen)
                ]
                pick = pick.to(device)
                logits_s.append(logits.flatten(1)[:, pick].T.cpu())
                labels_s.append(flat_t[pick].cpu())
    ious = iou_from(total)
    out: dict[str, Any] = {
        "confusion": total.tolist(),
        "iou": dict(zip(CLASSES, ious, strict=True)),
        "mean_iou_foreground": mean_foreground(ious),
        "pixel_accuracy": float(total.diag().sum() / total.sum()),
        "plans": len(rows),
        "per_image": per_image,
    }
    if sample_pixels:
        out["sample_logits"] = torch.cat(logits_s)
        out["sample_labels"] = torch.cat(labels_s)
    return out


def fit_temperature(logits: torch.Tensor, labels: torch.Tensor) -> float:
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure() -> torch.Tensor:
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), labels)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp())


def calibration(logits: torch.Tensor, labels: torch.Tensor, temperature: float) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, t in (("raw", 1.0), ("scaled", temperature)):
        prob = (logits / t).softmax(1)
        conf, pred = prob.max(1)
        ece, bins = ece_bins(conf, pred == labels)
        nll = float(F.cross_entropy(logits / t, labels))
        result[name] = {"ece": ece, "nll": nll, "bins": bins}
    result["pixels"] = len(labels)
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

PALETTE = np.array(
    [[255, 255, 255], [200, 30, 30], [30, 160, 30], [30, 60, 220], [235, 210, 120]], dtype=np.uint8
)


def save_overlay(
    path: Path, image: np.ndarray, target: np.ndarray, pred: np.ndarray, width: int = 1600
) -> None:
    t = PALETTE[np.where(target == IGNORE, 0, target)]
    p = PALETTE[pred]
    strip = np.concatenate([image, t, p], axis=1)
    im = Image.fromarray(strip)
    im.thumbnail((width * 3, width))
    im.save(path)


def save_reliability(path: Path, calib: dict[str, Any]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], color="0.6", lw=1, label="perfect calibration")
    for name, style in (("raw", "o-"), ("scaled", "s-")):
        bins = [b for b in calib[name]["bins"] if b["count"]]
        ax.plot(
            [b["confidence"] for b in bins],
            [b["accuracy"] for b in bins],
            style,
            ms=4,
            label=f"{name} (ECE {calib[name]['ece']:.4f})",
        )
    ax.set_xlabel("confidence")
    ax.set_ylabel("accuracy")
    ax.set_title(f"Test pixels, n = {calib['pixels']:,}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def memory_gb() -> dict[str, float]:
    """Host memory available and this process's resident size, where Linux reports them."""
    out: dict[str, float] = {}
    for path, key, name in (
        ("/proc/meminfo", "MemAvailable:", "available_gb"),
        ("/proc/self/status", "VmRSS:", "rss_gb"),
    ):
        try:
            for line in Path(path).read_text().splitlines():
                if line.startswith(key):
                    out[name] = round(int(line.split()[1]) / 2**20, 2)  # kB to GiB
        except OSError:
            pass
    return out


def fast_forward(sched: torch.optim.lr_scheduler.LRScheduler, steps: int) -> None:
    """Advance a schedule without optimizer steps (resuming from weights only)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # "scheduler.step() before optimizer.step()"
        for _ in range(steps):
            sched.step()


def kaggle_masks() -> Path:
    """Extract the prep kernel's archive to scratch space and return the masks folder."""
    archives = sorted(Path("/kaggle/input").rglob("cubicasa_masks.tar"))
    if not archives:
        raise FileNotFoundError("cubicasa_masks.tar not found under /kaggle/input")
    dest = Path("/kaggle/temp")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archives[0]) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python without extraction filters
            tar.extractall(dest)
    return dest / "cubicasa_masks"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate the segmentation model.")
    parser.add_argument("--masks", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--kaggle", action="store_true", help="use Kaggle input and output paths")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch", type=int, default=8, help="plans per step (x --crops crops)")
    parser.add_argument("--crops", type=int, default=2)
    parser.add_argument("--crop", type=int, default=512)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--hours", type=float, default=10.0, help="stop training after this long")
    parser.add_argument("--val-every", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="plans per split (smoke test)")
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--resume",
        type=Path,
        help="continue from a model_last.pt; run with the same schedule arguments as before",
    )
    args = parser.parse_args(argv)

    start = time.time()
    if args.kaggle:
        args.masks = args.masks or kaggle_masks()
        args.out = args.out or Path("/kaggle/working")
    if args.masks is None or args.out is None:
        parser.error("--masks and --out are required without --kaggle")
    args.out.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vocab = json.loads((args.masks / "vocab.json").read_text())
    tables = label_tables(vocab)
    splits = {s: load_index(args.masks, s) for s in ("train", "val", "test")}
    if args.limit:
        splits = {s: r[: args.limit] for s, r in splits.items()}
    print(
        {s: len(r) for s, r in splits.items()},
        "device",
        device,
        torch.cuda.device_count(),
        "GPUs",
        flush=True,
    )

    model: nn.Module = UNet(len(CLASSES), pretrained=not args.no_pretrained).to(device)
    net = nn.DataParallel(model) if torch.cuda.device_count() > 1 else model
    loader = DataLoader(
        CropDataset(args.masks, splits["train"], tables, args.crop, args.crops),
        batch_size=args.batch,
        shuffle=True,
        num_workers=args.workers,
        collate_fn=collate,
        drop_last=True,
        # Known issue, cause not yet found: the main process grows by about 0.6 GB per epoch
        # on Kaggle (2 x T4, 4 workers) with or without persistent workers, so a 30 GB host
        # lasts about 45 epochs. Longer runs are split with --resume.
        persistent_workers=args.workers > 0,
        pin_memory=device.type == "cuda",
    )
    steps = max(1, args.epochs * len(loader))
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=steps, pct_start=0.05
    )
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    budget = args.hours * 3600

    history: list[dict[str, Any]] = []
    best = -1.0
    best_path = args.out / "model_best.pt"
    start_epoch = 1
    resumed: dict[str, Any] | None = None
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt["model"])
        start_epoch = int(ckpt["epoch"]) + 1
        if "optimizer" in ckpt:
            opt.load_state_dict(ckpt["optimizer"])
            sched.load_state_dict(ckpt["scheduler"])
            scaler.load_state_dict(ckpt["scaler"])
            if ckpt["scheduler"].get("total_steps") != steps:
                raise ValueError(
                    f"the checkpoint's schedule has {ckpt['scheduler'].get('total_steps')} steps "
                    f"and this run's has {steps}; resume with the original --epochs and --batch"
                )
            restored = "weights, optimizer, schedule and loss scaler"
        else:
            fast_forward(sched, min(steps, (start_epoch - 1) * len(loader)))
            restored = "weights only: fresh optimizer moments, schedule advanced to the epoch"
        best = ckpt.get("best")
        if best is None:  # older checkpoints do not record it; measure the loaded weights
            best = evaluate(model, args.masks, splits["val"], tables, device)["mean_iou_foreground"]
        torch.save(
            {"model": model.state_dict(), "epoch": start_epoch - 1, "classes": CLASSES}, best_path
        )
        resumed = {
            "from": str(args.resume),
            "after_epoch": start_epoch - 1,
            "restored": restored,
            "val_mean_iou_foreground": best,
        }
        print(json.dumps({"resumed": resumed, "memory": memory_gb()}), flush=True)
    epochs_done = start_epoch - 1
    stopped_early = False
    for epoch in range(start_epoch, args.epochs + 1):
        net.train()
        t0, total_loss, n = time.time(), 0.0, 0
        for x, y in loader:
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                logits = net(x)
                loss = F.cross_entropy(logits.float(), y, ignore_index=IGNORE) + dice_loss(
                    logits, y
                )
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total_loss += float(loss.detach())
            n += 1
        epochs_done = epoch
        record: dict[str, Any] = {
            "epoch": epoch,
            "loss": total_loss / max(n, 1),
            "seconds": time.time() - t0,
            "memory": memory_gb(),
        }
        last = epoch == args.epochs or time.time() - start > budget
        if epoch % args.val_every == 0 or last:
            val = evaluate(model, args.masks, splits["val"], tables, device)
            record["val_iou"] = val["iou"]
            record["val_mean_iou_foreground"] = val["mean_iou_foreground"]
            if val["mean_iou_foreground"] > best:
                best = val["mean_iou_foreground"]
                torch.save(
                    {"model": model.state_dict(), "epoch": epoch, "classes": CLASSES}, best_path
                )
                record["best"] = True
        history.append(record)
        print(json.dumps(record), flush=True)
        torch.save(
            {
                "model": model.state_dict(),
                "epoch": epoch,
                "best": best,
                "optimizer": opt.state_dict(),
                "scheduler": sched.state_dict(),
                "scaler": scaler.state_dict(),
            },
            args.out / "model_last.pt",
        )
        if time.time() - start > budget and epoch < args.epochs:
            stopped_early = True
            print(f"time budget reached after epoch {epoch}", flush=True)
            break

    model.load_state_dict(torch.load(best_path, map_location=device)["model"])
    val = evaluate(model, args.masks, splits["val"], tables, device, sample_pixels=20_000)
    temperature = fit_temperature(val["sample_logits"], val["sample_labels"])
    test = evaluate(model, args.masks, splits["test"], tables, device, sample_pixels=20_000)
    calib = calibration(test["sample_logits"], test["sample_labels"], temperature)
    save_reliability(args.out / "reliability.png", calib)

    with (args.out / "per_image_test.jsonl").open("w") as fh:
        for row in test["per_image"]:
            fh.write(json.dumps(row) + "\n")
    worst = sorted(
        (r for r in test["per_image"] if r["iou"]["wall"] is not None),
        key=lambda r: r["iou"]["wall"],
    )[:6]
    (args.out / "failures").mkdir(exist_ok=True)
    for r in worst:
        image, target = load_plan(args.masks, r["id"], tables)
        pred = predict_logits(model, image, device).argmax(0).cpu().numpy().astype(np.uint8)
        save_overlay(args.out / "failures" / f"{r['id']}.png", image, target, pred)

    source = Path(__file__).read_bytes() if Path(__file__).is_file() else b""
    metrics = {
        "classes": CLASSES,
        "label_rules": (
            "railing and outdoor spaces are background; doors and windows override walls"
        ),
        "test": {
            k: test[k]
            for k in ("iou", "mean_iou_foreground", "pixel_accuracy", "plans", "confusion")
        },
        "val": {k: val[k] for k in ("iou", "mean_iou_foreground", "pixel_accuracy", "plans")},
        "temperature": temperature,
        "calibration_test": calib,
        "best_epoch": torch.load(best_path, map_location="cpu")["epoch"],
        "epochs_done": epochs_done,
        "stopped_early": stopped_early,
        "resumed": resumed,
        "history": history,
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "evaluation_resolution": "stored masks: long side at most the prep --max-side",
        "environment": {
            "torch": torch.__version__,
            "cuda_devices": [
                torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())
            ],
        },
        "script_sha256": hashlib.sha256(source).hexdigest(),
        "wall_clock_hours": (time.time() - start) / 3600,
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: metrics[k] for k in ("test", "temperature")}, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
