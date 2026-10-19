# TownshipFix: notes for the 23 October proposal

Reusable text for the submission. Replace the bracketed parts with your own findings.

## Problem

Residents waste time chasing updates because they don't know whom to contact or how to track an issue
(hackathon brief, PEOPLE examples). Three things make it worse:

- **The same problem is reported many times** through WhatsApp groups, calls and forms, so staff sort duplicates by hand.
- **Jobs are handled first come, first served**, not by how much they hurt residents. A ramp blocked for
  wheelchair users waits behind a cosmetic job.
- **Jobs get closed without proof**, so residents lose trust and report again.

The people least able to use apps (older residents, people with limited digital skills or language barriers)
report least, so their problems stay invisible. 311 studies in US cities find reporting depends on digital
access, skills and trust (*Sustainability* 2026; *Annals of Applied Statistics*).

[Add your resident interviews here: how many people, how they report today, how long it takes.]

## Solution

A phone web app plus a staff dashboard:

1. **Report in under a minute.** Photo and/or voice, in Malay or English. The app reads the report back
   ("Saya faham: Lampu jalan rosak… Betul?") before sending. Family can report for an elderly neighbour.
2. **One ticket per real problem.** Reports within 80 m are compared by distance, problem type and a
   same-scene photo match. Duplicates join the existing ticket and raise its priority.
3. **Ranked by impact on residents**, with visible reasons: severity, who is affected (wheelchair, school or
   clinic nearby, elderly, unsafe at night), how many reported it, and how long it has waited.
   Danger words such as *wayar terdedah* or *bau gas* trigger an emergency alert to security.
4. **Proof before closing.** The crew's after photo must show the same place with a visible change, must not
   be a reused photo, and must be taken after the report and nearby. The resident then confirms or reopens.

## Six judging criteria

| Criterion | Evidence |
|-----------|----------|
| Relevant | Directly addresses the brief's "Getting help for public assets" problem, plus Safety and Accessibility |
| Impactful | Measured live: time to report, duplicates grouped, time to fix, % closures with verified evidence |
| Innovative | Beyond a reporting form: impact-based ranking with reasons, photo-verified closure, Malay/English voice with read-back |
| Feasible | Runs on one laptop with Python; phones need only a browser; offline AI (no paid service needed) |
| Scalable | Categories, teams, zones and thresholds are in one config file; next step is a township ID per ticket |
| Evidence based | Working prototype, 53 automated tests, photo evaluation script, [your user test results] |

## User test plan (before 23 Oct)

- 8 to 10 people, including at least 3 older residents or relatives.
- Task: report one problem with TownshipFix and with a typed form (or WhatsApp to management).
- Measure: seconds to finish, failed attempts, 1–5 "would you use it again?".
- Photos: shoot 4–6 real problems as described in `demo_photos/README.md`, then run
  `python scripts/evaluate_images.py` and quote its accuracy.

| Measure | Typed form | TownshipFix |
|---------|-----------|-------------|
| Median time to report | [ ] s | [ ] s |
| Failed attempts | [ ] | [ ] |
| Would use again (1–5) | [ ] | [ ] |
| Same-problem photos matched | n/a | [ ] / [ ] |
| Fake repair photos caught | n/a | [ ] / [ ] |

## Pilot in one Sime Darby Property township (proposal)

- Month 1: one zone, streetlights + walkways + bins; QR code posters at lift lobbies and the surau.
- Month 2: add WhatsApp notifications and per-person staff accounts.
- Success = 30% fewer duplicate tickets, 25% faster median fix, 90% of closures with verified evidence.
  [Adjust the targets after your user test.]

## Honest limits

- Photo thresholds were tuned on generated scenes; real photos need re-checking with the evaluation script.
- Messages are simulated; a pilot needs an SMS or WhatsApp gateway.
- Voice depends on the phone's speech recognition; strong dialects may need typing.
