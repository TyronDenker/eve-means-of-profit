"""EVE Online character data models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EveCharacter(BaseModel):
    """Represents an EVE Online character from ESI API.

    Data sourced from ESI /characters/{character_id}/ endpoint.
    """

    model_config = ConfigDict(populate_by_name=True)

    character_id: int = Field(
        ..., description="The unique character ID", alias="character_id"
    )
    name: str = Field(..., description="Character name")
    corporation_id: int = Field(
        ..., description="Corporation ID the character belongs to"
    )

    # Optional fields
    alliance_id: int | None = Field(
        None, description="Alliance ID if character is in an alliance"
    )
    birthday: datetime | None = Field(None, description="Character creation date")
    bloodline_id: int | None = Field(None, description="Character's bloodline ID")
    description: str | None = Field(None, description="Character biography")
    faction_id: int | None = Field(
        None, description="Faction ID if character is in a faction"
    )
    gender: str | None = Field(None, description="Character gender (male/female)")
    race_id: int | None = Field(None, description="Character's race ID")
    security_status: float | None = Field(None, description="Character security status")
    title: str | None = Field(None, description="Character title")

    @classmethod
    def from_esi(cls, data: dict[str, Any]) -> "EveCharacter":
        """Create EveCharacter from ESI API response.

        Args:
            data: Raw dictionary from ESI /characters/{character_id}/ endpoint

        Returns:
            EveCharacter instance

        Example ESI response:
            {
                "name": "Character Name",
                "corporation_id": 98000001,
                "alliance_id": 99000001,
                "birthday": "2015-03-24T11:37:00Z",
                "bloodline_id": 1,
                "description": "Bio text",
                "faction_id": 500001,
                "gender": "male",
                "race_id": 1,
                "security_status": 5.0,
                "title": "CEO"
            }
        """
        # Extract character_id if present in the data, otherwise it should be provided separately
        character_id = data.get("character_id")

        # Parse birthday if present
        birthday = None
        if data.get("birthday"):
            try:
                birthday = datetime.fromisoformat(
                    data["birthday"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                birthday = None

        return cls(
            character_id=character_id,
            name=data["name"],
            corporation_id=data["corporation_id"],
            alliance_id=data.get("alliance_id"),
            birthday=birthday,
            bloodline_id=data.get("bloodline_id"),
            description=data.get("description"),
            faction_id=data.get("faction_id"),
            gender=data.get("gender"),
            race_id=data.get("race_id"),
            security_status=data.get("security_status"),
            title=data.get("title"),
        )

    def __str__(self) -> str:
        """Return string representation of character."""
        alliance_str = f" (Alliance: {self.alliance_id})" if self.alliance_id else ""
        return f"EveCharacter(id={self.character_id}, name='{self.name}', corp={self.corporation_id}{alliance_str})"
