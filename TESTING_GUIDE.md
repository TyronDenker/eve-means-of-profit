# Testing Guide

This guide outlines how to write tests for **EVE Means of Profit** based on our testing patterns and project priorities.

## Philosophy: Pragmatic Testing for MVP

**Target**: Ship ASAP with confidence, not perfection.

**Principles**:

- **Test what matters**: Focus on business logic, data processing, and critical paths
- **Start simple**: Basic functionality first, edge cases second
- **Real data wins**: Use actual EVE SDE samples where possible
- **Don't overthink**: 80% coverage of critical code beats 100% coverage of everything
- **Document shortcuts**: If you skip something intentionally, note it in comments

---

## Quick Start

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_utils/test_jsonl_parser.py

# Run specific test class
uv run pytest tests/test_utils/test_jsonl_parser.py::TestBasicParsing

# Run specific test
uv run pytest tests/test_utils/test_jsonl_parser.py::TestBasicParsing::test_parse_single_line_jsonl
```

### Writing Your First Test

```python
"""Tests for my_module."""

import pytest
from src.my_module import MyClass


def test_basic_functionality():
    """Test that MyClass does the basic thing.
    
    Given: A MyClass instance
    When: Calling the main method
    Then: Should return expected result
    """
    obj = MyClass()
    result = obj.do_thing()
    
    assert result == "expected"
```

---

## Test Structure

### File Naming

- **Test files**: `test_<module_name>.py`
- **Test classes**: `Test<Functionality>` (e.g., `TestBasicParsing`, `TestErrorHandling`)
- **Test functions**: `test_<specific_behavior>` (e.g., `test_parse_single_line_jsonl`)

---

## Test Patterns from `test_jsonl_parser.py`

Our `test_jsonl_parser.py` demonstrates proven patterns. Use these as templates.

### 1. Organize with Test Classes

Group related tests into classes for readability:

```python
class TestBasicParsing:
    """Test basic JSONL parsing functionality."""
    
    def test_parse_single_line_jsonl(self, create_jsonl_file, simple_jsonl_data):
        """Test parsing a JSONL file with a single line."""
        # ...

    def test_parse_multiple_lines_jsonl(self, create_jsonl_file, simple_jsonl_data):
        """Test parsing a JSONL file with multiple lines."""
        # ...


class TestSampleSize:
    """Test the sample_size parameter functionality."""
    
    def test_sample_size_limits_results(self, create_jsonl_file, simple_jsonl_data):
        """Test that sample_size parameter limits number of results."""
        # ...
```

**Benefits**:

- Easy to navigate
- Run specific test groups: `pytest tests/test_utils/test_jsonl_parser.py::TestBasicParsing`
- Clear separation of concerns

### 2. Use Fixtures for Test Data

Create reusable test data with fixtures:

```python
@pytest.fixture
def simple_jsonl_data() -> list[dict[str, Any]]:
    """Provide simple JSONL test data with basic key-value pairs."""
    return [
        {"_key": 1, "name": "Item 1", "value": 100},
        {"_key": 2, "name": "Item 2", "value": 200},
        {"_key": 3, "name": "Item 3", "value": 300},
    ]


@pytest.fixture
def eve_blueprint_data() -> list[dict[str, Any]]:
    """Provide realistic EVE blueprint data with nested structures.
    
    Based on actual blueprint data from EVE SDE.
    """
    return [
        {
            "_key": 681,
            "activities": {
                "copying": {"time": 480},
                "manufacturing": {
                    "materials": [{"quantity": 86, "typeID": 38}],
                    "products": [{"quantity": 1, "typeID": 165}],
                    "time": 600,
                },
            },
            "blueprintTypeID": 681,
            "maxProductionLimit": 300,
        },
    ]
```

**Benefits**:

- DRY (Don't Repeat Yourself)
- Easy to update test data in one place
- Self-documenting with docstrings

### 3. Factory Fixtures for Dynamic Test Files

Use factory fixtures when you need to create multiple variations:

```python
@pytest.fixture
def create_jsonl_file(tmp_path: Path):
    """Create factory fixture for temporary JSONL files for testing."""
    
    def _create_file(
        filename: str,
        data: list[dict[str, Any]] | None = None,
        content: str | None = None,
    ) -> Path:
        """Create a JSONL file with specified data or raw content."""
        file_path = tmp_path / filename
        
        if content is not None:
            file_path.write_text(content, encoding="utf-8")
        elif data is not None:
            lines = [json.dumps(item, ensure_ascii=False) for item in data]
            file_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            file_path.write_text("", encoding="utf-8")
        
        return file_path
    
    return _create_file


