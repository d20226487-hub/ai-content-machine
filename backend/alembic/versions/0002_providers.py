"""providers table with seed rows for the four supported providers

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_AVAILABLE_MODELS = {
    "ai_studio": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    "vertex": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "github_models": ["openai/gpt-4o", "openai/gpt-4o-mini", "meta/llama-3.1-405b-instruct"],
    "openrouter": [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "google/gemini-2.5-pro",
    ],
}

_DEFAULTS = [
    {
        "code": "ai_studio",
        "display_name": "Google AI Studio",
        "default_model": "gemini-2.5-flash",
        "prompt_creation_model": "gemini-2.5-pro",
        "requests_per_minute": 60,
        "max_concurrency": 5,
    },
    {
        "code": "vertex",
        "display_name": "Google Vertex AI",
        "default_model": "gemini-2.5-flash",
        "prompt_creation_model": "gemini-2.5-pro",
        "requests_per_minute": 120,
        "max_concurrency": 8,
    },
    {
        "code": "github_models",
        "display_name": "GitHub Models",
        "default_model": "openai/gpt-4o-mini",
        "prompt_creation_model": "openai/gpt-4o",
        "requests_per_minute": 30,
        "max_concurrency": 3,
    },
    {
        "code": "openrouter",
        "display_name": "OpenRouter",
        "default_model": "openai/gpt-4o-mini",
        "prompt_creation_model": "anthropic/claude-sonnet-4-6",
        "requests_per_minute": 60,
        "max_concurrency": 5,
    },
]


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("prompt_creation_model", sa.String(length=120), nullable=True),
        sa.Column("available_models", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("requests_per_minute", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("inter_request_delay_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("backoff_base_ms", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("backoff_jitter_ms", sa.Integer(), nullable=False, server_default="250"),
        sa.Column(
            "respect_retry_after", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_providers_code"),
    )
    op.create_index("ix_providers_code", "providers", ["code"])

    bind = op.get_bind()
    for row in _DEFAULTS:
        bind.execute(
            sa.text(
                """
                INSERT INTO providers
                  (code, display_name, default_model, prompt_creation_model,
                   available_models, requests_per_minute, max_concurrency)
                VALUES
                  (:code, :display_name, :default_model, :prompt_creation_model,
                   CAST(:available_models AS JSON), :rpm, :concurrency)
                """
            ),
            {
                "code": row["code"],
                "display_name": row["display_name"],
                "default_model": row["default_model"],
                "prompt_creation_model": row["prompt_creation_model"],
                "available_models": _json_dumps(_DEFAULT_AVAILABLE_MODELS[row["code"]]),
                "rpm": row["requests_per_minute"],
                "concurrency": row["max_concurrency"],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_providers_code", table_name="providers")
    op.drop_table("providers")


def _json_dumps(value: object) -> str:
    import json

    return json.dumps(value)
