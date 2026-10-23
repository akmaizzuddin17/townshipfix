# TownshipFix

**Turn resident complaints into completed, verified repairs.**
Sime Darby Property University Hackathon 2026, PEOPLE track (Safety & Security, Digital Living, Accessibility & Inclusion).

Residents snap a photo or simply *say* what is broken, in Malay or English. TownshipFix:

1. **Groups duplicate reports.** Three neighbours photographing the same dark streetlight become one job, not three.
2. **Ranks jobs by impact on residents.** A ramp blocked for wheelchair users near a clinic outranks a full bin, and the score shows its reasons.
3. **Proves the fix.** A job only closes when the crew's *after* photo passes five checks and the resident confirms it (or doesn't object within 3 days).

![Architecture](docs/architecture.png)

![Report to repair](docs/flow.png)

## Run it (5 minutes)

**On Windows:** double-click **`Start TownshipFix.bat`**. It installs what's needed, starts the app over HTTPS and opens the resident app and staff dashboard (PIN `1234`). Run `git pull` first to get updates.

Needs Python 3.10 or newer.

```bash
git clone <this repo> && cd townshipfix
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

- Resident app: http://localhost:8000
- Staff dashboard: http://localhost:8000/staff (PIN `1234`)

### Dashboard map

The staff dashboard uses locally bundled Leaflet 1.9.4 with OpenStreetMap street tiles.
Priority-labelled pins open ticket summaries and resident photos; **View ticket & photos**
opens the full details. Scroll with two fingers on a trackpad, use a mouse wheel, or pinch with two
fingers on a phone to zoom. Drag the map to move, or use **Show all tickets** to return to the queue's locations.
Filtering updates the pins; background refreshes preserve the current map view.

Use **Streets / Satellite** above the map to switch between OpenStreetMap streets and
[Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9).
Switching preserves the map position, zoom, selected ticket and photos. The choice is remembered
for the current browser tab. Satellite imagery is not live and capture dates vary by location.
Leaflet remains open source; Esri imagery is a separately licensed hosted service. Review the
provider's published terms before deployment; tiles are fetched only for interactive viewing.
Set `TOWNSHIPFIX_MAP_SATELLITE_TILE_URL` and `TOWNSHIPFIX_MAP_SATELLITE_ATTRIBUTION`
to use a different licensed imagery provider. Attribution updates with the selected layer.

Street and satellite tiles need an internet connection. If they cannot load, ticket pins and the queue still work.
Sample township zones and demo report coordinates are illustrative.
For a different tile provider, set `TOWNSHIPFIX_MAP_TILE_URL` and
`TOWNSHIPFIX_MAP_ATTRIBUTION` (trusted attribution HTML) before starting the server.
Keep provider attribution visible. The default community service is for normal interactive viewing;
follow its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/), including no bulk
downloads or offline prefetching. For larger deployments, choose a suitable provider or self-host tiles.
The staff page sends only its origin in cross-site referrers; the resident app retains `no-referrer`.

**On a phone**, connect to the same Wi-Fi and run `python run.py --https`, then open the
`https://<laptop-ip>:8000` address it prints and accept the certificate warning.
Phones only allow the microphone and GPS on HTTPS pages.

### Fill it with demo data

```bash
python scripts/synthetic_photos.py                                   # generated test scenes
python scripts/load_demo.py demo_photos/_synthetic --complete        # 15 reports -> 5 tickets -> verified repairs
python scripts/load_demo.py --complete                               # your real photos in demo_photos/
```

### Report through Telegram (free prototype)

The optional Telegram worker accepts **private chats**, reads GPS from original
photo files when present, and uses the existing Malay/English keyword rules.
It does **not** call a paid AI API. It creates ordinary dashboard tickets with
the same prioritisation, photo privacy processing and duplicate grouping as web
reports. Staff see **Telegram** next to the resident's explanation.

1. Create a bot with Telegram's official [@BotFather](https://t.me/BotFather), using `/newbot`.
2. Keep the dashboard running. Open a second terminal in this repository, activate
   the same Python environment and run:

   ```bash
   python -m app.telegram
   ```

   Paste the bot token into the **hidden prompt**. It is not displayed or saved.
   Do not paste it into chat, commit it, or put it in a command-line argument.
   For an unattended worker, set `TOWNSHIPFIX_TELEGRAM_BOT_TOKEN` securely in its
   environment instead. `python -m app.telegram --check` checks the connection
   without starting the polling loop.

