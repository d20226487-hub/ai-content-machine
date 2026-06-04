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

# The fix-links prompt powers the Link Checker's AI fix pass. It is given a
# piece of content plus that row's EXPECTED links and the specific problems
# the checker flagged, and must edit ONLY the links — three rules, nothing
# else. The user message (built by ``build_fix_user_message``) carries the
# content + expected list + flagged issues; this system prompt sets the
# behavior.
DEFAULT_FIX_LINKS_PROMPT = (
    "You are a precise link-correction assistant for HTML / WordPress block "
    "content. You are given a piece of content, the list of EXPECTED links "
    "for this item, and the specific link problems detected. Fix ONLY the "
    "hyperlinks. Apply exactly these three rules and nothing else:\n"
    "1. MISSING expected link: if an expected link is absent from the "
    "content, naturally integrate it into the most relevant existing "
    "sentence using concise, contextually appropriate anchor text. Do not "
    "add new sentences, paragraphs, or sections beyond the minimal anchor "
    "needed.\n"
    "2. TYPO / malformed link: if a link in the content is clearly a "
    "misspelled or malformed version of one of the expected links, correct "
    "it to match the expected link exactly.\n"
    "3. HALLUCINATED link: if a link in the content does not correspond to "
    "any expected link and is not a plausible typo of one (nothing in the "
    "expected list resembles it), remove the link by unwrapping the anchor "
    "and keeping its visible text.\n"
    "Do not add, remove, retarget, or reword any link beyond these rules. "
    "Do not change any non-link text, headings, attributes, formatting, or "
    "block structure. Preserve all existing HTML / markup exactly except "
    "for the specific link edits above. Return ONLY the corrected content — "
    "no preamble, no explanation, no quotes, no markdown fences."
)

# The gdocs-meta prompt powers the Google-Docs importer's meta extraction
# (seo_title + seo_description from the top of each Doc). Unlike translate /
# fix_links, the provider/model are NOT configured here — they're chosen per
# import on the upload modal — so this entry carries only the prompt.
DEFAULT_GDOCS_META_PROMPT = (
    "You extract SEO metadata from the top of an article. The article begins "
    "with a meta/SEO title and a meta description (the labels may vary or be "
    "absent). Return ONLY a JSON object with keys \"seo_title\" and "
    "\"seo_description\" containing the plain-text values (no labels, no "
    "quotes, no HTML). If a value is genuinely absent, use an empty string. No "
    "prose, no code fences."
)

# The gdocs-pairing prompt maps each imported Doc to its Structure entry (the
# slug source of truth). Default lives in gdocs_ai; imported here so the two
# stay in sync. Like gdocs_meta, provider/model come from the import modal.
from app.services.gdocs_ai import PAIR_STRUCT_SYSTEM_PROMPT as DEFAULT_GDOCS_PAIRING_PROMPT

