# EVE Means of Profit

A profit analysis tool for EVE Online industry and manufacturing, currently in active MVP development.

## Quick Start

### Prerequisites

- **Python 3.13+** (required)
- **[uv](https://github.com/astral-sh/uv)** package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/TyronDenker/eve-means-of-profit
cd eve-means-of-profit

# Create virtual environment and install dependencies
uv sync
```

### Running the Application

```bash
uv run python -m main
```

The application will:

1. Load EVE SDE (Static Data Export) from `data/sde/*.jsonl`
2. Load market data from `data/fuzzwork/aggregatecsv.csv`
3. Launch the PyQt6 GUI with a types browser and manufacturing calculator

## Project Status

### MVP Phase - Active Development

This project is being rapidly developed to get a working minimum viable product. As such:

- **Business logic may have shortcuts** – Some calculations are approximations or use hardcoded defaults
- **Design patterns vary** – Some corners might have been cut, which should be avoided and rapidly fixed in future iterations.
- **No test coverage** – Tests are planned but not yet implemented, should be done ASAP.
- **Data validation is minimal** – Input sanitization and error handling need improvement.
- **Performance not optimized** – Caching and query optimization are functional but not tuned.

## Architecture Overview

```text
src/
├── core/        # Business logic services
├── data/        # Data loading and management
├── models/      # EVE domain models (blueprints, types, dogma)
├── ui/          # PyQt6 user interface
└── utils/       # Utility functions, config, parsers

```

See [TECHNICAL_SPECS.md](TECHNICAL_SPECS.md) for detailed architecture documentation.

## Contributing

This is an open-source project. Contributions are welcome!

### Guidelines

- **Code style**: Follow existing patterns where they exist, use your best judgment elsewhere, utilize ruff for formatting.
- **Commit messages**: Keep them descriptive
- **Pull requests**: Small, focused PRs are easier to review
- **Issues**: Report bugs or suggest features via GitHub Issues

### Areas Needing Help

- Test coverage (pytest, unittest)
- API integration with ESI, SDE and 3rd party services (Fuzzwork, EVE Ref)
- UI/UX improvements
- Refactoring and code quality enhancements
- Feature implementations
- Documentation

## Data Sources

- **SDE (Static Data Export)**: EVE's official game data in JSONL format (`data/sde/`)
- **ESI (EVE Swagger Interface)**: User and game data API (not yet integrated)
- **Fuzzwork Market Data**: Market prices CSV (`data/fuzzwork/aggregatecsv.csv`)

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE.md](LICENSE.md) file for details.

## Known Issues

- Manufacturing cost calculations use approximations for Estimated Item Value (EIV)
- System Cost Index (SCI) is manually configured, not fetched from ESI
- Alpha clone tax logic may not match in-game exactly
- Market data is static (CSV), not real-time
- SDE data is loaded from local files, not updated automatically
See [TECHNICAL_SPECS.md](TECHNICAL_SPECS.md) for a detailed list of known technical debt and missing features.
