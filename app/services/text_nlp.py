"""Understands what a resident said or typed, in Malay or English (or a mix).

Deliberately rule-based: transparent, works offline, and every decision comes
with the words that triggered it, so staff and judges can see *why*.
"""
import re

from .. import config

# Phrases are matched on word boundaries against lower-cased text.
CATEGORY_KEYWORDS = {
    "streetlight": [
        "streetlight", "street light", "lamp post", "lamppost", "lamp", "light", "lights",
        "bulb", "lampu", "lampu jalan", "tiang lampu", "mentol", "padam", "tak menyala",
        "tidak menyala", "berkelip", "flickering",
    ],
    "road_damage": [
        "pothole", "potholes", "road", "crack in the road", "asphalt", "tar", "lubang",
        "jalan berlubang", "jalan rosak", "jalan retak", "permukaan jalan", "bonggol", "speed bump",
    ],
    "walkway": [
        "walkway", "pavement", "sidewalk", "footpath", "tiles", "tile", "paving", "kaki lima",
        "laluan pejalan kaki", "jubin", "laluan", "pejalan kaki", "uneven", "tidak rata",
    ],
    "accessibility": [
        "ramp", "wheelchair", "oku", "disabled", "pram", "stroller", "tanjakan", "kerusi roda",
        "kereta sorong", "blocked ramp", "tactile", "lift", "lif",
    ],
    "drain": [
        "drain", "drains", "clogged", "flood", "flooding", "longkang", "parit", "tersumbat",
        "banjir", "air bertakung", "stagnant water", "mosquito", "nyamuk", "aedes",
    ],
    "water_leak": [
        "pipe", "burst", "leak", "leaking", "water leak", "paip", "pecah", "bocor", "air bocor",
        "paip pecah", "pancur",
    ],
    "waste_bin": [
        "bin", "bins", "rubbish", "garbage", "trash", "litter", "overflowing", "dumping",
        "sampah", "tong sampah", "tong", "penuh", "melimpah", "longgokan", "buang sampah",
    ],
    "tree": [
        "tree", "fallen tree", "branch", "branches", "pokok", "dahan", "ranting", "tumbang",
        "pokok tumbang", "akar",
    ],
    "playground": [
        "playground", "swing", "slide", "taman permainan", "buaian", "gelongsor", "see saw", "jongkang",
    ],
    "vandalism": [
        "graffiti", "vandal", "vandalism", "vandalised", "vandalized", "conteng", "contengan",
        "vandalisme", "dirosakkan",
    ],
}

# Words that mean "this could hurt someone right now".
EMERGENCY_PHRASES = [
    "live wire", "exposed wire", "exposed wires", "electric shock", "sparking", "sparks",
    "gas leak", "smell gas", "smell of gas", "fire", "smoke", "on fire", "open manhole",
    "manhole open", "sinkhole", "collapsed", "tree fell on", "blocking the road",
    "wayar terdedah", "renjatan", "percikan api", "bocor gas", "bau gas", "kebakaran",
    "terbakar", "asap", "lubang terbuka", "penutup longkang hilang", "mendap", "runtuh",
    "menghalang jalan",
]

FLAG_PHRASES = {
    "wheelchair": ["wheelchair", "oku", "pram", "stroller", "kerusi roda", "kereta sorong", "disabled"],
    "injury": ["fell", "fall", "fallen down", "tripped", "hurt", "injured", "accident", "bleeding",
               "jatuh", "terjatuh", "tersandung", "cedera", "luka", "kemalangan"],
    "school": ["school", "clinic", "kindergarten", "surau", "mosque", "hospital",
               "sekolah", "klinik", "tadika", "masjid", "hospital"],
    "vulnerable": ["elderly", "old people", "children", "kids", "child", "senior",
                   "warga emas", "orang tua", "kanak-kanak", "budak", "anak-anak", "pak cik", "mak cik"],
    "night": ["dark", "night", "at night", "gelap", "malam", "waktu malam", "tak nampak", "cannot see"],
}


def normalise(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find(phrases, text):
    hits = []
    for p in phrases:
        if re.search(r"(?<![\w-])" + re.escape(p) + r"(?![\w-])", text):
            hits.append(p)
    return hits


def suggest_category(text: str):
    """Return (category, confidence 0..1, matched_words)."""
    t = normalise(text)
    if not t:
        return None, 0.0, []
    scores = {}
    matched = {}
    for cat, words in CATEGORY_KEYWORDS.items():
        hits = _find(words, t)
        if hits:
            # longer phrases are more specific -> weigh by word count
            scores[cat] = sum(len(h.split()) for h in hits)
            matched[cat] = hits
    if not scores:
        return "other", 0.2, []
    # "ramp blocked" + "walkway" -> accessibility should win when wheelchair words appear
    best = max(scores, key=lambda c: (scores[c], config.CATEGORIES[c]["severity"]))
    total = sum(scores.values())
    confidence = round(min(0.95, 0.45 + 0.5 * scores[best] / total), 2)
    return best, confidence, matched[best]


def detect_emergency(text: str):
    return _find(EMERGENCY_PHRASES, normalise(text))


def detect_flags(text: str):
    t = normalise(text)
    found = {}
    for flag, words in FLAG_PHRASES.items():
        hits = _find(words, t)
        if hits:
            found[flag] = hits
    return found


def readback(category: str, place: str, lang: str, urgent: bool) -> str:
    cat = config.CATEGORIES.get(category, config.CATEGORIES["other"])
    if lang == "ms":
        s = f"Saya faham: {cat['ms']} di {place}."
        if urgent:
            s += " Ini nampak berbahaya, jadi pengawal keselamatan akan dimaklumkan segera."
        return s + " Betul?"
    s = f"I understood: {cat['en']} at {place}."
    if urgent:
        s += " This sounds dangerous, so security will be alerted straight away."
    return s + " Is that right?"
