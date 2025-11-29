"""Character service for business logic."""

import logging
from typing import Any

from data.clients import ESIClient
from models.app.character_info import CharacterInfo
from src.utils import global_config

logger = logging.getLogger(__name__)


class CharacterService:
    """Service for character-related operations."""

    def __init__(self, esi_client: ESIClient | None = None):
        """Initialize character service.

        Args:
            esi_client: ESI client instance (creates new one if None)
        """
        self._client = esi_client or ESIClient(client_id=global_config.esi.client_id)
        self._image_cache: dict[str, bytes] = {}

    async def get_authenticated_characters(self) -> list[CharacterInfo]:
        """Get all authenticated characters with full info.

        Returns:
            List of CharacterInfo with corp/alliance details
        """
        if not self._client.auth:
            return []

        characters = self._client.auth.list_authenticated_characters()
        character_infos = []

        for char in characters:
            try:
                # Get public info for corp/alliance
                public_info = await self._get_character_public_info(
                    char["character_id"]
                )

                char_info = CharacterInfo(
                    character_id=char["character_id"],
                    character_name=char["character_name"],
                    corporation_id=public_info.get("corporation_id"),
                    corporation_name=public_info.get("corporation_name"),
                    alliance_id=public_info.get("alliance_id"),
                    alliance_name=public_info.get("alliance_name"),
                    scopes=char.get("scopes", []),
                )
                character_infos.append(char_info)
            except Exception:
                logger.exception(
                    "Failed to get info for character %s", char["character_id"]
                )
                # Add minimal info
                character_infos.append(
                    CharacterInfo(
                        character_id=char["character_id"],
                        character_name=char["character_name"],
                        scopes=char.get("scopes", []),
                    )
                )

        return character_infos

    async def authenticate_character(self, scopes: list[str]) -> CharacterInfo:
        """Authenticate a new character.

        Args:
            scopes: List of ESI scopes to request

        Returns:
            CharacterInfo for newly authenticated character

        Raises:
            ValueError: If authentication fails
        """
        # Authenticate via ESI client
        token_info = await self._client.authenticate_character(scopes)

        # Get public info for corp/alliance
        try:
            public_info = await self._get_character_public_info(
                token_info["character_id"]
            )
        except Exception:
            logger.exception(
                "Failed to get public info for character %s",
                token_info["character_id"],
            )
            public_info = {}

        return CharacterInfo(
            character_id=token_info["character_id"],
            character_name=token_info["character_name"],
            corporation_id=public_info.get("corporation_id"),
            corporation_name=public_info.get("corporation_name"),
            alliance_id=public_info.get("alliance_id"),
            alliance_name=public_info.get("alliance_name"),
            scopes=token_info.get("scopes", []),
        )

    async def remove_character(self, character_id: int) -> bool:
        """Remove a character's authentication.

        Args:
            character_id: Character ID to remove

        Returns:
            True if removed, False if not found
        """
        if not self._client.auth:
            return False
        return self._client.auth.remove_token(character_id)

    async def _get_character_public_info(self, character_id: int) -> dict[str, Any]:
        """Get public character information from ESI.

        Args:
            character_id: Character ID

        Returns:
            Dict with corporation_id, corporation_name, alliance_id, alliance_name
        """
        try:
            # Get character public info
            data, _ = await self._client.request(
                "GET", f"/characters/{character_id}/", use_cache=True
            )

            result = {
                "corporation_id": data.get("corporation_id"),
            }

            # Get corporation info
            if result["corporation_id"]:
                try:
                    corp_data, _ = await self._client.request(
                        "GET",
                        f"/corporations/{result['corporation_id']}/",
                        use_cache=True,
                    )
                    result["corporation_name"] = corp_data.get("name")
                    result["alliance_id"] = corp_data.get("alliance_id")

                    # Get alliance info if exists
                    if result["alliance_id"]:
                        alliance_data, _ = await self._client.request(
                            "GET",
                            f"/alliances/{result['alliance_id']}/",
                            use_cache=True,
                        )
                        result["alliance_name"] = alliance_data.get("name")
                except Exception:
                    logger.debug(
                        "Failed to get corp/alliance info for character %s",
                        character_id,
                    )

            return result
        except Exception:
            logger.exception("Failed to get public info for character %s", character_id)
            return {}

    async def get_character_portrait(
        self, character_id: int, preferred_size: int = 1024
    ) -> bytes | None:
        """Get character portrait image, prioritizing largest size and falling back as needed."""
        cache_key = f"character_{character_id}_portrait"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        try:
            img_data, _ = await self._client.get_image_with_fallback(
                "characters", character_id, "portrait", preferred_size
            )
            if img_data:
                self._image_cache[cache_key] = img_data
            return img_data
        except Exception:
            logger.debug(
                "Failed to get portrait for character %s", character_id, exc_info=True
            )
            return None

    async def get_corporation_logo(
        self, corp_id: int, preferred_size: int = 1024
    ) -> bytes | None:
        """Get corporation logo image, prioritizing largest size and falling back as needed."""
        cache_key = f"corp_{corp_id}_logo"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        try:
            img_data, _ = await self._client.get_image_with_fallback(
                "corporations", corp_id, "logo", preferred_size
            )
            if img_data:
                self._image_cache[cache_key] = img_data
            return img_data
        except Exception:
            logger.debug(
                "Failed to get logo for corporation %s", corp_id, exc_info=True
            )
            return None

    async def get_alliance_logo(
        self, alliance_id: int, preferred_size: int = 1024
    ) -> bytes | None:
        """Get alliance logo image, prioritizing largest size and falling back as needed."""
        cache_key = f"alliance_{alliance_id}_logo"
        if cache_key in self._image_cache:
            return self._image_cache[cache_key]

        try:
            img_data, _ = await self._client.get_image_with_fallback(
                "alliances", alliance_id, "logo", preferred_size
            )
            if img_data:
                self._image_cache[cache_key] = img_data
            return img_data
        except Exception:
            logger.debug(
                "Failed to get logo for alliance %s", alliance_id, exc_info=True
            )
            return None

    async def close(self) -> None:
        """Close the service and cleanup resources."""
        await self._client.close()
