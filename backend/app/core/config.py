from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    # Single-key form (backward compatible). For rotation, set FERNET_KEYS
    # instead — see fernet_keys_list below.
    FERNET_KEY: str | None = None
    # Comma-separated list of Fernet keys, primary first. Rotation flow:
    #   1. Generate a new key (Fernet.generate_key()).
    #   2. Set FERNET_KEYS="<new>,<old>"  — primary first, old kept for decrypt.
    #   3. Restart api + worker. New writes use <new>; old ciphertext still
    #      decrypts via <old>.
    #   4. Re-encrypt existing rows at leisure (a script can call MultiFernet
    #      .rotate on each row), then drop <old> from FERNET_KEYS.
    # Either FERNET_KEY or FERNET_KEYS must be set; FERNET_KEYS wins if both.
    FERNET_KEYS: str | None = None

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def fernet_keys_list(self) -> list[str]:
        """Resolved list of Fernet keys, primary first.

        Precedence: FERNET_KEYS over FERNET_KEY. The single-key field stays
        supported so existing .env files (which only ship FERNET_KEY) keep
        working without operator action.
        """
        if self.FERNET_KEYS:
            keys = [k.strip() for k in self.FERNET_KEYS.split(",") if k.strip()]
            if keys:
                return keys
        if self.FERNET_KEY:
            return [self.FERNET_KEY]
        raise ValueError(
            "Neither FERNET_KEY nor FERNET_KEYS is set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
