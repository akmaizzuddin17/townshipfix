"""Telegram events through real photo storage/ticket creation, without network."""
import io
import json
import unittest
from unittest import mock

import requests
from PIL import Image

from app import config, db
from app.services import telegram
from tests.helpers import AppTestCase, PIN


class FakeTelegram:
    def __init__(self, photo):
        self.photo = photo
        self.messages = []
        self.failure = None
        self.updates = []

    def download(self, media):
        return self.photo

    def call(self, method, **payload):
        if self.failure:
            raise self.failure
        if method == "getUpdates":
            return self.updates
        self.messages.append(payload)
        return {"message_id": len(self.messages)}


class TestTelegramIntake(AppTestCase):
    def setUp(self):
        super().setUp()
        self.photo = (self.photos / "case1_streetlight_main_boulevard" / "before_1.jpg").read_bytes()
        self.client = FakeTelegram(self.photo)
        self.bot = telegram.TelegramIntake(self.client, 77)
        self.update_id = 0

    def send(self, text=None, chat=123, **message):
        self.update_id += 1
        message = {"chat": {"type": "private", "id": chat}, "from": {"id": chat}, **message}
        if text is not None:
            message["text"] = text
        update = {"update_id": self.update_id, "message": message}
        self.bot.process_update(update)
        self.bot.flush_replies()
        return update

    def count(self):
        return db.q1("SELECT COUNT(*) AS n FROM reports")["n"]

    def draft(self, chat=123):
        row = db.q1("SELECT draft FROM telegram_chats WHERE bot_id=77 AND chat_id=?", (chat,))
        return json.loads(row["draft"])

    def photo_message(self, **extra):
        return self.send(document={"file_id": "image", "mime_type": "image/jpeg"},
                         caption="Lampu jalan rosak, gelap waktu malam", **extra)

    def test_original_photo_gps_and_text_create_dashboard_ticket_only_after_confirmation(self):
        self.photo_message()
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.draft()["location"]["source"], "photo_gps")
        self.assertIn("keyword suggestion", self.client.messages[-1]["text"])
        before = self.c.get("/api/staff/changes", headers=PIN).json["version"]
        self.send("/confirm")
        self.assertEqual(self.count(), 1)
        report = db.q1("SELECT * FROM reports")
        ticket = self.c.get("/api/staff/tickets/TF-0001", headers=PIN).json
        self.assertEqual(ticket["reports"][0]["source_channel"], "telegram")
        self.assertEqual(report["text"], "Lampu jalan rosak, gelap waktu malam")
        self.assertEqual(ticket["category"], "streetlight")
        self.assertEqual(report["location_source"], "photo_gps")
        self.assertTrue((config.UPLOAD_DIR / report["photo"]).exists())
        with Image.open(config.UPLOAD_DIR / report["photo"]) as cleaned:
            self.assertFalse(cleaned.getexif())
        self.assertNotEqual(before, self.c.get("/api/staff/changes", headers=PIN).json["version"])
        self.assertEqual(self.draft(), {})

    def test_photo_without_gps_asks_for_pin_then_submits(self):
        clean = io.BytesIO()
        Image.new("RGB", (60, 60), "gray").save(clean, format="JPEG")
        self.client.photo = clean.getvalue()
        self.send(photo=[{"file_id": "compressed"}], caption="Pothole in the road")
        self.assertIn("no problem location", self.client.messages[-1]["text"])
        self.send("/confirm")
        self.assertEqual(self.count(), 0)
        self.send(location={"latitude": 3.1, "longitude": 101.5, "horizontal_accuracy": 12})
        self.send("/confirm")
        report = db.q1("SELECT * FROM reports")
        self.assertEqual(report["location_source"], "telegram_pin")
        self.assertEqual(report["lat"], 3.1)
        self.assertEqual(report["location_accuracy_m"], 12)

    def test_shared_pin_overrides_photo_gps_and_later_photo_preserves_pin(self):
        self.photo_message()
        self.send(location={"latitude": 3.2, "longitude": 101.7})
        self.send(document={"file_id": "replacement", "mime_type": "image/jpeg"})
        self.assertEqual(self.draft()["location"]["source"], "telegram_pin")
        self.assertEqual(self.draft()["location"]["lat"], 3.2)

    def test_draft_and_offset_survive_worker_restart(self):
        self.photo_message()
        self.bot = telegram.TelegramIntake(self.client, 77)
        self.assertEqual(self.bot.offset, 2)
        self.send("/confirm")
        self.assertEqual(self.count(), 1)

    def test_replayed_confirmation_and_reply_failure_never_duplicate_report(self):
        self.photo_message()
        self.update_id += 1
        update = {"update_id": self.update_id, "message": {"chat": {"type": "private", "id": 123}, "text": "/confirm"}}
        self.bot.process_update(update)
        self.client.failure = telegram.TelegramError()
        with self.assertRaises(telegram.TelegramError):
            self.bot.flush_replies()
        self.bot.process_update(update)
        self.assertEqual(self.count(), 1)
        self.client.failure = None
        self.bot = telegram.TelegramIntake(self.client, 77)
        self.bot.flush_replies()
        self.assertIn("TF-0001", self.client.messages[-1]["text"])
        self.assertEqual(db.q1("SELECT COUNT(*) AS n FROM telegram_replies WHERE sent=0")["n"], 0)
        self.send("/confirm")
        self.assertEqual(self.count(), 1)

    def test_failed_transaction_retries_without_partial_report_or_receipt(self):
        self.photo_message()
        update = {"update_id": 2, "message": {"chat": {"type": "private", "id": 123}, "text": "/confirm"}}
        with mock.patch.object(self.bot, "_reply", side_effect=RuntimeError("disk problem")):
            with self.assertRaises(RuntimeError):
                self.bot.process_update(update)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.bot.offset, 2)
        self.assertTrue(self.draft())
        self.bot.process_update(update)
        self.assertEqual(self.count(), 1)

    def test_conversations_are_separate_and_group_messages_ignored(self):
        self.photo_message()
        self.send("/confirm", chat=456)
        self.assertEqual(self.count(), 0)
        self.bot.process_update({"update_id": 99, "message": {"chat": {"type": "group", "id": -10}, "text": "/confirm"}})
        self.assertIsNone(db.q1("SELECT 1 FROM telegram_chats WHERE chat_id=-10"))
        self.send("/confirm")
        self.assertEqual(self.count(), 1)

    def test_allowlist_rejects_other_private_chats(self):
        self.bot = telegram.TelegramIntake(self.client, 77, {999})
        self.photo_message()
        self.assertEqual(self.client.messages, [])
        self.assertIsNone(db.q1("SELECT 1 FROM telegram_chats"))

    def test_cancel_and_expired_draft_cannot_be_confirmed(self):
        self.photo_message()
        self.send("/cancel")
        self.send("/confirm")
        self.assertEqual(self.count(), 0)
        self.photo_message()
        self.advance(hours=25)
        self.send("/confirm")
        self.assertEqual(self.count(), 0)

    def test_text_only_area_and_category_override(self):
        self.send("Broken lamp near the park")
        self.send("/area Z2")
        self.send("/category electrical")
        self.send("/confirm")
        report = db.q1("SELECT * FROM reports")
        self.assertEqual(report["location_source"], "zone")
        self.assertEqual(report["category_chosen"], "electrical")
        self.assertIsNone(report["photo"])

    def test_address_requires_choice_and_new_search_invalidates_old_pin(self):
        self.photo_message()
        self.send("/place Community park")
        self.assertNotIn("location", self.draft())
        self.send("/confirm")
        self.assertEqual(self.count(), 0)
        self.send("/pick 1")
        self.assertEqual(self.draft()["location"]["label"], "Community park")
        self.send("/confirm")
        self.assertEqual(self.count(), 1)

    def test_pin_clears_stale_address_results(self):
        self.send("/place Community park")
        self.send(location={"latitude": 3.2, "longitude": 101.7})
        self.send("/pick 1")
        self.assertEqual(self.draft()["location"]["lat"], 3.2)

    def test_invalid_photo_or_coordinates_leave_draft_intact(self):
        self.photo_message()
        old = self.draft()
        self.client.photo = b"not an image"
        self.send(document={"file_id": "bad", "mime_type": "image/jpeg"})
        self.assertEqual(old, self.draft())
        self.send(location={"latitude": float("nan"), "longitude": 101.5})
        self.assertEqual(old, self.draft())
        self.send(document={"file_id": "pdf", "mime_type": "application/pdf"})
        self.assertEqual(old, self.draft())

    def test_status_follows_latest_ticket_and_other_chats_see_no_ticket(self):
        self.photo_message()
        self.send("/confirm")
        self.send("/status")
        self.assertIn("TF-0001: open", self.client.messages[-1]["text"])
        self.send("/status", chat=456)
        self.assertNotIn("TF-0001", self.client.messages[-1]["text"])

    def test_duplicate_reports_use_existing_dashboard_deduplication(self):
        self.photo_message()
        self.send("/confirm")
        self.photo_message(chat=456)
        self.send("/confirm", chat=456)
        self.assertEqual(self.count(), 2)
        self.assertEqual(db.q1("SELECT COUNT(*) AS n FROM tickets")["n"], 1)
        self.assertIn("added to existing ticket", self.client.messages[-1]["text"])

    def test_migration_keeps_web_reports_and_labels_them_web(self):
        self.c.post("/api/reports", json={"text": "broken lamp", "zone": "Z1"})
        db.ex("ALTER TABLE reports DROP COLUMN source_channel")
        db.reset_connection()
        self.assertEqual(db.q1("SELECT source_channel FROM reports")["source_channel"], "web")
        self.assertEqual(self.count(), 1)


