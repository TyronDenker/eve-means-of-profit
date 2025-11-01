# Technical Specifications

Architecture and system design documentation for **EVE Means of Profit**.

> **For development guidelines, testing, and workflow**, see [CONTRIBUTING.md](CONTRIBUTING.md)

## Table of Contents

- [System Architecture](#system-architecture)
- [Module Responsibilities](#module-responsibilities)
- [Data Flow](#data-flow)
- [Design Principles](#design-principles)
- [Known Technical Debt](#known-technical-debt)

---

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

## Design Principles

1. **Pragmatic MVP**: Speed over perfection, but keep debt visible
2. **Separation of Concerns**: Data → Models → Services → UI
3. **Type Safety**: Use Pydantic, type hints, and `TypedDict`
4. **Lazy + Cached**: Load data on demand, cache in memory
5. **Open for Extension**: Easy to add new services, models, UI widgets

---

## Known Technical Debt

### Missing Features

- **ESI Integration**: Not yet implemented (SCI hardcoded, no real-time data)
- **Database Usage**: SQLite barely used (most data in-memory)
- **Error Handling**: Minimal validation, needs improvement
- **Performance**: No optimization, caching is naive
- **Testing**: Low coverage outside critical paths
- **UI Polish**: Basic widgets, needs UX improvements

### Approximations & Shortcuts

- Manufacturing costs use Estimated Item Value (EIV) approximations
- System Cost Index (SCI) is manually configured, not fetched
- Alpha clone tax logic may not match in-game exactly
- Market data is static CSV, not real-time
- No blueprint research time calculations

### Future Improvements

- Integrate ESI API for real-time data
- Add database persistence for user configs and cache
- Improve error messages and input validation
- Add comprehensive logging
- Implement proper caching strategy (Redis/memcached)
- Add performance profiling and optimization
- Expand test coverage to >80%
- Build better UI components with Qt Designer

**For current development priorities, see [GitHub Issues](https://github.com/TyronDenker/eve-means-of-profit/issues)**

---

## Adding New Features

### Adding a New Service

1. Create service class in `src/core/`
2. Inject dependencies (`SDEManager`, `MarketDataManager`) in `__init__`
3. Define public methods with typed return values
4. Register in `main.py` and wire to UI

### Adding a New EVE Data Model

1. Create Pydantic model in `src/models/eve/`
2. Add loader in `src/data/loaders/sde_jsonl.py`
3. Add cache in `SDEManager`
4. Add query methods

### Working with SDE Data

- **Location**: `data/sde/*.jsonl` (one JSON per line)
- **Schema**: CCP's SDE YAML structure (converted to JSON)
- **Access**: Use `SDEManager` methods, not direct file loading
- **Performance**: `SDEManager` builds O(1) hashmaps

---

## External Resources

- [EVE API Documentation](https://developers.eveonline.com/) - EVE Third Party Developers
- [Fuzzwork Market API](https://market.fuzzwork.co.uk/api/) - Market data
- [EVE Ref](https://docs.everef.net/) - Reference data
- [CCP SDE Documentation](https://developers.eveonline.com/resource/resources) - Static data