def test_example(create_jsonl_file, simple_jsonl_data):
    """Example using factory fixture."""
    file_path = create_jsonl_file("test.jsonl", simple_jsonl_data)
    # Use file_path in test...
```

**Benefits**:

- Create test files on-the-fly
- Automatic cleanup (pytest's `tmp_path` is auto-deleted)
- Flexible: pass data or raw content

### 4. Given-When-Then Docstrings

Structure test docstrings with Given-When-Then for clarity:

```python
def test_sample_size_limits_results(self, create_jsonl_file, simple_jsonl_data):
    """Test that sample_size parameter limits number of results.
    
    Given: A JSONL file with 3 objects
    When: Parsing with sample_size=2
    Then: Should return exactly 2 objects
    """
    file_path = create_jsonl_file("sample.jsonl", simple_jsonl_data)
    
    parser = JSONLParser(file_path)
    result = list(parser.parse(sample_size=2))
    
    assert len(result) == 2
    assert result == simple_jsonl_data[:2]
```

**Benefits**:

- Clear test intent
- Easy to understand what's being tested
- Self-documenting

### 5. Test Error Handling Explicitly

Don't just test the happy path—test failures:

```python
def test_file_not_found_raises_exception(self, tmp_path: Path):
    """Test that missing file raises FileNotFoundError.
    
    Given: A path to a non-existent file
    When: Attempting to parse
    Then: Should raise FileNotFoundError with appropriate message
    """
    non_existent = tmp_path / "does_not_exist.jsonl"
    
    parser = JSONLParser(non_existent)
    
    with pytest.raises(FileNotFoundError) as exc_info:
        list(parser.parse())
    
    assert "File not found" in str(exc_info.value)
    assert str(non_existent) in str(exc_info.value)


def test_invalid_json_line_is_skipped(self, create_jsonl_file):
    """Test that invalid JSON lines are skipped with warning.
    
    Given: A JSONL file with 1 valid and 1 invalid JSON line
    When: Parsing the file
    Then: Should return only the valid line and skip the invalid one
    """
    content = '{"_key": 1, "name": "Valid"}\n{invalid json here\n{"_key": 2, "name": "Also valid"}'
    file_path = create_jsonl_file("invalid.jsonl", content=content)
    
    parser = JSONLParser(file_path)
    result = list(parser.parse())
    
    assert len(result) == 2
    assert result[0]["name"] == "Valid"
    assert result[1]["name"] == "Also valid"
```

**Benefits**:

- Ensures graceful error handling
- Documents expected error behavior
- Catches regressions in error messages

### 6. Integration Tests with Real Data

Test with actual EVE SDE data when available:

```python
class TestIntegration:
    """Integration tests with real EVE SDE data."""
    
    def test_parse_real_races_file(self):
        """Test parsing the actual races.jsonl file from EVE SDE.
        
        Given: The real races.jsonl file from data/sde
        When: Parsing the file
        Then: Should successfully parse all races
        """
        sde_path = Path("e:/DOCS/Video Game Related/EVE Online/eve-means-of-profit/data/sde")
        races_file = sde_path / "races.jsonl"
        
        if not races_file.exists():
            pytest.skip("Real SDE data not available")
        
        parser = JSONLParser(races_file)
        result = list(parser.parse())
        
        # Verify we got race data
        assert len(result) > 0
        # Check for known races
        race_keys = [r["_key"] for r in result]
        assert 1 in race_keys  # Caldari
        assert 2 in race_keys  # Minmatar
