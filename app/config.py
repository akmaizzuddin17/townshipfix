"""Central settings for TownshipFix.

Every threshold the AI uses lives here so it can be re-tuned after you test
with real photos (see scripts/evaluate_images.py, which suggests new values).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TOWNSHIPFIX_DATA", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
FEATURE_DIR = DATA_DIR / "features"
DB_PATH = DATA_DIR / "townshipfix.db"

STAFF_PIN = os.environ.get("TOWNSHIPFIX_STAFF_PIN", "1234")
LOCAL_TZ = os.environ.get("TOWNSHIPFIX_TZ", "Asia/Kuala_Lumpur")
MAX_UPLOAD_MB = 15
# Photon-compatible address search; set an empty URL to use township areas only.
GEOCODER_URL = os.environ.get("TOWNSHIPFIX_GEOCODER_URL", "https://photon.komoot.io/api/")
MAP_TILE_URL = os.environ.get("TOWNSHIPFIX_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
MAP_ATTRIBUTION = os.environ.get("TOWNSHIPFIX_MAP_ATTRIBUTION", "© OpenStreetMap contributors")
# Blur faces / number plates when OpenCV ships the detectors (set to "off" to disable).
PRIVACY_DETECTION = os.environ.get("TOWNSHIPFIX_PRIVACY_DETECTION", "on")

# Optional cloud vision. Leave ANTHROPIC_API_KEY unset to run fully offline.
VISION_PROVIDER = os.environ.get("TOWNSHIPFIX_VISION", "auto")  # auto | keywords | claude
CLAUDE_MODEL = os.environ.get("TOWNSHIPFIX_CLAUDE_MODEL", "claude-haiku-5-5")

# ---------------------------------------------------------------- categories
# severity: 1 (cosmetic) .. 5 (dangerous). group: related categories that a
# resident might confuse, so duplicates can still merge across them.
CATEGORIES = {
    "electrical":    {"en": "Exposed wiring / electrical", "ms": "Wayar terdedah / elektrik",  "severity": 5, "team": "electrical", "group": "lighting"},
    "streetlight":   {"en": "Broken streetlight",        "ms": "Lampu jalan rosak",          "severity": 3, "team": "electrical", "group": "lighting"},
    "road_damage":   {"en": "Pothole / road damage",     "ms": "Lubang / jalan rosak",       "severity": 3, "team": "civil",      "group": "surface"},
    "walkway":       {"en": "Damaged walkway",           "ms": "Laluan pejalan kaki rosak",  "severity": 3, "team": "civil",      "group": "surface"},
    "accessibility": {"en": "Blocked ramp / OKU access", "ms": "Tanjakan / laluan OKU terhalang", "severity": 4, "team": "civil",  "group": "surface"},
    "drain":         {"en": "Blocked drain / flooding",  "ms": "Longkang tersumbat / banjir", "severity": 3, "team": "drainage", "group": "water"},
    "water_leak":    {"en": "Burst pipe / water leak",   "ms": "Paip pecah / air bocor",     "severity": 3, "team": "drainage",   "group": "water"},
    "waste_bin":     {"en": "Overflowing bin / rubbish", "ms": "Tong sampah penuh / sampah", "severity": 2, "team": "cleansing",  "group": "waste"},
    "tree":          {"en": "Fallen tree / branches",    "ms": "Pokok / dahan tumbang",      "severity": 3, "team": "landscape",  "group": "green"},
    "playground":    {"en": "Unsafe playground",         "ms": "Taman permainan tidak selamat", "severity": 3, "team": "landscape", "group": "green"},
    "vandalism":     {"en": "Vandalism / graffiti",      "ms": "Vandalisme / conteng",       "severity": 1, "team": "facilities", "group": "other"},
    "other":         {"en": "Other problem",             "ms": "Masalah lain",               "severity": 2, "team": "facilities", "group": "other"},
}

TEAMS = {
    "electrical": "Electrical team",
    "civil":      "Civil & roads team",
    "drainage":   "Drainage & water team",
    "cleansing":  "Cleansing contractor",
    "landscape":  "Landscape & parks team",
    "facilities": "Facilities helpdesk",
    "security":   "Security control room",
}

# Impact flags a resident can tick (or that we detect from their words).
IMPACT_FLAGS = {
    "wheelchair":  {"points": 20, "en": "Blocks wheelchair / pram access", "ms": "Menghalang kerusi roda / kereta sorong"},
    "injury":      {"points": 20, "en": "Someone has been hurt",           "ms": "Ada orang tercedera"},
    "school":      {"points": 10, "en": "Near school, clinic or surau",     "ms": "Dekat sekolah, klinik atau surau"},
    "vulnerable":  {"points": 10, "en": "Affects elderly or children",     "ms": "Menjejaskan warga emas atau kanak-kanak"},
    "night":       {"points": 10, "en": "Unsafe at night / dark area",     "ms": "Tidak selamat waktu malam / gelap"},
}

# Priority bands: (minimum score, band, hours to fix)
PRIORITY_BANDS = [(75, "P1", 24), (50, "P2", 72), (0, "P3", 168)]
EMERGENCY_SLA_HOURS = 2

# ---------------------------------------------------------- duplicate rules
DEDUP_RADIUS_M = 80          # only open tickets this close are compared
DEDUP_NO_PHOTO_RADIUS_M = 25 # without photos, require this closeness
DEDUP_MERGE_SCORE = 0.62     # combined score needed to merge automatically
DEDUP_SUGGEST_SCORE = 0.45   # between this and MERGE -> "possible duplicate"
DEDUP_STRONG_IMAGE = 0.75    # same scene so clearly that category typos are ignored
DEDUP_DIFFERENT_SCENE = 0.15 # photo match below this = clearly a different spot

# ------------------------------------------------------- image match tuning
IMAGE_MAX_SIDE = 640
SIFT_RATIO = 0.75
GEOM_MIN_INLIERS = 10        # fewer inliers -> not the same scene
GEOM_FULL_INLIERS = 45       # this many inliers -> similarity 1.0

# ---------------------------------------------------- repair verification
VERIFY_MAX_DISTANCE_M = 50
VERIFY_MIN_SCENE = 0.30      # geometric match needed to accept "same place"
VERIFY_MIN_CHANGE = 0.0075   # fraction of the scene that must look different
VERIFY_MAX_CHANGE = 0.50     # more than this -> probably a different view/place
VERIFY_DIFF_L = 30           # brightness difference (Lab L, 0-255) that counts as changed
VERIFY_DIFF_AB = 18          # colour difference that counts as changed
AUTO_CLOSE_HOURS = 72        # resident silent this long after a verified fix -> close

# ----------------------------------------------------------- demo township
# Sample zones so residents without GPS can still pick a location.
# Coordinates are illustrative sample data, not a real development's layout.
ZONES = [
    {"id": "Z1", "name": "Main boulevard",       "lat": 3.07210, "lng": 101.51820},
    {"id": "Z2", "name": "Community park",       "lat": 3.07345, "lng": 101.52010},
    {"id": "Z3", "name": "School & clinic area", "lat": 3.07050, "lng": 101.51655},
    {"id": "Z4", "name": "Apartment Block C",    "lat": 3.07440, "lng": 101.51740},
    {"id": "Z5", "name": "Shoplots & surau",     "lat": 3.07120, "lng": 101.52150},
]