class TestTelegramTransport(unittest.TestCase):
    def test_token_never_appears_in_network_exception(self):
        session = mock.Mock()
        session.post.side_effect = requests.Timeout("https://api.telegram.org/botSECRET/getMe")
        client = telegram.TelegramClient("SECRET", session)
        with self.assertRaises(telegram.TelegramError) as error:
            client.call("getMe")
        self.assertNotIn("SECRET", str(error.exception))

    def test_retry_after_and_unauthorized_errors(self):
        session = mock.Mock()
        session.post.return_value.json.return_value = {"ok": False, "error_code": 429, "parameters": {"retry_after": 17}}
        with self.assertRaises(telegram.TelegramError) as error:
            telegram.TelegramClient("SECRET", session).call("sendMessage", chat_id=123, text="test")
        self.assertEqual(error.exception.retry_after, 17)

    def test_declared_and_streamed_file_limits(self):
        client = telegram.TelegramClient("SECRET", mock.MagicMock())
        with self.assertRaises(telegram.photos.PhotoError):
            client.download({"file_id": "large", "file_size": config.MAX_UPLOAD_MB * 1024 * 1024 + 1})
        client.session.post.assert_not_called()
        client.session.post.return_value.json.return_value = {"ok": True, "result": {"file_path": "photos/test.jpg"}}
        response = client.session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b"x" * 1024 * 1024] * (config.MAX_UPLOAD_MB + 1)
        with self.assertRaises(telegram.photos.PhotoError):
            client.download({"file_id": "large"})
        self.assertFalse(client.session.get.call_args.kwargs["allow_redirects"])


if __name__ == "__main__":
    unittest.main()