```

**Benefits**:

- Catches real-world edge cases
- Validates against actual game data
- Use `pytest.skip()` to handle missing data gracefully

### 7. Parametrize for Multiple Scenarios

Use `@pytest.mark.parametrize` to test multiple inputs efficiently:

```python
@pytest.mark.parametrize("sample_size", [1, 2, 5, 10])
def test_sample_size_parametrized(self, create_jsonl_file, sample_size: int):
    """Test various sample_size values with parametrization.
    
    Given: A JSONL file with 10 objects
    When: Parsing with different sample_size values
    Then: Should return correct number of objects
    """
    data = [{"_key": i, "value": i * 10} for i in range(10)]
    file_path = create_jsonl_file("param.jsonl", data)
    
    parser = JSONLParser(file_path)
    result = list(parser.parse(sample_size=sample_size))
    
    assert len(result) == sample_size
    assert result == data[:sample_size]


@pytest.mark.parametrize("error_position", ["start", "middle", "end"])
def test_errors_at_different_positions(self, create_jsonl_file, error_position: str):
    """Test handling errors at different file positions."""
    valid_lines = ['{"_key": 1}', '{"_key": 2}', '{"_key": 3}']
    invalid = "{bad json"
    
    if error_position == "start":
        lines = [invalid, *valid_lines]
        expected_error_line = 1
    elif error_position == "middle":
        lines = [valid_lines[0], invalid, valid_lines[1], valid_lines[2]]
        expected_error_line = 2
    else:  # end
        lines = [*valid_lines, invalid]
        expected_error_line = 4
    
    content = "\n".join(lines)
    file_path = create_jsonl_file(f"error_{error_position}.jsonl", content=content)
    
    parser = JSONLParser(file_path)
    result = list(parser.parse())
    
    assert len(result) == 3
    assert len(parser.errors) == 1
    assert parser.errors[0][0] == expected_error_line
```

**Benefits**:

- Run one test with multiple inputs
- Reduces code duplication
- Easy to add more test cases

---

## What to Test (Priority Order)

### Critical (Must Have for Release)

1. **Data Loaders** (`src/data/loaders/`)
   - Parse SDE JSONL files correctly
   - Handle malformed data gracefully
   - Validate field mappings

2. **Core Services** (`src/core/`)
   - Manufacturing cost calculations
   - Blueprint queries
   - Price analysis

3. **Data Managers** (`src/data/managers/`)
   - SDEManager caching and lookups
   - MarketDataManager price queries

### Important (Should Have)

1. **Models** (`src/models/eve/`)
   - Pydantic validation works
   - Edge cases in field constraints

2. **Utilities** (`src/utils/`)
   - Config path resolution
   - Formatting functions
   - JSONL parser (**Done!** See `test_jsonl_parser.py`)

### Nice to Have (Can Wait)

1. **UI Components** (`src/ui/`)
   - UI tests are slow and fragile
   - Manual testing is fine for MVP
   - Focus on logic, not widgets

---

## Testing Recipes

### Recipe 1: Testing a Service

```python
"""Tests for ManufacturingService."""

import pytest
from src.core.manufacturing_service import ManufacturingService
from src.data.managers.sde import SDEManager
from src.data.managers.market import MarketDataManager


class TestManufacturingService:
    """Test manufacturing calculations."""
    
    @pytest.fixture
    def service(self):
        """Create a ManufacturingService instance for testing."""
        # Use real or mock managers depending on test needs
        sde_manager = SDEManager()  # Or a mock
        market_manager = MarketDataManager()  # Or a mock
        return ManufacturingService(sde_manager, market_manager)
    
    def test_calculate_base_manufacturing_cost(self, service):
        """Test basic manufacturing cost calculation.
        
        Given: A blueprint with known materials and prices
        When: Calculating manufacturing cost with no bonuses
        Then: Should return correct base cost
        """
        blueprint_id = 681  # Example blueprint
        
        result = service.calculate_manufacturing_cost(
            blueprint_id=blueprint_id,
            runs=1,
            me_level=0,
            te_level=0,
        )
        
        assert result["total_cost"] > 0
        assert "material_cost" in result
        assert "installation_cost" in result
```

### Recipe 2: Testing a Data Loader

```python
"""Tests for SDEJsonlLoader."""

import pytest
from pathlib import Path
from src.data.loaders.sde_jsonl import SDEJsonlLoader


