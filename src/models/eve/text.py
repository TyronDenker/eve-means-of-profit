"""EVE Online localized text data models."""

from pydantic import BaseModel


class EveLocalizedText(BaseModel):
    """Localized text with translations in multiple languages."""

    de: str | None = None
    en: str
    es: str | None = None
    fr: str | None = None
    ja: str | None = None
    ko: str | None = None
    ru: str | None = None
    zh: str | None = None