3. Open the bot's Telegram username, press Start, and send an original JPG/PNG as
   a **File/document**, with a caption explaining the issue. A normal shared photo
   also works, but may arrive without location metadata. Photo limit: 15 MB.
4. If GPS is missing, share the problem's pin, use `/place <address>` and then
   `/pick <number>`, or `/area`. The current configured areas are illustrative demo
   coordinates; replace `config.ZONES` before using area selection in a real township.
5. Review the suggested category and location. Correct the pin if needed or use
   `/category`, then `/confirm`. The ticket appears in the staff dashboard on its
   next automatic refresh. `/status` checks your latest ticket; `/cancel` drops
   the current draft. Explanations can be entered in English or Malay; bot prompts
   are currently English. Photos without an explanation prompt for one.

Both processes must use the **same data folder** (`TOWNSHIPFIX_DATA` if configured).
The worker uses [long polling](https://core.telegram.org/bots/api#getupdates), so
it only needs outbound internet access: no public URL, HTTPS tunnel or hosting
subscription is needed. Keep the computer and worker running to receive reports.
Only one worker should poll a bot; an existing webhook must be removed separately
or a different bot used. This worker never changes another integration's webhook.

Drafts and replies survive worker restarts. Drafts expire after 24 hours. Replayed
updates do not create extra reports; queued replies retry after temporary network
failures. A reply may be delivered twice if Telegram accepted it but the network
failed before acknowledging it. `/status` is supported; proactive repair-status
messages are still simulated in the dashboard outbox. WhatsApp and email intake
are not implemented in this prototype.

For a private pilot, `TOWNSHIPFIX_TELEGRAM_ALLOWED_CHATS` can contain a comma-separated
list of numeric private-chat IDs; without it, any user who finds the bot can submit
reports. Group messages, bots, voice notes and non-image documents are ignored or
rejected. Original image bytes are processed locally, GPS is extracted before the
stored image is stripped of metadata, and chat IDs/drafts are kept in local SQLite.
Only an explicit `/place` query is sent to the configured address search provider.
Telegram transports the messages and files; the application sends its replies
back to that same private chat. Stop the worker before clearing demo data.

```bash
python -m unittest tests.test_telegram -v  # offline integration tests; no bot token needed
```

## The 2-minute demo

### Choose and confirm the problem location

- **Use my current location** requests one phone location reading, with permission. It does not track the resident continuously. Use this when standing at the problem; HTTPS is required on phones.
- **Use photo location** uses GPS metadata when the uploaded photo includes it. Photos without GPS still work: search for the place or choose an area instead. A photo never overwrites an explicit manual or phone location choice.
- **Enter a road, building or landmark**, press Search, and select a result. Configured township areas are searched locally; other queries use Photon. Search is button-triggered, cached and rate-limited. Only the search words go to Photon, not the report or photo.
- Review the map, tap or drag the pin to correct it, and tap **Yes, the problem is here** before checking the report. Keyboard users can focus the pin and use arrow keys. Changing location requires confirmation again. Add a nearby landmark for the crew.

Map tiles and address lookup need internet; local area selection remains available if either service fails. The bundled Leaflet library loads locally. Areas in `app/config.py` are illustrative demo coordinates: replace them with your pilot township's roads and landmarks before field testing.

`TOWNSHIPFIX_GEOCODER_URL` selects a Photon-compatible API (default: `https://photon.komoot.io/api/`); an empty value disables external search. The [Photon public demo](https://github.com/komoot/photon#demo-server) allows reasonable small-project usage but may throttle and has no availability guarantee; use a private provider for a larger pilot. `TOWNSHIPFIX_MAP_TILE_URL` and `TOWNSHIPFIX_MAP_ATTRIBUTION` configure map tiles. Default tiles use OpenStreetMap with visible attribution and normal browser caching; follow the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and do not bulk-download/offline-cache tiles.

Coordinates, location source and optional phone accuracy are saved with the report. Existing databases upgrade automatically without deleting reports.

### Walkthrough

1. Phone 1 (Bahasa Melayu): photo of the broken streetlight, say *"Lampu jalan rosak, gelap waktu malam"*.
   Confirm the problem's map pin. The app reads it back: *"Saya faham: Lampu jalan rosak… Betul?"* Send, and you get plate **TF-0001**.
2. Phones 2 and 3 photograph the same lamp from other angles. Before sending they see
   *"Already reported by 1 neighbour (TF-0001)… photo match 96%"*. Still one ticket, now 3 reporters, higher priority.
3. A resident reports *"exposed wire sparking at the playground"*: P0 emergency, security alerted, top of the queue.
4. Staff dashboard: open TF-0001, see the three photos and **why it ranks where it does**. Assign a crew.
5. Upload a photo of a *different* place as the "after" photo. **Rejected**: scene match 17%, 277 m away.
6. Upload the real after photo. **Accepted**: same place, 1% of the scene changed (the lamp), new photo, taken after the report, 7 m away.
7. Resident's phone: before and after side by side, tap **Yes, it's fixed**. Measures update.

Screenshots of every step are in [`docs/screenshots`](docs/screenshots).

## What the AI does, honestly

| Job | How | Runs offline? |
|-----|-----|---------------|
| Understand the report | Malay + English keyword rules (incl. Manglish), danger words, impact words like *kerusi roda*, *warga emas*, *gelap* | Yes |
| Optional photo opinion | Claude vision API, only if `ANTHROPIC_API_KEY` is set; falls back to keywords on any error | No (optional) |
| Same problem? | Distance + problem type + **same-scene photo match** (SIFT keypoints + RANSAC geometry) | Yes |
| Repair really done? | Align after photo onto before photo, cancel lighting changes, measure how much of the scene changed | Yes |
| Privacy | Strips photo metadata always; blurs faces and number plates with OpenCV's detectors when installed | Yes |
| Voice | Phone's built-in speech recognition (`ms-MY`, `en-MY`) and read-aloud | On the phone |

The resident always confirms the problem type with one tap, and staff see every score's reasons.
Nothing is a black box.

**Accuracy so far:** on generated test scenes, 100% of same-problem photo pairs matched, 0 of 90
different-problem pairs matched, 15/15 real repairs were accepted and 35/35 fake ones rejected
([report](docs/evaluation_synthetic.md)). **Generated scenes are easier than real photos.** Run
`python scripts/evaluate_images.py` on real photos (see [`demo_photos/README.md`](demo_photos/README.md));
it reports accuracy and suggests new thresholds for `app/config.py`.

## Measures (shown live on the dashboard)

- **Time to report** (median seconds from opening the app to sending)
- **Duplicate reports grouped** (jobs avoided)
- **Time to fix** (median hours from report to closure)
- **Closures with verified evidence** (photo-checked and confirmed, vs. supervisor override)
- **Weak repair photos rejected** (fake or premature closures blocked)

## Tests

```bash
python -m unittest discover -s tests -t . -v      # 65 tests: location, language, vision, privacy, priority, full flows
python tests/browser_e2e.py                        # clicks through both apps in a headless browser (needs playwright)
python tests/browser_locations.py                  # GPS, manual search, pin correction and permission failures
```

GitHub Actions runs the tests and the photo check on every push (see the Actions tab).

## Project layout

```
app/
  api.py                 HTTP endpoints
  config.py              every threshold, category, team and zone in one place
  services/
    text_nlp.py          Malay/English understanding, danger + impact words, read-back
    classifier.py        problem type (keywords, optional Claude vision)
    vision.py            photo matching and change detection (OpenCV)
    privacy.py           metadata removal, face/plate blur
    dedup.py             duplicate decision with explanation
    priority.py          impact score with reasons
    verification.py      the five repair checks
    tickets.py           ticket lifecycle
    notify.py, metrics.py
  static/                resident app (index.html) and staff dashboard (staff.html), no build step
scripts/                 synthetic photos, demo loader, photo evaluation
demo_photos/             put real photos here (guide inside)
docs/                    architecture, flow, screenshots, reports
tests/
```

## Limits and next steps

- **Thresholds are tuned on generated scenes.** Real photos with heavy parallax, rain or night shots
  need the evaluation script and probably new values.
- **Messages are simulated** (dashboard outbox). Next: WhatsApp Business / SMS gateway.
- **One township per install**, with sample zones. Next: a `township_id` on tickets for multi-township rollout.
- **Staff sign-in is a shared PIN**. A pilot needs per-person accounts.
- Voice relies on the phone's speech recognition; strong dialects may need typing.

## Research behind it

- Residents least able to use reporting apps report fewer problems; see the 311 visibility audit
  (*Sustainability* 2026, doi:10.3390/su18147500) and the 311 underreporting study (*Annals of Applied Statistics*).
- Poorly maintained walkways and inaccessible infrastructure limit older adults' and disabled people's
  mobility (*Cities* review of 60 studies, 2026).
- Voice assistants suit many older adults but need customisation and error handling
  (*Universal Access in the Information Society* 2026 review).
