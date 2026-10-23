import re
import unicodedata
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

MAX_TOPIC_LENGTH = 100
MAX_DEV_NAME_LENGTH = 50

_WHITESPACE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    """Trim and collapse runs of whitespace to a single space."""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_topic_name(name: str) -> str:
    """Key used to detect duplicates regardless of case or spacing."""
    return clean_text(name).casefold()


def _validate_text(value: str, label: str, max_length: int) -> str:
    value = clean_text(value)
    if not value:
        raise ValueError(f"{label} can't be empty.")
    if len(value) > max_length:
        raise ValueError(f"{label} must be {max_length} characters or fewer.")
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError(f"{label} contains invalid characters.")
    if not any(ch.isalnum() for ch in value):
        raise ValueError(f"{label} must contain at least one letter or number.")
    return value


class TopicCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_text(value, "Topic", MAX_TOPIC_LENGTH)


class TopicOut(BaseModel):
    id: int
    name: str
    vote_count: int
    has_voted: bool
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


class AuthOptions(BaseModel):
    google_enabled: bool
    dev_login_enabled: bool
    csrf_token: str


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_text(value, "Name", MAX_DEV_NAME_LENGTH)
