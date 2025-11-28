"""Character information model for application use."""

from pydantic import BaseModel, Field


class CharacterInfo(BaseModel):
    """Character information with corporation and alliance details."""

    character_id: int
    character_name: str
    corporation_id: int | None = None
    corporation_name: str | None = None
    alliance_id: int | None = None
    alliance_name: str | None = None
    scopes: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration."""

        frozen = False  # Allow mutation for updates
