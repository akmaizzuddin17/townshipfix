"""Telegram intake: durable drafts, confirmed reports and retryable replies.

No webhook/public port is needed. The separate polling worker shares the app's
SQLite database. Network delivery is outside the report transaction, so a lost
reply or repeated update cannot create a second report.
"""
import json
import math
from datetime import timedelta
from urllib.parse import quote

import requests

from .. import clock, config, db
from . import locations, photos, text_nlp, tickets


class TelegramError(Exception):
    """Safe to log: never includes the token-bearing URL or message contents."""

    def __init__(self, code=0, retry_after=5):
        super().__init__(f"Telegram request failed (code {code}); check connectivity and bot configuration.")
        self.code = code
        self.retry_after = max(1, min(int(retry_after), 300))


class TelegramClient:
    def __init__(self, token, session=None):
        self._token = token
        self.session = session or requests.Session()

    def call(self, method, **payload):
        try:
            response = self.session.post(f"https://api.telegram.org/bot{self._token}/{method}",
                                         json=payload, timeout=(10, payload.get("timeout", 0) + 20))
            body = response.json()
        except (requests.RequestException, ValueError):
            raise TelegramError() from None
        if not body.get("ok"):
            raise TelegramError(body.get("error_code", response.status_code),
                                (body.get("parameters") or {}).get("retry_after", 5))
        return body["result"]

    def download(self, media):
        limit = config.MAX_UPLOAD_MB * 1024 * 1024
        if media.get("file_size", 0) > limit:
            raise photos.PhotoError(f"Photo must be at most {config.MAX_UPLOAD_MB} MB.")
        info = self.call("getFile", file_id=media["file_id"])
        if info.get("file_size", 0) > limit:
            raise photos.PhotoError(f"Photo must be at most {config.MAX_UPLOAD_MB} MB.")
        path = info.get("file_path", "")
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise TelegramError()
        # Only Telegram's file endpoint; never follow a user-supplied URL.
        url = f"https://api.telegram.org/file/bot{self._token}/{quote(path, safe='/')}"
        try:
            with self.session.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as response:
                if response.status_code != 200:
                    raise TelegramError(response.status_code)
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise photos.PhotoError(f"Photo must be at most {config.MAX_UPLOAD_MB} MB.")
                return bytes(data)
        except requests.RequestException:
            raise TelegramError() from None


HELP = (
    "Send a photo and explain the problem in English or Bahasa Melayu. "
    "For photo GPS, send the original image as a FILE/document; shared photos may have no GPS.\n\n"
    "Share a location pin for the PROBLEM, or use:\n"
    "/place road or building — search for a place\n"
    "/area — list configured areas\n"
    "/category — change the suggested category\n"
    "/confirm — submit after reviewing the summary\n"
    "/cancel — discard the draft\n"
    "/status — check your latest submitted report\n\n"
    "Drafts expire after 24 hours. This bot is not an emergency response service."
)
LOCATION_KEYBOARD = {"keyboard": [[{"text": "Share my current location", "request_location": True}],
                                  [{"text": "/area"}], [{"text": "/cancel"}]], "resize_keyboard": True}
REVIEW_KEYBOARD = {"keyboard": [[{"text": "/confirm"}, {"text": "/cancel"}]], "resize_keyboard": True}


def valid_position(lat, lng):
    return (isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lng, (int, float)) and not isinstance(lng, bool)
            and math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180)


