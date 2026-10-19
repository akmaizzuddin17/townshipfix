"""Decides what kind of problem a report is about.

Providers:
  * keywords (default, offline): the resident's words in Malay/English.
  * claude (optional): if ANTHROPIC_API_KEY is set, the photo and words are sent
    to Claude's vision API for a second opinion. Any failure falls back to keywords.
The resident always confirms the category with one tap, so the AI only suggests.
"""
import base64
import json
import os
import re

from .. import config
from . import text_nlp

PROMPT = (
    "You help a township maintenance team triage resident reports. Look at the photo "
    "and the resident's words, then reply with JSON only, no prose:\n"
    '{"category": one of %s, "confidence": 0-1, "hazards": [short strings], '
    '"description": "under 15 words, plain English"}\n'
    "If the photo does not show a township maintenance problem, use \"other\" with low confidence.\n"
    "Resident's words: %s"
)


def _provider():
    p = config.VISION_PROVIDER
    if p == "auto":
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "keywords"
    return p


def _claude(photo_bytes: bytes, media_type: str, text: str, post=None):
    import requests
    post = post or requests.post
    body = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.b64encode(photo_bytes).decode()}},
                {"type": "text", "text": PROMPT % (json.dumps(list(config.CATEGORIES)), text or "(none)")},
            ],
        }],
    }
    r = post("https://api.anthropic.com/v1/messages", timeout=20, json=body, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    r.raise_for_status()
    raw = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    cat = data.get("category")
    if cat not in config.CATEGORIES:
        raise ValueError(f"unexpected category {cat!r}")
    conf = float(data.get("confidence", 0.6))
    return {"category": cat, "confidence": round(max(0.0, min(1.0, conf)), 2),
            "source": "claude_vision", "evidence": [str(h) for h in data.get("hazards", [])][:5],
            "description": str(data.get("description", ""))[:120]}


def classify(text: str, photo_bytes: bytes = None, media_type: str = "image/jpeg", post=None) -> dict:
    cat, conf, words = text_nlp.suggest_category(text)
    kw = {"category": cat, "confidence": conf, "source": "keywords", "evidence": words, "description": ""}
    if _provider() == "claude" and photo_bytes:
        try:
            ai = _claude(photo_bytes, media_type, text, post=post)
            # if the resident's words strongly disagree, keep the words but show both
            if cat and cat != "other" and conf >= 0.8 and ai["category"] != cat:
                kw["alternative"] = ai
                return kw
            ai["keyword_guess"] = cat
            return ai
        except Exception as e:  # network down, bad key, odd reply -> stay offline
            kw["warning"] = f"vision API unavailable ({type(e).__name__}); used keywords"
    return kw
