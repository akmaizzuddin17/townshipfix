"""Check how well the photo AI works on YOUR photos, and suggest better settings.

Put photos in demo_photos/<one folder per problem>/ (see demo_photos/README.md), then:

    python scripts/evaluate_images.py                  # uses demo_photos/
    python scripts/evaluate_images.py demo_photos/_synthetic
    python scripts/evaluate_images.py --report docs/evaluation_report.md

It tests three things with the current settings in app/config.py:
  1. Duplicates   - photos of the same problem should match; different problems should not
  2. Fix accepted - the after photo should pass verification against each before photo
  3. Fakes caught - an unrepaired photo, or an after photo from another problem, must fail
and prints suggested thresholds based on your photos.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.services import vision  # noqa: E402

IMG = {".jpg", ".jpeg", ".png", ".webp"}


def load(path):
    data = path.read_bytes()
    im = vision.to_cv(vision.load_pil(data))
    return {"path": path, "img": im, "feat": vision.compute_features(im), "exif": vision.exif_info(data)}


def collect(folder: Path):
    cases = {}
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        if d.name.startswith("_"):
            continue  # e.g. _synthetic: run it by passing that folder directly
        files = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG)
        before = [p for p in files if p.stem.lower().startswith("before")]
        after = [p for p in files if p.stem.lower().startswith("after")]
        if before:
            meta = json.loads((d / "case.json").read_text()) if (d / "case.json").exists() else {}
            cases[d.name] = {"before": [load(p) for p in before], "after": [load(p) for p in after], "meta": meta}
    return cases


def verify_pair(before, after):
    sim = vision.photo_similarity(after["feat"], before["feat"])
    frac, _ = vision.change_fraction(before["img"], after["img"], before["feat"], after["feat"])
    identical = sim["dhash"] >= 0.98 and sim["hist"] >= 0.98
    ok = (sim["geom"] >= config.VERIFY_MIN_SCENE and frac is not None
          and config.VERIFY_MIN_CHANGE <= frac <= config.VERIFY_MAX_CHANGE and not identical)
    return ok, sim["geom"], frac


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "demo_photos"))
    ap.add_argument("--report", help="also write a Markdown report to this file")
    args = ap.parse_args()
    folder = Path(args.folder)
    cases = collect(folder)
    lines = [f"# Photo AI check: {folder}", ""]
    if not cases:
        print(f"No problem folders with before_*.jpg found in {folder}. See demo_photos/README.md")
        return 1
    lines.append(f"{len(cases)} problems, {sum(len(c['before']) for c in cases.values())} before photos, "
                 f"{sum(len(c['after']) for c in cases.values())} after photos.\n")

    # 1. duplicates
    same, diff = [], []
    for name, c in cases.items():
        for a, b in itertools.combinations(c["before"], 2):
            same.append((vision.photo_similarity(a["feat"], b["feat"])["score"], name, a["path"].name, b["path"].name))
    names = list(cases)
    for x, y in itertools.combinations(names, 2):
        for a in cases[x]["before"]:
            for b in cases[y]["before"]:
                diff.append((vision.photo_similarity(a["feat"], b["feat"])["score"], f"{x} vs {y}", a["path"].name, b["path"].name))
    # the merge decision also uses distance + category; here we judge the photo signal alone
    photo_thr = config.DEDUP_STRONG_IMAGE
    lines += ["## 1. Do photos of the same problem match?", ""]
    if same:
        ok = sum(s >= 0.5 for s, *_ in same)
        lines.append(f"- Same-problem pairs scoring 0.50 or more: {ok}/{len(same)} ({pct(ok, len(same))})")
        lines.append(f"- Lowest same-problem score: {min(s for s, *_ in same):.2f}  "
                     f"(alone >= {photo_thr:.2f} merges even if the category was tapped wrong)")
    else:
        lines.append("- Add 2 or more before photos per problem to test this.")
    if diff:
        bad = sorted(diff, reverse=True)[:3]
        lines.append(f"- Different-problem pairs scoring 0.50 or more: {sum(s >= 0.5 for s, *_ in diff)}/{len(diff)}")
        lines.append(f"- Highest different-problem score: {bad[0][0]:.2f} ({bad[0][1]}: {bad[0][2]} / {bad[0][3]})")
    weak = [x for x in same if x[0] < 0.5]
    for s, n, a, b in sorted(weak)[:5]:
        lines.append(f"  - weak match {s:.2f} in {n}: {a} / {b} (try standing closer to where the first photo was taken)")
    lines.append("")

    # 2 + 3. verification
    lines += ["## 2. Is a real repair accepted?", ""]
    pos, neg_same, neg_other = [], [], []
    for name, c in cases.items():
        for af in c["after"]:
            for bf in c["before"]:
                pos.append((name, bf["path"].name, *verify_pair(bf, af)))
        for a, b in itertools.combinations(c["before"], 2):
            neg_same.append((name, *verify_pair(a, b)))
        for other, oc in cases.items():
            if other != name:
                for af in oc["after"]:
                    neg_other.append((f"{other} after vs {name}", *verify_pair(c["before"][0], af)))
    if pos:
        ok = sum(p[2] for p in pos)
        lines.append(f"- After photos accepted: {ok}/{len(pos)} ({pct(ok, len(pos))})")
        for name, bname, passed, g, f in pos:
            if not passed:
                lines.append(f"  - rejected: {name} after vs {bname}: scene {g:.2f}, change "
                             f"{'n/a' if f is None else f'{f:.3f}'}")
    else:
        lines.append("- Add after.jpg to a problem folder to test this.")
    lines += ["", "## 3. Are fake or wrong repair photos caught?", ""]
    if neg_same:
        caught = sum(not n[1] for n in neg_same)
        lines.append(f"- Unrepaired spot photographed again (should fail): caught {caught}/{len(neg_same)}")
    if neg_other:
        caught = sum(not n[1] for n in neg_other)
        lines.append(f"- After photo from a different problem (should fail): caught {caught}/{len(neg_other)}")
    lines.append("")

    # suggestions
    lines += ["## Suggested settings for app/config.py", ""]
    n_before = len(lines)
    pos_change = [f for *_, passed, g, f in pos if f is not None and g >= config.VERIFY_MIN_SCENE]
    neg_change = [f for _, _, g, f in neg_same if f is not None and g >= config.VERIFY_MIN_SCENE]
    if pos_change and neg_change:
        lo, hi = max(neg_change), min(pos_change)
        if lo < hi:
            lines.append(f"- VERIFY_MIN_CHANGE = {round((lo + hi) / 2, 4)}  (unrepaired max {lo:.4f}, repaired min {hi:.4f}; "
                         f"current {config.VERIFY_MIN_CHANGE})")
        else:
            lines.append(f"- Repaired and unrepaired photos overlap (unrepaired up to {lo:.4f}, repaired from {hi:.4f}). "
                         "Retake after photos from the same position as a before photo, in similar light.")
    pos_scene = [g for *_, g, f in pos]
    neg_scene = [g for _, _, g, f in neg_other]
    if pos_scene and neg_scene:
        lo, hi = max(neg_scene), min(pos_scene)
        if lo < hi:
            lines.append(f"- VERIFY_MIN_SCENE = {round((lo + hi) / 2, 2)}  (wrong place max {lo:.2f}, right place min {hi:.2f}; "
                         f"current {config.VERIFY_MIN_SCENE})")
        else:
            lines.append(f"- Some wrong-place photos look as similar as right-place ones (max {lo:.2f} vs min {hi:.2f}).")
    if len(lines) == n_before:
        lines.append("- Not enough photos yet to suggest values.")
    text = "\n".join(lines) + "\n"
    print(text)
    if args.report:
        Path(args.report).write_text(text)
        print(f"Report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
