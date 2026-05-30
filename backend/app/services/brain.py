"""Brain — admin-configurable system prompts that drive on-demand actions.

Today the only "brain prompt" is `translate`, which powers the Translate
button in the bulk-table cell editor. The settings page exposes a Brain
tab where an admin can edit the prompt template, pick the provider/model
that runs it, and set the default target language. The shape is
deliberately generic so we can add more prompts later (e.g. a Summarize
button, a Title-suggest button, etc.) without another migration.

Storage: a single ``app_settings`` row keyed `brain` with shape

    {
      "translate": {
        "prompt": "<system prompt template — may use {{target_language}}>",
        "provider_code": "openrouter" | null,
        "model": "openai/gpt-4o-mini" | null,
        "default_target_language": "ru"
      }
      // future: "summarize": { ... }
    }

Falls through to ``DEFAULT_BRAIN_PROMPTS`` when no row exists so the
feature works on a fresh install without anyone touching Settings first.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import ProviderNotConfigured, get_provider
from app.services.ai_assist import first_enabled_provider_code
from app.services.app_settings_cache import (
    get_setting,
    invalidate as invalidate_setting,
)

BRAIN_KEY = "brain"

# The translate prompt is intentionally short and HTML-aware. Output
# columns in this app typically hold HTML / WordPress block markup;
# preserving structure is more important than nice prose.
DEFAULT_TRANSLATE_PROMPT = (
    "You are a professional translator. Translate the user-provided "
    "content into {{target_language}}. Preserve the original formatting "
    "exactly — keep every HTML tag, WordPress block comment, attribute, "
    "URL, and inline code identical. Translate only the human-readable "
    "text inside tags. Do not translate brand names, code identifiers, "
    "or proper nouns unless their accepted form differs in the target "
    "language. Return ONLY the translated content — no preamble, no "
    "explanation, no quotes, no markdown fences."
)

DEFAULT_BRAIN_PROMPTS: dict[str, dict[str, Any]] = {
    "translate": {
        "prompt": DEFAULT_TRANSLATE_PROMPT,
        "provider_code": None,  # falls back to first-enabled provider
        "model": None,  # falls back to provider's default_model
        "default_target_language": "ru",
    },
}


# Two-letter / short language codes expanded to their full English
# names so the prompt placeholder reads as a clear instruction. GPT
# was reading bare "uk" as "United Kingdom" → English; "Ukrainian"
# leaves no room for ambiguity. Cache keys remain the short code so
# stored translations stay consistent regardless of mapping changes.
_LANG_CODE_TO_NAME: dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "uk": "Ukrainian",
    "ua": "Ukrainian",  # common typo for the uk tag — folded in deliberately
    "pl": "Polish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "tr": "Turkish",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "he": "Hebrew",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "hr": "Croatian",
    "sl": "Slovenian",
    "be": "Belarusian",
    "kk": "Kazakh",
    "uz": "Uzbek",
    "az": "Azerbaijani",
    "ka": "Georgian",
    "hy": "Armenian",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "hi": "Hindi",
    "bn": "Bengali",
    "fa": "Persian",
    "ur": "Urdu",
}


def expand_language_label(code: str) -> str:
    """Return a human-readable target-language label for a code.

    The model reads ``"Russian"`` as Russian unambiguously; ``"ru"`` is
    less reliable (especially short ISO-639-1 codes that overlap with
    country tags — ``uk`` reads as ``United Kingdom``). For codes the
    map doesn't cover (custom-typed tags), the original code is passed
    through so power-users can still steer the model. BCP-47 region
    suffixes (e.g. ``en-GB``) are honored as-is — they're already
    unambiguous."""
    if not code:
        return code
    norm = code.strip().lower()
    if norm in _LANG_CODE_TO_NAME:
        return _LANG_CODE_TO_NAME[norm]
    # Take just the language subtag (everything before the first hyphen)
    # for region-tagged codes — e.g. "en-GB" → "English" then suffix
    # the region back so the model knows the variant.
    if "-" in norm:
        primary, _, region = norm.partition("-")
        if primary in _LANG_CODE_TO_NAME:
            return f"{_LANG_CODE_TO_NAME[primary]} ({region.upper()})"
    return code


def _merge_defaults(raw: Any) -> dict[str, dict[str, Any]]:
    """Hydrate stored partial config against the defaults so the API
    always returns a complete shape even when an admin saved only a
    subset of fields (or never saved anything)."""
    out: dict[str, dict[str, Any]] = {}
    for key, default in DEFAULT_BRAIN_PROMPTS.items():
        stored = (raw or {}).get(key) if isinstance(raw, dict) else None
        merged = dict(default)
        if isinstance(stored, dict):
            for k, v in stored.items():
                # Empty string for prompt/lang is treated as "unset" so
                # the form's blank-input case doesn't lock the feature.
                if v in ("", None) and k != "provider_code" and k != "model":
                    continue
                merged[k] = v
        out[key] = merged
    return out


async def load_brain(db: AsyncSession) -> dict[str, dict[str, Any]]:
    raw = await get_setting(db, BRAIN_KEY)
    return _merge_defaults(raw)


async def save_translate_config(
    db: AsyncSession,
    *,
    prompt: str,
    provider_code: str | None,
    model: str | None,
    default_target_language: str,
    actor_id: int | None,
) -> dict[str, Any]:
    """Idempotent update of just the `translate` slice. Other brain
    keys (when we add them) are preserved."""
    raw = await get_setting(db, BRAIN_KEY)
    current = raw if isinstance(raw, dict) else {}
    current = dict(current)  # copy — `get_setting` may return cached ref
    current["translate"] = {
        "prompt": prompt.strip(),
        "provider_code": (provider_code or None),
        "model": (model or None),
        "default_target_language": default_target_language.strip().lower() or "ru",
    }

    stmt = (
        pg_insert(AppSetting)
        .values(key=BRAIN_KEY, value=current, updated_by_id=actor_id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": current, "updated_by_id": actor_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    invalidate_setting(BRAIN_KEY)
    return _merge_defaults(current)["translate"]


async def translate_text(
    db: AsyncSession,
    *,
    source_text: str,
    target_language: str,
) -> tuple[str, str, str]:
    """Run the configured translate prompt against `source_text`.

    Returns ``(translated_text, provider_used_code, model_used)``. Raises
    ``ProviderNotConfigured`` when no provider is enabled and no override
    is set, or ``ProviderError`` for any LLM-side failure (the caller
    surfaces it as a 502).
    """
    cfg = (await load_brain(db))["translate"]
    code = cfg.get("provider_code") or await first_enabled_provider_code(db)
    if not code:
        raise ProviderNotConfigured(
            "No AI provider is enabled. Configure one in Settings first."
        )

    provider = await get_provider(db, code)
    model = cfg.get("model") or provider.default_model
    if not model:
        raise ProviderError(f"No model configured for provider '{code}'")

    # Lightweight Mustache-style substitution. We deliberately don't run
    # this through `services.prompts.render_template` — that helper raises
    # on missing vars, and the brain prompt is admin-edited so we'd rather
    # leave an unresolved placeholder visible than 500 the request.
    # Expand the bare code into a human-readable name so the model can't
    # mistake e.g. ``uk`` for "United Kingdom" → English.
    system = (cfg.get("prompt") or DEFAULT_TRANSLATE_PROMPT).replace(
        "{{target_language}}", expand_language_label(target_language)
    )

    result = await provider.generate(
        prompt=source_text,
        model=model,
        params=GenerationParams(
            temperature=0.2,
            max_output_tokens=8192,
            system=system,
        ),
    )

    text = result.text.strip()
    # Strip stray markdown fences just in case the model added them.
    if text.startswith("```") and text.endswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()

    return text, code, result.model


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def resolve_target_language(
    db: AsyncSession, requested: str | None
) -> str:
    """Resolve a requested language code, falling back to the brain default.

    Lowercases + strips. ``None`` / empty → brain's
    ``default_target_language`` (or ``ru`` if even that's unset)."""
    lang = (requested or "").strip().lower()
    if lang:
        return lang
    cfg = (await load_brain(db))["translate"]
    return (cfg.get("default_target_language") or "ru").strip().lower()


def cache_lookup(
    translations: dict | None, language: str
) -> dict | None:
    """Return a memoized translation entry if present + well-formed.

    Used by every memoized translate endpoint (cell / generation /
    prompt-version) so the cache-hit shape is identical everywhere."""
    if not translations:
        return None
    entry = translations.get(language)
    if isinstance(entry, dict) and isinstance(entry.get("text"), str):
        return entry
    return None


def make_translation_entry(
    *, text: str, provider_code: str, model: str
) -> dict[str, str]:
    """Build a translations[lang] entry with a fresh timestamp."""
    return {
        "text": text,
        "provider_used": provider_code,
        "model_used": model,
        "translated_at": now_iso(),
    }
