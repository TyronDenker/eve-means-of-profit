"""Test ESI client model integration."""

import pytest

from models.eve import EveCharacter, EVEMarketPrice


class TestEveCharacterFromESI:
    """Test EveCharacter.from_esi() method."""

    def test_from_esi_basic(self):
        """Test creating EveCharacter from basic ESI response."""
        esi_data = {
            "character_id": 123456789,
            "name": "Test Character",
            "corporation_id": 98000001,
        }

        character = EveCharacter.from_esi(esi_data)

        assert character.character_id == 123456789
        assert character.name == "Test Character"
        assert character.corporation_id == 98000001
        assert character.alliance_id is None

    def test_from_esi_complete(self):
        """Test creating EveCharacter with all fields."""
        esi_data = {
            "character_id": 987654321,
            "name": "Full Test Character",
            "corporation_id": 98000001,
            "alliance_id": 99000001,
            "birthday": "2015-03-24T11:37:00Z",
            "bloodline_id": 1,
            "description": "Character bio",
            "faction_id": 500001,
            "gender": "male",
            "race_id": 1,
            "security_status": 5.0,
            "title": "CEO",
        }

        character = EveCharacter.from_esi(esi_data)

        assert character.character_id == 987654321
        assert character.name == "Full Test Character"
        assert character.corporation_id == 98000001
        assert character.alliance_id == 99000001
        assert character.birthday is not None
        assert character.bloodline_id == 1
        assert character.description == "Character bio"
        assert character.faction_id == 500001
        assert character.gender == "male"
        assert character.race_id == 1
        assert character.security_status == 5.0
        assert character.title == "CEO"

    def test_from_esi_invalid_birthday(self):
        """Test handling invalid birthday format."""
        esi_data = {
            "character_id": 111222333,
            "name": "Test",
            "corporation_id": 98000001,
            "birthday": "invalid-date",
        }

        character = EveCharacter.from_esi(esi_data)

        # Should handle gracefully by setting birthday to None
        assert character.birthday is None


class TestMarketPriceFromESI:
    """Test MarketPrice.from_esi() method."""

    def test_from_esi_with_average_price(self):
        """Test creating MarketPrice from ESI response with average price."""
        esi_data = {
            "type_id": 34,
            "average_price": 654321.12,
            "adjusted_price": 123456.78,
        }

        price = EVEMarketPrice.from_esi(esi_data)

        assert price.type_id == 34
        assert price.weighted_average == 654321.12
        assert price.region_id == 0  # ESI prices are global
        assert price.is_buy_order is False

    def test_from_esi_with_adjusted_price_only(self):
        """Test creating MarketPrice when only adjusted price is available."""
        esi_data = {
            "type_id": 35,
            "adjusted_price": 999999.99,
            "average_price": 0.0,
        }

        price = EVEMarketPrice.from_esi(esi_data)

        assert price.type_id == 35
        assert price.weighted_average == 999999.99
        assert price.max_val == 999999.99
        assert price.min_val == 999999.99

    def test_from_esi_minimal(self):
        """Test creating MarketPrice with minimal data."""
        esi_data = {
            "type_id": 36,
        }

        price = EVEMarketPrice.from_esi(esi_data)

        assert price.type_id == 36
        assert price.weighted_average == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