class TestSDEJsonlLoader:
    """Test SDE JSONL data loading."""
    
    @pytest.fixture
    def loader(self):
        """Create loader instance."""
        return SDEJsonlLoader()
    
    def test_load_types_returns_eve_type_objects(self, loader):
        """Test that load_types returns EveType instances.
        
        Given: A real types.jsonl file
        When: Loading types with sample_size=10
        Then: Should return list of EveType objects
        """
        types = list(loader.load_types(sample_size=10))
        
        assert len(types) == 10
        assert all(hasattr(t, "id") for t in types)
        assert all(hasattr(t, "name") for t in types)
    
    def test_field_name_mapping_works(self, loader):
        """Test that camelCase SDE fields are mapped to snake_case.
        
        Given: SDE data with camelCase field names
        When: Loading the data
        Then: Should map to snake_case model fields
        """
        types = list(loader.load_types(sample_size=1))
        
        # Check that snake_case fields exist
        assert hasattr(types[0], "group_id")  # Not "groupID"
        assert hasattr(types[0], "base_price")  # Not "basePrice"
```

### Recipe 3: Testing a Pydantic Model

```python
"""Tests for EveBlueprint model."""

import pytest
from pydantic import ValidationError
from src.models.eve.blueprint import EveBlueprint, ManufacturingMaterial


class TestEveBlueprintModel:
    """Test EveBlueprint Pydantic model validation."""
    
    def test_valid_blueprint_passes_validation(self):
        """Test that valid blueprint data passes Pydantic validation.
        
        Given: Valid blueprint data matching EVE SDE structure
        When: Creating an EveBlueprint instance
        Then: Should validate successfully
        """
        data = {
            "id": 681,
            "blueprint_type_id": 681,
            "max_production_limit": 300,
            "activities": {
                "manufacturing": {
                    "time": 600,
                    "materials": [
                        {"type_id": 38, "quantity": 86}
                    ],
                    "products": [
                        {"type_id": 165, "quantity": 1}
                    ]
                }
            }
        }
        
        blueprint = EveBlueprint(**data)
        
        assert blueprint.id == 681
        assert blueprint.blueprint_type_id == 681
    
    def test_invalid_material_quantity_raises_error(self):
        """Test that invalid material quantity fails validation.
        
        Given: Material with quantity outside valid range
        When: Creating a ManufacturingMaterial instance
        Then: Should raise ValidationError
        """
        with pytest.raises(ValidationError) as exc_info:
            ManufacturingMaterial(type_id=38, quantity=-1)
        
        assert "quantity" in str(exc_info.value)
```

### Recipe 4: Testing Utilities

```python
"""Tests for formatting utilities."""

import pytest
from src.utils.formatting import format_currency, format_number


class TestFormatting:
    """Test formatting utility functions."""
    
    @pytest.mark.parametrize("value,expected", [
        (1000, "1,000"),
        (1000000, "1,000,000"),
        (999, "999"),
        (0, "0"),
        (-1000, "-1,000"),
    ])
    def test_format_number_with_thousands_separator(self, value, expected):
        """Test number formatting with comma separators."""
        result = format_number(value)
        assert result == expected
    
    def test_format_currency_includes_isk_suffix(self):
        """Test currency formatting includes ISK suffix by default."""
        result = format_currency(1000.50)
        assert result == "1,000.50 ISK"
    
    def test_format_currency_handles_none(self):
        """Test currency formatting handles None gracefully."""
        result = format_currency(None)
        assert result == "N/A"
```

---

## Common Pitfalls to Avoid

### Don't: Over-mock Everything

```python
# Bad: Mocking too much loses value
def test_manufacturing_with_all_mocks(mocker):
    mock_sde = mocker.Mock()
    mock_market = mocker.Mock()
    mock_sde.get_blueprint.return_value = mocker.Mock()
    # ... endless mocking ...
    # What are we even testing at this point?
```

### Do: Use Real Objects When Possible

```python
# Good: Use real objects for integration-style tests
def test_manufacturing_with_real_data():
    sde_manager = SDEManager()  # Real instance
    market_manager = MarketDataManager()  # Real instance
    service = ManufacturingService(sde_manager, market_manager)
    
    result = service.calculate_manufacturing_cost(blueprint_id=681, runs=1)
    assert result["total_cost"] > 0
