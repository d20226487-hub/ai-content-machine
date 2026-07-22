"""Guards for the output-token ceiling and truncation detection.

These are pure functions, so no DB fixtures — the point is to pin behaviour
that previously failed *silently*:

  * Claude model ids were being sent to Vertex's publishers/google endpoint,
    which reports them as unsupported / inaccessible.
  * A reply cut off at the token ceiling was written as a clean success, so a
    half-written article was indistinguishable from a finished one.
"""
from app.providers.base import (
    GenerationParams,
    gemini_completion_tokens,
    is_truncated,
)
from app.providers.vertex_ai import _accepts_sampling_params, _is_anthropic_model
from app.services.generation_limits import (
    GenerationLimits,
    resolve_max_output_tokens,
)


class TestVertexPublisherDispatch:
    """Vertex serves Claude and Gemini from different publishers with
    different request shapes; picking the wrong one is a hard failure."""

    def test_claude_models_route_to_anthropic(self):
        for model in ("claude-sonnet-5", "claude-sonnet-4-6", "claude-opus-4-8"):
            assert _is_anthropic_model(model), model

    def test_gemini_models_stay_on_the_google_path(self):
        for model in (
            "gemini-2.5-flash",
            "gemini-3.6-flash",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
        ):
            assert not _is_anthropic_model(model), model

    def test_dispatch_is_case_and_whitespace_insensitive(self):
        assert _is_anthropic_model("  Claude-Sonnet-5 ")


class TestSamplingParamCompatibility:
    """Newer Claude models reject non-default temperature/top_p with a 400,
    so bulk generation's temperature=0.7 must not reach them."""

    def test_sonnet_4_6_accepts_sampling(self):
        assert _accepts_sampling_params("claude-sonnet-4-6")

    def test_sonnet_5_rejects_sampling(self):
        assert not _accepts_sampling_params("claude-sonnet-5")

    def test_unknown_claude_model_defaults_to_omitting(self):
        # Omitting is a soft behaviour change; sending to a model that rejects
        # it is a hard 400 — so an unrecognised id must fail safe.
        assert not _accepts_sampling_params("claude-something-new-9")


class TestTruncationDetection:
    def test_every_provider_spelling_is_recognised(self):
        # Gemini shouts, OpenAI-compatible and Anthropic don't.
        assert is_truncated("MAX_TOKENS")
        assert is_truncated("length")
        assert is_truncated("max_tokens")

    def test_normal_completions_are_not_flagged(self):
        for reason in ("STOP", "stop", "end_turn", "", None):
            assert not is_truncated(reason), reason

    def test_other_stop_reasons_are_not_truncation(self):
        # SAFETY/RECITATION are worth surfacing, but they aren't "ran out of
        # room" — raising max_output_tokens wouldn't help.
        assert not is_truncated("SAFETY")
        assert not is_truncated("RECITATION")


class TestMaxOutputTokenResolution:
    def test_column_override_wins(self):
        assert resolve_max_output_tokens(16000, GenerationLimits(8192, None)) == 16000

    def test_falls_back_to_global_default(self):
        assert resolve_max_output_tokens(None, GenerationLimits(8192, None)) == 8192

    def test_nonpositive_override_falls_back(self):
        assert resolve_max_output_tokens(0, GenerationLimits(8192, None)) == 8192


class TestGeminiBillableTokens:
    """Gemini reports the answer and the reasoning separately but bills both
    at the output rate. Counting only the answer understated real spend —
    on one measured gemini-2.5-flash call, 3 answer tokens vs 346 thinking.
    Shared by ai_studio and vertex so the two can't drift apart.
    """

    def test_thinking_tokens_are_billed(self):
        usage = {
            "promptTokenCount": 22,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 346,
            "totalTokenCount": 371,
        }
        assert gemini_completion_tokens(usage) == 349

    def test_non_thinking_response_is_unchanged(self):
        # Models that don't report thoughts must bill exactly as before.
        assert gemini_completion_tokens({"candidatesTokenCount": 120}) == 120

    def test_vertex_legacy_output_token_count_spelling(self):
        assert gemini_completion_tokens({"outputTokenCount": 80}) == 80

    def test_thinking_only_response_still_counts(self):
        # A reply truncated during thinking can have no answer tokens at all —
        # that reasoning was still billed.
        assert gemini_completion_tokens({"thoughtsTokenCount": 500}) == 500

    def test_zero_answer_tokens_is_not_treated_as_missing(self):
        # Guards the old `a or b` fallback, which let a legitimate 0 fall
        # through to the other field.
        assert gemini_completion_tokens(
            {"candidatesTokenCount": 0, "thoughtsTokenCount": 40}
        ) == 40

    def test_absent_usage_stays_none(self):
        # None (not 0) so cost stays best-effort rather than claiming free.
        assert gemini_completion_tokens({}) is None

    def test_unknown_token_bucket_is_caught_by_total_reconciliation(self):
        # A future model billing reasoning under a key we don't read: the
        # explicit sum says 10, but total-minus-prompt says 200. Trust the
        # larger so new models can't silently undercount.
        usage = {
            "promptTokenCount": 22,
            "candidatesTokenCount": 10,
            "reasoningTokenCount": 190,  # hypothetical renamed field
            "totalTokenCount": 222,
        }
        assert gemini_completion_tokens(usage) == 200

    def test_total_is_never_used_to_shrink_a_known_count(self):
        # An inconsistent/partial total must not drag the figure down below
        # what the explicit fields already reported.
        usage = {
            "promptTokenCount": 22,
            "candidatesTokenCount": 3,
            "thoughtsTokenCount": 346,
            "totalTokenCount": 25,  # ignores thoughts
        }
        assert gemini_completion_tokens(usage) == 349

    def test_real_responses_reconcile_exactly(self):
        # Captured from live calls on the four models in production use.
        for name, u in {
            "gemini-2.5-flash": {"promptTokenCount": 22, "candidatesTokenCount": 3, "thoughtsTokenCount": 432, "totalTokenCount": 457},
            "gemini-3.6-flash": {"promptTokenCount": 22, "candidatesTokenCount": 3, "thoughtsTokenCount": 260, "totalTokenCount": 285},
            "gemini-3.1-flash-lite": {"promptTokenCount": 22, "candidatesTokenCount": 65, "totalTokenCount": 87},
            "gemini-3-flash-preview": {"promptTokenCount": 22, "candidatesTokenCount": 3, "thoughtsTokenCount": 469, "totalTokenCount": 494},
        }.items():
            billed = gemini_completion_tokens(u)
            assert billed == u["totalTokenCount"] - u["promptTokenCount"], name


class TestThinkingBudgetDefault:
    def test_unset_by_default(self):
        # Must stay None so providers whose thinking API we haven't verified
        # (Gemini 3.x) are never sent a field they might reject.
        assert GenerationParams().thinking_budget is None
