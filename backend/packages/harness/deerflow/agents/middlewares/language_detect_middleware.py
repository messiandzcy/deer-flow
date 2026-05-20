"""Middleware to detect user message language and inject language context for the LLM.

Detects the language of the last user message based on Unicode character ranges
and injects a ``<system-reminder>`` HumanMessage so the model knows what language
to respond in.  Avoids re-injecting the same language on consecutive turns.

Supported: chinese, japanese, korean, russian, arabic, thai, english (default).
"""

import logging
import re
from typing import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)

# Unicode ranges for character-level language detection (u-escapes for readability)
_RE_CHINESE = re.compile("[\u4e00-\u9fff]")  # CJK Unified Ideographs
_RE_JAPANESE = re.compile("[\u3040-\u309f\u30a0-\u30ff]")  # Hiragana + Katakana
_RE_KOREAN = re.compile("[\uac00-\ud7af]")  # Hangul Syllables
_RE_CYRILLIC = re.compile("[\u0400-\u04ff]")  # Cyrillic
_RE_ARABIC = re.compile("[\u0600-\u06ff]")  # Arabic
_RE_THAI = re.compile("[\u0e00-\u0e7f]")  # Thai


def _detect_language(text: str) -> str:
    """Detect the language of *text* using Unicode character-range scoring."""
    text = text.strip()
    if not text:
        return "unknown"

    scores = {
        "chinese": len(_RE_CHINESE.findall(text)),
        "japanese": len(_RE_JAPANESE.findall(text)),
        "korean": len(_RE_KOREAN.findall(text)),
        "russian": len(_RE_CYRILLIC.findall(text)),
        "arabic": len(_RE_ARABIC.findall(text)),
        "thai": len(_RE_THAI.findall(text)),
    }

    # Only consider scripts that actually appear in the text
    scores = {k: v for k, v in scores.items() if v > 0}
    if not scores:
        return "english"

    return max(scores, key=scores.get)


class LanguageDetectMiddleware(AgentMiddleware[ThreadState]):
    """Detects user message language and injects language context for the LLM.

    Runs before each model call (``before_model``) to ensure the LLM knows which
    language the user is speaking.  Only injects when the detected language
    differs from the previously injected language.
    """

    def _get_last_user_text(self, messages: list) -> str | None:
        """Return the plain-text content of the last real user message."""
        for msg in reversed(messages):
            if not isinstance(msg, HumanMessage):
                continue
            # Skip injected/system messages
            name = getattr(msg, "name", None) or ""
            if name in ("system-reminder", "todo_reminder", "todo_completion_reminder", "language_context"):
                continue
            if msg.additional_kwargs.get("hide_from_ui"):
                continue

            content = msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
                return ""
            return str(content) if content else ""
        return None

    def _last_injected_language(self, messages: list) -> str | None:
        """Return the language from the most recently injected language reminder, or None."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and getattr(msg, "name", None) == "language_context":
                m = re.search(r"language[:\s]*(\w+)", str(msg.content), re.IGNORECASE)
                if m:
                    return m.group(1).lower()
        return None

    @override
    def before_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        """Detect language and inject context before LLM call."""
        messages = state.get("messages", [])
        if not messages:
            return None

        user_text = self._get_last_user_text(messages)
        if not user_text:
            return None

        detected = _detect_language(user_text)
        if detected == "unknown":
            return None

        if self._last_injected_language(messages) == detected:
            return None

        logger.info("LanguageDetectMiddleware: detected '%s' — injecting language reminder", detected)

        reminder = HumanMessage(
            content=f"<system-reminder>\nThe user is speaking in **{detected}**. Respond in the same language.\n</system-reminder>",
            name="language_context",
            additional_kwargs={"hide_from_ui": True},
        )
        return {"messages": [reminder]}

    @override
    async def abefore_model(self, state: ThreadState, runtime: Runtime) -> dict | None:
        return self.before_model(state, runtime)
