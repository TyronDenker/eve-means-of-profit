# Technical Specifications

This document provides technical context for developers working on **EVE Means of Profit**.

## System Architecture

### High-Level Overview

```text
Data Layer (src/data/)
    ↓
Models Layer (src/models/)
    ↓
Services Layer (src/core/)
    ↓
UI Layer (src/ui/)
```

### Module Responsibilities

#### `src/data/` - Data Access Layer

**Purpose**: Load and manage EVE SDE and market data.

- **`clients/`**: External data source clients (not yet implemented)
  - `esi_client.py`: ESI API client
  - `sde_client.py`: Provide up to date SDE data access
  - `fuzzwork_client.py`: Fuzzwork market data client
  - `everef_client.py`: EVE Ref data client
- **`loaders/`**: Parse raw data files
  - `sde_jsonl.py`: Loads EVE SDE from JSONL files
  - `fuzzwork_csv.py`: Loads market prices from CSV
- **`managers/`**: Provide cached, optimized access to data
  - `sde.py`: `SDEManager` - In-memory cache with O(1) lookups and indices
  - `market.py`: `MarketDataManager` - Market price queries
- **`repositories/`**: Database abstraction (currently SQLite)
  - `sqlite_manager.py`: SQLite connection and query management

**Key Design Principle**: Lazy loading + caching. Data is loaded on first access and cached in memory.

#### `src/models/` - Domain Models

**Purpose**: Pydantic models representing EVE game entities.

- **`eve/`**: EVE Online domain models
  - `type.py`: Item types (ships, modules, resources)
  - `blueprint.py`: Blueprint definitions and activities
  - `dogma.py`: Dogma attributes, effects (game mechanics)
  - `group.py`, `category.py`: Type taxonomy
  - `market_group.py`: Market organization
  - `market_price.py`: Price data structures
  - `type_material.py`: Reprocessing materials
- **`ui/`**: UI-specific models

**Key Design Principle**: Immutable data classes using Pydantic for validation.

#### `src/core/` - Business Logic Services

**Purpose**: High-level operations and calculations.

- `type_service.py`: Type queries and enrichment
- `blueprint_service.py`: Blueprint queries and calculations
- `manufacturing_service.py`: Manufacturing cost/profit calculations
- `market_service.py`: Market operations
- `price_analyzer.py`: Price analysis and statistics

**Key Design Principle**: Services depend on managers (data layer), not directly on loaders. Services are stateless.

#### `src/ui/` - User Interface

**Purpose**: PyQt6 GUI application.

- `main_window.py`: Main application window with tabs
- **`widgets/`**: Custom UI components
  - Types browser
  - Manufacturing calculator

**Key Design Principle**: UI depends on services, passes user input to services, displays results.

---

## Data Flow Example

**Manufacturing Cost Calculation:**

1. User selects blueprint in UI (`ManufacturingWindow`)
2. UI calls `ManufacturingService.calculate_manufacturing_cost()`
3. Service queries `SDEManager` for blueprint data
4. Service queries `MarketDataManager` for material prices
5. Service queries `ESIClient` for System Cost Index (SCI)
6. Service performs calculations (ME/TE bonuses, structure bonuses, taxes)
7. Service returns `ManufacturingCostBreakdown` typed dict
8. UI displays results in tables/labels

---

## Development Guidelines

### Adding a New Service

1. Create service class in `src/core/`
2. Inject `SDEManager` and/or `MarketDataManager` in `__init__`
3. Define public methods with typed return values (use `TypedDict` for complex returns)
4. Register service in `main.py` and pass to UI components

### Adding a New EVE Data Model

1. Create Pydantic model in `src/models/eve/`
2. Add loader method in `src/data/loaders/sde_jsonl.py`
3. Add cache in `SDEManager` (`src/data/managers/sde.py`)
4. Add public query methods in `SDEManager`

### Working with SDE Data

- **SDE files**: `data/sde/*.jsonl` (one JSON object per line)
- **Schema**: Follows CCP's SDE YAML structure (converted to JSON)
- **Lazy loading**: Use `SDEManager` methods, don't load files directly
- **Indices**: `SDEManager` builds O(1) lookup hashmaps (e.g., types by group)

### Database Interactions

- Use `src/data/repositories/sqlite_manager.py` for SQLite queries
- Currently underutilized (most data is in-memory)
- Future: Persist user configurations, cached market data

---

## Onboarding Checklist

- [ ] Install Python 3.13+
- [ ] Install `uv` package manager
- [ ] Clone repository and run `uv sync`
- [ ] Run `uv run -m main` to verify setup
- [ ] Read `README.md` for project overview
- [ ] Review `src/data/` to understand data access patterns
- [ ] Review `src/core/` to see business logic
- [ ] Explore `src/models/eve/` to understand EVE domain models
- [ ] Experiment with UI (Types Browser, Manufacturing Calculator)
- [ ] Identify an issue or feature to work on

---

## Design Principles

1. **Pragmatic MVP**: Speed over perfection, but keep debt visible
2. **Separation of Concerns**: Data → Models → Services → UI
3. **Type Safety**: Use Pydantic, type hints, and `TypedDict` where possible
4. **Lazy + Cached**: Load data on demand, cache in memory
5. **Open for Extension**: Easy to add new services, models, UI widgets
6. **Honest Communication**: Document shortcuts, acknowledge missing tests

---

## External Resources

- **EVE API Documentation**: [EVE Third Party Developers](https://developers.eveonline.com/)
- **Fuzzwork Market Data**: [Fuzzwork Market Data](https://market.fuzzwork.co.uk/api/)
- **EVE Ref**: [EVE Ref](https://docs.everef.net/)