```

### Don't: Test Implementation Details

```python
# Bad: Testing private methods
def test_internal_calculation_method():
    service = ManufacturingService()
    result = service._calculate_internal_thing()  # Don't test private methods
```

### Do: Test Public Interface

```python
# Good: Test public API behavior
def test_manufacturing_cost_calculation():
    service = ManufacturingService()
    result = service.calculate_manufacturing_cost(blueprint_id=681, runs=1)
    assert "total_cost" in result
    assert result["total_cost"] > 0
```

### Don't: Write Brittle Tests

```python
# Bad: Too specific, will break on minor changes
def test_error_message_exact_text():
    with pytest.raises(ValueError) as exc:
        do_thing()
    assert str(exc.value) == "Error: Invalid input at line 42, column 7"  # Too specific!
```

### Do: Test Behavior, Not Strings

```python
# Good: Test that error is raised and contains key info
def test_error_contains_relevant_info():
    with pytest.raises(ValueError) as exc:
        do_thing()
    assert "Invalid input" in str(exc.value)  # Flexible, still useful
```

---

## MVP Testing Checklist

Before release, ensure:

- [ ] **Data loaders work**: Can parse SDE files without crashes
- [ ] **Critical calculations are correct**: Manufacturing costs, profit margins
- [ ] **Error handling is graceful**: Bad data doesn't crash the app
- [ ] **Happy path works end-to-end**: User can select item → see cost → see profit
- [ ] **Coverage on core business logic**: `src/core/` has >70% coverage
- [ ] **Known edge cases are handled**: Empty files, missing data, bad inputs

**Don't need for MVP**:

- 100% coverage
- UI tests
- Performance tests
- Mutation testing
- Property-based testing (unless you want to use Hypothesis)

---

## Advanced Patterns (Optional)

These are **not required for MVP**, but useful to know:

### Mocking External Dependencies

If you need to mock (e.g., API calls):

```python
def test_with_mock_api(mocker):
    """Test using pytest-mock."""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"price": 1000}
    
    mocker.patch("requests.get", return_value=mock_response)
    
    result = fetch_price_from_api(item_id=123)
    assert result == 1000
```

### Testing Logging

Use `caplog` to verify log messages:

```python
def test_logs_warning_on_error(caplog):
    """Test that errors are logged."""
    parser = JSONLParser("bad_file.jsonl")
    
    with caplog.at_level(logging.WARNING):
        list(parser.parse())
    
    assert "Invalid JSON" in caplog.text
```

### Snapshot Testing

For complex output, consider snapshot testing:

```python
# Install: uv add syrupy
def test_blueprint_serialization(snapshot):
    """Test blueprint serialization output matches snapshot."""
    blueprint = load_blueprint(681)
    output = blueprint.model_dump_json(indent=2)
    
    assert output == snapshot
```

---

## Resources

- **pytest docs**: <https://docs.pytest.org/>
- **pytest-cov docs**: <https://pytest-cov.readthedocs.io/>
- **Our example**: `tests/test_utils/test_jsonl_parser.py` - 53 tests, 100% coverage

---

## Quick Reference

| Task | Command |
|------|---------|
| Run all tests | `uv run pytest` |
| Run with coverage | `uv run pytest --cov=src --cov-report=term-missing` |
| Run specific file | `uv run pytest tests/test_utils/test_jsonl_parser.py` |
| Run specific test | `uv run pytest tests/test_utils/test_jsonl_parser.py::test_name` |
| Run in verbose mode | `uv run pytest -v` |
| Run and stop on first failure | `uv run pytest -x` |
| Show print statements | `uv run pytest -s` |
| Run tests matching pattern | `uv run pytest -k "pattern"` |

---

## Final Notes

**Testing is about confidence, not perfection.**

For this project's MVP phase:

1. **Prioritize critical paths** (data loading, calculations)
2. **Use real data** (EVE SDE samples)
3. **Keep tests simple** (avoid over-engineering)
4. **Document assumptions** (if you skip something, say why)
5. **Ship it** (better to have 70% coverage and a working app than 100% coverage and no release)

You can always add more tests later. Focus on what gives you confidence to ship.
