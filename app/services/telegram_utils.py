"""Telegram messaging, formatting, and Ollama query utilities."""
from __future__ import annotations

import html
import logging
import re
import time
from pathlib import Path

import requests

from app.core.config import TELEGRAM_BOT_TOKEN, OLLAMA_BASE_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

MAX_TELEGRAM_LEN = 3900


def send_message(chat_id: str, text: str, retries: int = 2) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN is empty — skipping send")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in _split_text(text, MAX_TELEGRAM_LEN):
        payload = {
            "chat_id": chat_id, "text": chunk,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }
        if not _post_with_fallback(url, payload, retries):
            return False
    return True


def _post_with_fallback(url: str, payload: dict, retries: int) -> bool:
    for attempt in range(1, retries + 1):
        resp = requests.post(url, json=payload, timeout=30)
        if resp.ok:
            return True
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if "can't parse entities" in body.get("description", "").lower():
            log.warning("Telegram rejected HTML — retrying as plain text")
            plain = {k: v for k, v in payload.items() if k != "parse_mode"}
            return requests.post(url, json=plain, timeout=30).ok
        if attempt < retries:
            time.sleep(2 * attempt)
    return False


def download_telegram_file(file_id: str, dest_path: Path) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile"
    resp = requests.get(url, params={"file_id": file_id}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        log.error("Failed to getFile: %s", data)
        return False

    file_path = data["result"]["file_path"]
    dl_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    dl_resp = requests.get(dl_url, stream=True, timeout=60)
    dl_resp.raise_for_status()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in dl_resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def _split_text(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_len:
            if current:
                chunks.append("".join(current))
                current = [line]
                current_len = len(line)
            else:
                chunks.append(line[:max_len])
                remainder = line[max_len:]
                current = [remainder] if remainder else []
                current_len = len(remainder)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def format_html(text: str) -> str:
    """Convert lightweight Markdown to Telegram-safe HTML."""
    escaped = html.escape(text)
    escaped = re.sub(r"(?m)^#{1,4}\s+(.*?)$", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*\*([^\s*](?:[^*]*[^\s*])?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*([^\s*](?:[^*]*[^\s*])?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"```(.*?)```", r"<pre>\1</pre>", escaped, flags=re.DOTALL)
    escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)
    return escaped


def query_ollama(prompt: str, base_url: str | None = None,
                 model: str | None = None, timeout: int = 600,
                 num_predict: int | None = None) -> str:
    base = (base_url or OLLAMA_BASE_URL).rstrip("/")
    mdl = model or OLLAMA_MODEL
    url = f"{base}/api/generate"

    log.info("Calling Ollama (%s), prompt length: %d chars", mdl, len(prompt))
    resp = requests.post(
        url,
        json={
            "model": mdl, "prompt": prompt, "stream": False, "think": False,
            "options": {"num_ctx": 4096, "num_predict": num_predict or 1024},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "")

    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if not cleaned:
        parts = raw.split("</think>")
        cleaned = parts[-1].strip() if len(parts) > 1 else raw.strip()

    if not cleaned:
        log.warning("Ollama returned empty response (raw length: %d)", len(raw))
    return cleaned
