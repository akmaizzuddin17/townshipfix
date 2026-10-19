# Photos for TownshipFix

This folder is where real photos go. The app already works with generated test
images, but **real photos from a real township are what will convince the judges**.

## How to add photos (no coding needed)

1. On GitHub, open this `demo_photos` folder.
2. Click **Add file → Upload files**.
3. Drag in your photos **inside a folder per problem**. GitHub creates the folder
   if you type it in front of the file name, for example
   `case1_streetlight_block_c/before_1.jpg`.
4. Click **Commit changes**. GitHub then checks the photos automatically
   (Actions tab → "Check photos") and writes a short report.

## What to photograph (one folder per problem)

| File | What it shows | How to take it |
|------|---------------|----------------|
| `before_1.jpg` | The problem, as resident 1 would snap it | Normal phone photo, problem in the middle |
| `before_2.jpg` | Same problem, as resident 2 | Step 1 to 2 metres sideways, slightly different angle |
| `before_3.jpg` | Same problem, as resident 3 | Another angle or a bit closer / further |
| `after.jpg` | The same spot after it was fixed (or cleaned / tidied) | Stand roughly where `before_1` was taken |
| `case.json` *(optional)* | Category and location if photos have no GPS | See example below |

**Aim for 4 to 6 problems.** A good mix:

- A **streetlight** that is off (before at dusk) and on (after). Easy "after" photo.
- An **overflowing bin** before and after collection.
- A **blocked ramp or walkway** (e.g. motorbike on the OKU ramp) and the same spot cleared.
- A **pothole or broken tiles** (an after photo is only possible if it was repaired; skip `after.jpg` if not).
- A **second similar problem nearby**, e.g. a different broken lamp 20–50 m away.
  This proves the AI does *not* wrongly merge two different problems.

## Tips that matter

- **Turn on location for the camera** (iPhone: Settings → Privacy → Location Services → Camera → While Using;
  Android: camera settings → Save location). The app reads the GPS from the photo.
- **Send the original files.** WhatsApp and Telegram strip GPS and shrink photos.
  Upload straight from the phone's gallery or via Google Drive / AirDrop.
- Keep **faces and car plates out of frame** where you can. The app blurs them when
  the detector is installed, but it is better not to capture them.
- Daylight is best. If before and after are at very different times of day, that is fine,
  but avoid one photo at night and the other at noon.
- JPG or PNG, under 15 MB each. Screenshots of photos will not have GPS.

## `case.json` example (only needed if your photos have no GPS)

```json
{
  "category": "streetlight",
  "lat": 3.07210,
  "lng": 101.51820,
  "landmark": "Jalan 2, near Block C",
  "texts": ["Lampu jalan rosak, gelap waktu malam", "Streetlight not working", "lamp post broken"]
}
```

`category` is one of: `electrical`, `streetlight`, `road_damage`, `walkway`, `accessibility`, `drain`,
`water_leak`, `waste_bin`, `tree`, `playground`, `vandalism`, `other`.
Get `lat`/`lng` by long-pressing the spot in Google Maps.

## Using the photos

```bash
python scripts/evaluate_images.py            # how well does the AI do on these photos? suggests settings
python run.py                                 # start the app
python scripts/load_demo.py --complete        # send them in like real residents, then submit the repair
```

The `_synthetic` folder (created by `python scripts/synthetic_photos.py`) holds generated
test scenes. They are not real photos and are not uploaded to GitHub.