class TelegramIntake:
    def __init__(self, client, bot_id, allowed_chats=None):
        self.client, self.bot_id = client, bot_id
        self.allowed_chats = allowed_chats

    @property
    def offset(self):
        row = db.q1("SELECT next_offset FROM telegram_workers WHERE bot_id=?", (self.bot_id,))
        return row["next_offset"] if row else 0

    def process_update(self, update):
        update_id = update["update_id"]
        with db.transaction():
            if db.q1("SELECT 1 FROM telegram_updates WHERE bot_id=? AND update_id=?", (self.bot_id, update_id)):
                return
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if (chat.get("type") == "private" and isinstance(chat_id, int)
                    and not (message.get("from") or {}).get("is_bot")
                    and (self.allowed_chats is None or chat_id in self.allowed_chats)):
                self._process_message(chat_id, message)
            db.ex("INSERT INTO telegram_updates (bot_id, update_id) VALUES (?,?)", (self.bot_id, update_id))
            db.ex("""INSERT INTO telegram_workers (bot_id, next_offset) VALUES (?,?)
                     ON CONFLICT(bot_id) DO UPDATE SET next_offset=MAX(next_offset, excluded.next_offset)""",
                  (self.bot_id, update_id + 1))

    def _reply(self, chat_id, text, keyboard=None):
        payload = {"chat_id": chat_id, "text": text,
                   "reply_markup": keyboard or {"remove_keyboard": True}}
        db.ex("INSERT INTO telegram_replies (bot_id, payload) VALUES (?,?)", (self.bot_id, json.dumps(payload)))

    def _process_message(self, chat_id, message):
        row = db.q1("SELECT * FROM telegram_chats WHERE bot_id=? AND chat_id=?", (self.bot_id, chat_id))
        draft = json.loads(row["draft"]) if row else {}
        if row and clock.now() - clock.parse(row["updated_at"]) > timedelta(hours=24):
            draft = {}
        raw = (message.get("text") or "").strip()
        command, _, arg = raw.partition(" ")
        command = command.split("@", 1)[0].lower()
        last_code = row["last_ticket_code"] if row else None
        if command in ("/start", "/help"):
            self._reply(chat_id, HELP)
        elif command == "/cancel":
            draft = {}
            self._reply(chat_id, "Draft cancelled. Send a new photo or description whenever you are ready.")
        elif command == "/status":
            if last_code:
                ticket = tickets.get(last_code)
                if ticket["merged_into"]:
                    ticket = tickets.get(ticket["merged_into"])
                self._reply(chat_id, f"{ticket['code']}: {ticket['status'].replace('_', ' ')}. "
                                    f"{config.CATEGORIES[ticket['category']]['en']}. Team: {config.TEAMS[ticket['team']]}")
            else:
                self._reply(chat_id, "You have not submitted a report through this bot yet.")
        elif command == "/confirm":
            if draft.get("text") and draft.get("location"):
                loc = draft["location"]
                result = tickets.create_report(text=draft["text"], lat=loc["lat"], lng=loc["lng"],
                    location_source=loc["source"], location_accuracy_m=loc.get("accuracy"), landmark=loc.get("label"),
                    category=self._category(draft), flags=[], lang=draft.get("lang", "en"),
                    photo=draft.get("photo"), source_channel="telegram")
                last_code = result["ticket"]["code"]
                verb = "added to existing ticket" if result["merged"] else "created"
                self._reply(chat_id, f"Report {verb}: {last_code}. The team can now see it on the dashboard. "
                                    "Use /status to check progress, or send a new report.")
                draft = {}
            else:
                self._review(chat_id, draft)
        elif command == "/area":
            zone = next((z for z in config.ZONES if z["id"].casefold() == arg.strip().casefold()), None)
            if zone:
                draft.pop("places", None)
                draft["location"] = {**zone, "label": zone["name"], "source": "zone"}
                self._review(chat_id, draft)
            else:
                self._reply(chat_id, "Choose the problem's area:\n" + "\n".join(
                    f"/area {z['id']} — {z['name']}" for z in config.ZONES)
                    + "\nThese are configured demo areas. Use a shared pin or /place for a real address.")
        elif command == "/place":
            if not 3 <= len(arg.strip()) <= 160:
                self._reply(chat_id, "Use /place followed by a road, building or area name (3–160 characters).")
            else:
                draft.pop("location", None)
                found = locations.search(arg.strip())
                draft["places"] = found["items"][:5]
                if draft["places"]:
                    self._reply(chat_id, "Choose the problem's location:\n" + "\n".join(
                        f"/pick {i} — {p['label']}" for i, p in enumerate(draft["places"], 1)))
                else:
                    self._reply(chat_id, "No place found or search unavailable. Share a pin or use /area.", LOCATION_KEYBOARD)
        elif command == "/pick":
            places = draft.get("places", [])
            if arg.strip().isdigit() and 1 <= int(arg) <= len(places):
                draft["location"] = places[int(arg) - 1]
                draft.pop("places", None)
                self._review(chat_id, draft)
            else:
                self._reply(chat_id, "Use /place first, then /pick with one of the result numbers.")
        elif command == "/category":
            category = arg.strip()
            if category in config.CATEGORIES:
                draft["category"] = category
                self._review(chat_id, draft)
            else:
                self._reply(chat_id, "Choose a category:\n" + "\n".join(
                    f"/category {key} — {value['en']}" for key, value in config.CATEGORIES.items()))
        elif raw.startswith("/"):
            self._reply(chat_id, "Unknown command. Use /help for reporting instructions.")
        else:
            self._receive(chat_id, message, draft)
        db.ex("""INSERT INTO telegram_chats (bot_id, chat_id, draft, updated_at, last_ticket_code) VALUES (?,?,?,?,?)
                 ON CONFLICT(bot_id, chat_id) DO UPDATE SET draft=excluded.draft,
                 updated_at=excluded.updated_at, last_ticket_code=excluded.last_ticket_code""",
              (self.bot_id, chat_id, json.dumps(draft), clock.iso(clock.now()), last_code))

    def _receive(self, chat_id, message, draft):
        text = (message.get("text") or message.get("caption") or "").strip()
        combined = "\n".join(filter(None, (draft.get("text"), text)))
        if len(combined) > 1000:
            self._reply(chat_id, "The explanation is too long. Use /cancel and keep the new explanation under 1,000 characters.")
            return
        media = message.get("document") or (message.get("photo") or [None])[-1]
        if media:
            mime = media.get("mime_type", "image/jpeg")
            if not mime.startswith("image/"):
                self._reply(chat_id, "Please send an image (JPG or PNG), not another document type.")
                return
            try:
                stored = photos.store(self.client.download(media))
            except photos.PhotoError as error:
                self._reply(chat_id, f"Could not use this photo: {error}. Send a JPG or PNG and try again.")
                return
            draft["photo"] = {"name": stored["name"], "privacy": stored["privacy"]}
            exif = stored["exif"]
            if (draft.get("location") or {}).get("source") in (None, "photo_gps"):
                draft.pop("location", None)
                if valid_position(exif["lat"], exif["lng"]):
                    draft["location"] = {"lat": exif["lat"], "lng": exif["lng"],
                                         "source": "photo_gps", "label": "Photo capture location"}
        position = message.get("location")
        if position:
            lat, lng = position.get("latitude"), position.get("longitude")
            if not valid_position(lat, lng):
                self._reply(chat_id, "That location is invalid. Please share another pin.")
                return
            accuracy = position.get("horizontal_accuracy")
            if not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy) or not 0 <= accuracy <= 10000000:
                accuracy = None
            draft["location"] = {"lat": lat, "lng": lng, "source": "telegram_pin", "accuracy": accuracy,
                                 "label": "Location shared in Telegram"}
            draft.pop("places", None)
        if not text and not media and not position:
            self._reply(chat_id, "Send a photo, text explanation or location pin. Voice messages are not supported yet.")
            return
        if text:
            draft["text"] = combined
            draft.pop("category", None)  # changing the explanation requires a fresh suggestion
        draft.setdefault("lang", "ms" if (message.get("from") or {}).get("language_code", "").startswith("ms") else "en")
        self._review(chat_id, draft)

    @staticmethod
    def _category(draft):
        return draft.get("category") or text_nlp.suggest_category(draft.get("text", ""))[0] or "other"

    def _review(self, chat_id, draft):
        if not draft.get("text"):
            self._reply(chat_id, "Please describe what is broken. You can add a photo too.")
            return
        if not draft.get("location"):
            self._reply(chat_id, "I have your explanation, but no problem location. "
                        "Share a pin, use /place followed by an address, or /area. "
                        "An original photo file may contain GPS; normal shared photos may not.", LOCATION_KEYBOARD)
            return
        loc = draft["location"]
        category = config.CATEGORIES[self._category(draft)]["en"]
        danger = "\nPossible danger detected. Contact emergency services if there is immediate danger." if text_nlp.detect_emergency(draft["text"]) else ""
        self._reply(chat_id, f"Review your report:\n{draft['text']}\n\nCategory: {category} (keyword suggestion)"
                    f"\nPhoto: {'attached' if draft.get('photo') else 'none'}"
                    f"\nLocation: {loc['label']}\n{loc['lat']:.6f}, {loc['lng']:.6f}"
                    "\n\nIs this the PROBLEM's location? Use /confirm to submit, share a new pin to correct it, "
                    "or /category to change the category." + danger, REVIEW_KEYBOARD)

    def flush_replies(self):
        for row in db.q("SELECT id, payload FROM telegram_replies WHERE bot_id=? AND sent=0 ORDER BY id LIMIT 30", (self.bot_id,)):
            try:
                self.client.call("sendMessage", **json.loads(row["payload"]))
            except TelegramError as error:
                if error.code not in (400, 403):
                    raise
                # A blocked bot or invalid/deleted chat cannot accept this reply.
                db.ex("UPDATE telegram_replies SET sent=-1 WHERE id=?", (row["id"],))
            else:
                db.ex("UPDATE telegram_replies SET sent=1 WHERE id=?", (row["id"],))

    def poll_once(self):
        self.flush_replies()
        updates = self.client.call("getUpdates", offset=self.offset, timeout=25, allowed_updates=["message"])
        for update in updates:
            self.process_update(update)
        self.flush_replies()