DEFAULT_BRAIN_PROMPTS: dict[str, dict[str, Any]] = {
    "translate": {
        "prompt": DEFAULT_TRANSLATE_PROMPT,
        "provider_code": None,  # falls back to first-enabled provider
        "model": None,  # falls back to provider's default_model
        "default_target_language": "ru",
    },
    "fix_links": {
        "prompt": DEFAULT_FIX_LINKS_PROMPT,
        "provider_code": None,  # falls back to first-enabled provider
        "model": None,  # falls back to provider's default_model
    },
    "gdocs_meta": {
        "prompt": DEFAULT_GDOCS_META_PROMPT,
        # No provider/model — the import job uses the provider/model picked on
        # the upload modal (or the first-enabled fallback).
    },
    "gdocs_pairing": {
        "prompt": DEFAULT_GDOCS_PAIRING_PROMPT,
        # Provider/model also come from the import modal.
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


async def save_gdocs_meta_config(
    db: AsyncSession,
    *,
    prompt: str,
    actor_id: int | None,
) -> dict[str, Any]:
    """Idempotent update of just the `gdocs_meta` slice (prompt only). Other
    brain keys are preserved."""
    raw = await get_setting(db, BRAIN_KEY)
    current = raw if isinstance(raw, dict) else {}
    current = dict(current)  # copy — `get_setting` may return cached ref
    current["gdocs_meta"] = {"prompt": prompt.strip()}

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
    return _merge_defaults(current)["gdocs_meta"]


async def gdocs_meta_prompt(db: AsyncSession) -> str:
    """The effective gdocs-meta system prompt (DB override or shipped default)."""
    cfg = (await load_brain(db))["gdocs_meta"]
    return (cfg.get("prompt") or DEFAULT_GDOCS_META_PROMPT).strip()


async def save_gdocs_pairing_config(
    db: AsyncSession,
    *,
    prompt: str,
    actor_id: int | None,
) -> dict[str, Any]:
    """Idempotent update of just the `gdocs_pairing` slice (prompt only)."""
    raw = await get_setting(db, BRAIN_KEY)
    current = raw if isinstance(raw, dict) else {}
    current = dict(current)
    current["gdocs_pairing"] = {"prompt": prompt.strip()}

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
    return _merge_defaults(current)["gdocs_pairing"]


async def gdocs_pairing_prompt(db: AsyncSession) -> str:
    """The effective gdocs-pairing system prompt (DB override or default)."""
    cfg = (await load_brain(db))["gdocs_pairing"]
    return (cfg.get("prompt") or DEFAULT_GDOCS_PAIRING_PROMPT).strip()


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


async def save_fix_links_config(
    db: AsyncSession,
    *,
    prompt: str,
    provider_code: str | None,
    model: str | None,
    actor_id: int | None,
) -> dict[str, Any]:
    """Idempotent update of just the `fix_links` slice. Other brain keys are
    preserved."""
    raw = await get_setting(db, BRAIN_KEY)
    current = raw if isinstance(raw, dict) else {}
    current = dict(current)  # copy — `get_setting` may return cached ref
    current["fix_links"] = {
        "prompt": prompt.strip(),
        "provider_code": (provider_code or None),
        "model": (model or None),
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
    return _merge_defaults(current)["fix_links"]


def build_fix_user_message(
    *, content: str, expected_links: list[str], violations: list[dict]
) -> str:
    """Assemble the user message for the fix-links prompt.

    Embeds the EXPECTED links and the flagged problems so the model has the
    full context the three rules need, then the content to rewrite. The
    expected list is the single source of truth for the typo-vs-hallucination
    decision (rule 2 vs rule 3)."""
    exp = "\n".join(f"- {u}" for u in expected_links) or "(none)"
    issue_lines: list[str] = []
    for v in violations:
        problem = v.get("problem")
        link = v.get("link", "")
        if problem == "omitted":
            issue_lines.append(f"- MISSING expected link (should appear): {link}")
        elif problem == "broken":
            code = v.get("status_code")
            tail = f" (HTTP {code})" if code else ""
            issue_lines.append(
                f"- BROKEN link in the content{tail} — fix if it's a typo of "
                f"an expected link, otherwise leave it: {link}"
            )
        elif problem == "hallucinated":
            issue_lines.append(
                f"- UNEXPECTED link in the content — fix if it's a typo of an "
                f"expected link, otherwise remove it: {link}"
            )
    issues = "\n".join(issue_lines) or "(none flagged)"
    return (
        "EXPECTED LINKS for this item:\n"
        f"{exp}\n\n"
        "PROBLEMS DETECTED:\n"
        f"{issues}\n\n"
        "CONTENT TO CORRECT (return the full corrected content):\n"
        f"{content}"
    )


async def fix_links_text(
    db: AsyncSession,
    *,
    content: str,
    expected_links: list[str],
    violations: list[dict],
    system_override: str | None = None,
) -> tuple[str, str, str]:
    """Run the fix-links prompt against ``content``.

    ``system_override`` (a per-job prompt) takes precedence over the global
    Brain ``fix_links`` prompt when non-empty; the provider/model still come
    from the Brain config. Returns ``(fixed_text, provider_used_code,
    model_used)``. Raises ``ProviderNotConfigured`` when no provider is
    enabled, or ``ProviderError`` for any LLM-side failure."""
    cfg = (await load_brain(db))["fix_links"]
    code = cfg.get("provider_code") or await first_enabled_provider_code(db)
    if not code:
        raise ProviderNotConfigured(
            "No AI provider is enabled. Configure one in Settings first."
        )

    provider = await get_provider(db, code)
    model = cfg.get("model") or provider.default_model
    if not model:
        raise ProviderError(f"No model configured for provider '{code}'")

    system = (
        system_override.strip()
        if system_override and system_override.strip()
        else (cfg.get("prompt") or DEFAULT_FIX_LINKS_PROMPT)
    )
    user_msg = build_fix_user_message(
        content=content, expected_links=expected_links, violations=violations
    )

    result = await provider.generate(
        prompt=user_msg,
        model=model,
        params=GenerationParams(
            temperature=0.1,
            max_output_tokens=8192,
            system=system,
        ),
    )

    text = result.text.strip()
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
