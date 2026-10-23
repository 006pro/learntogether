import os
from dataclasses import dataclass

from dotenv import load_dotenv

VALID_ENVS = ("development", "production")


class ConfigError(RuntimeError):
    pass


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    secret_key: str = ""
    database_url: str = "sqlite:///./learntogether.db"
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = ""
    dev_auth_enabled: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            app_env=os.getenv("APP_ENV", "development").strip().lower(),
            secret_key=os.getenv("SECRET_KEY", ""),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            oauth_redirect_uri=os.getenv("OAUTH_REDIRECT_URI", "").strip(),
            dev_auth_enabled=_env_bool("DEV_AUTH_ENABLED"),
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def dev_auth_active(self) -> bool:
        # Development sign-in requires both the explicit flag and a development environment.
        return self.dev_auth_enabled and self.app_env == "development"

    def validate(self) -> None:
        if self.app_env not in VALID_ENVS:
            raise ConfigError(f"APP_ENV must be one of {', '.join(VALID_ENVS)}, got '{self.app_env}'.")
        if not self.secret_key:
            raise ConfigError("SECRET_KEY is required. Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\"")
        if self.is_production:
            if self.dev_auth_enabled:
                raise ConfigError("DEV_AUTH_ENABLED must not be set when APP_ENV=production.")
            if len(self.secret_key) < 32:
                raise ConfigError("SECRET_KEY must be at least 32 characters in production.")
            if not self.google_configured:
                raise ConfigError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required in production.")
