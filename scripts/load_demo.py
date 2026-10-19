"""Feed the photos in demo_photos/ into a running TownshipFix, like real residents would.

    python run.py                                   # in one terminal
    python scripts/load_demo.py                     # in another: reports only
    python scripts/load_demo.py --complete          # also assigns and submits after.jpg
    python scripts/load_demo.py demo_photos/_synthetic --complete

Each folder becomes one problem. Every before_*.jpg is sent as a separate resident
report, so you can watch duplicates being grouped on the staff dashboard.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
IMG = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_TEXT = {
    "streetlight": ["Lampu jalan rosak, gelap waktu malam", "Streetlight not working here", "lamp post broken"],
    "road_damage": ["Jalan berlubang, bahaya untuk motosikal", "big pothole on the road", "pothole near the school"],
    "waste_bin": ["Tong sampah penuh dan melimpah", "rubbish bin overflowing", "sampah bersepah"],
    "walkway": ["Jubin kaki lima pecah, warga emas tersandung", "broken tiles on the walkway", "pavement damaged"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "demo_photos"))
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--pin", default="1234")
    ap.add_argument("--complete", action="store_true", help="assign each ticket and submit after.jpg")
    ap.add_argument("--insecure", action="store_true", help="accept the self-signed cert from run.py --https")
    args = ap.parse_args()
    s = requests.Session()
    s.verify = not args.insecure
    folder = Path(args.folder)
    cases = [d for d in sorted(folder.iterdir()) if d.is_dir() and not d.name.startswith("_")] \
        if folder.name != "_synthetic" else sorted(d for d in folder.iterdir() if d.is_dir())
    if not cases:
        print(f"No problem folders in {folder}. See demo_photos/README.md")
        return 1
    for d in cases:
        meta = json.loads((d / "case.json").read_text()) if (d / "case.json").exists() else {}
        befores = sorted(p for p in d.iterdir() if p.suffix.lower() in IMG and p.stem.lower().startswith("before"))
        texts = meta.get("texts") or DEFAULT_TEXT.get(meta.get("category"), [meta.get("note", "")])
        code = None
        for i, p in enumerate(befores):
            with open(p, "rb") as f:
                up = s.post(f"{args.server}/api/photos", files={"photo": (p.name, f)}).json()
            if "error" in up:
                print(f"  {p}: {up['error']}")
                continue
            gps = up.get("gps") or {}
            body = {"photo_ref": up["ref"], "text": texts[i % len(texts)], "category": meta.get("category"),
                    "lang": "ms" if i % 2 == 0 else "en", "landmark": meta.get("landmark"),
                    "lat": gps.get("lat", meta.get("lat")), "lng": gps.get("lng", meta.get("lng")),
                    "location_source": "photo_gps" if gps else "zone", "zone": meta.get("zone"),
                    "client_duration_ms": 35000 + i * 4000}
            r = s.post(f"{args.server}/api/reports", json=body)
            if r.status_code != 201:
                print(f"  {p}: {r.json().get('error')}")
                continue
            r = r.json()
            code = r["ticket"]["code"]
            print(f"{d.name}/{p.name} -> {code} {'(merged)' if r['merged'] else '(new)'}: {r['explanation']}")
            time.sleep(0.2)
        after = next((p for p in sorted(d.iterdir()) if p.stem.lower().startswith("after") and p.suffix.lower() in IMG), None)
        if args.complete and code and after:
            h = {"X-Staff-Pin": args.pin}
            s.post(f"{args.server}/api/staff/tickets/{code}/assign", json={"assignee": "Demo crew"}, headers=h)
            with open(after, "rb") as f:
                res = s.post(f"{args.server}/api/staff/tickets/{code}/complete", files={"photo": (after.name, f)},
                             headers=h).json()
            if "result" in res:
                print(f"   repair photo for {code}: {res['result']['summary']}")
            else:
                print(f"   repair photo for {code}: {res.get('error')}")
    print(f"\nOpen {args.server}/staff (PIN {args.pin}) to see the result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
