"""
Module: server/ai_service.py
Purpose: Server-Side AI Summarization Service for Private & Group Chat Rooms
Mapped Requirements:
  - B1 (AI Summary Bonus): Summarizes a room's stored chat history on the Server so that
    only the Server needs an LLM API key, then returns the summary text
    to be broadcast via `AI_SUMMARY_RES` to all room members.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

logger = logging.getLogger("server.ai_service")

# Default Gemini model and API URL template
GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def load_env_file(dotenv_path: Optional[Path] = None) -> None:
    """
    Zero-dependency .env parser loading key-value pairs into os.environ.
    Does not overwrite existing environment variables.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"

    if not dotenv_path.is_file():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key:
                    os.environ.setdefault(key, val)
    except OSError as err:
        logger.warning(f"Could not read .env file at {dotenv_path}: {err}")


# Automatically attempt to load .env on module import
load_env_file()


def get_api_key() -> str:
    """Retrieves GEMINI_API_KEY from environment."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key in ("", "your_gemini_api_key_here"):
        return ""
    return key


def format_history_for_prompt(room_name: str, history: List[Dict[str, Any]]) -> str:
    """Formats stored message dictionaries into a structured LLM prompt."""
    transcript_lines = []
    for entry in history:
        ts = entry.get("timestamp", "")
        sender = entry.get("sender", "Unknown")
        text = entry.get("text", "")
        transcript_lines.append(f"[{ts}] {sender}: {text}")

    transcript = "\n".join(transcript_lines)

    return (
        f"You are an AI assistant summarizing a chat conversation from room '{room_name}'.\n"
        "Please provide a concise, clear summary highlighting:\n"
        "- Key discussion topics\n"
        "- Decisions or agreements made\n"
        "- Action items or pending questions (if any)\n\n"
        "Chat transcript:\n"
        f"{transcript}\n\n"
        "Summary:"
    )


def generate_fallback_summary(room_name: str, history: List[Dict[str, Any]], note: Optional[str] = None) -> str:
    """
    Generates a clean offline heuristic summary when Gemini API key is not configured
    or when network access is unavailable.
    """
    participants = sorted(list({entry.get("sender", "Unknown") for entry in history}))
    parts_str = ", ".join(participants) if participants else "None"
    total_msgs = len(history)

    # Pick up to the 5 most recent messages for the sample highlights
    highlights = []
    sample_entries = history[-5:] if total_msgs > 5 else history
    for entry in sample_entries:
        sender = entry.get("sender", "Unknown")
        text = entry.get("text", "")
        if len(text) > 60:
            text = text[:57] + "..."
        highlights.append(f"• {sender}: \"{text}\"")

    header = "[AI Summary - Offline Mode]"
    if note:
        header += f" ({note})"

    summary_lines = [
        header,
        f"Room: {room_name}",
        f"Total Messages: {total_msgs}",
        f"Participants: {parts_str}",
        "Recent Highlights:",
    ]
    summary_lines.extend(highlights)
    return "\n".join(summary_lines)


def generate_chat_summary(
    room_name: str,
    history: List[Dict[str, Any]],
    timeout_seconds: int = 15,
) -> Tuple[bool, str]:
    """
    Summarizes chat history using Google Gemini REST API or falls back gracefully
    to an offline heuristic summary.

    Returns:
      (success: bool, summary_text: str)
    """
    if not history:
        return False, "No chat messages in this room to summarize yet."

    api_key = get_api_key()
    if not api_key:
        logger.info(f"No GEMINI_API_KEY configured. Returning fallback summary for '{room_name}'.")
        return True, generate_fallback_summary(room_name, history, note="No API Key configured")

    prompt = format_history_for_prompt(room_name, history)
    url = GEMINI_API_URL_TEMPLATE.format(model=GEMINI_MODEL)

    payload_data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    req_body = json.dumps(payload_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw_response = response.read().decode("utf-8")
            data = json.loads(raw_response)
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts and "text" in parts[0]:
                    summary_text = parts[0]["text"].strip()
                    logger.info(f"Successfully generated AI summary for room '{room_name}' via Gemini API")
                    return True, summary_text

            # If candidates structure was unexpected
            return True, generate_fallback_summary(room_name, history, note="Empty API response")

    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as err:
        logger.warning(f"Gemini API request failed for room '{room_name}': {err}")
        return True, generate_fallback_summary(room_name, history, note="API unavailable, offline fallback used")
    except Exception as exc:
        logger.error(f"Unexpected error calling Gemini API: {exc}", exc_info=True)
        return True, generate_fallback_summary(room_name, history, note="Internal error, offline fallback used")
