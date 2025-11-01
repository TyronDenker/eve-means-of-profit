# EVE Means of Profit

[![CI](https://github.com/TyronDenker/eve-means-of-profit/workflows/CI/badge.svg)](https://github.com/TyronDenker/eve-means-of-profit/actions/workflows/python-app.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/type_checker-ty-blue.svg)](https://github.com/astral-sh/ty)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A fully featured EVE Online tool for asset tracking, manufacturing and trading analysis, currently in active MVP development.

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
- **Test coverage is growing** – See [TESTING_GUIDE.md](TESTING_GUIDE.md) for how to write tests.
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

See [TECHNICAL_SPECS.md](TECHNICAL_SPECS.md) for detailed architecture documentation and [TESTING_GUIDE.md](TESTING_GUIDE.md) for testing guidelines.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development environment setup
- Code quality standards (Ruff + ty)
- Testing guidelines and examples
- Pull request workflow
- CI/CD pipeline details

### Quick Contribution Guide

1. Fork and clone: `git clone https://github.com/TyronDenker/eve-means-of-profit`
2. Setup environment: `uv sync`
3. Setup hooks: `uv run pre-commit install`
4. Create branch: `git checkout -b feature/my-feature`
5. Make changes and test: `uv run pytest --cov=src`
6. Run checks: `uv run ruff check . --fix && uv run ruff format .`
7. Push and create PR

**For detailed guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md)**

### Areas Needing Help

- Test coverage (see [TESTING_GUIDE.md](TESTING_GUIDE.md))
- API integration with ESI, SDE and 3rd party services (Fuzzwork, EVE Ref)
- UI/UX improvements
- Refactoring and code quality enhancements
- Feature implementations
- Documentation

### Documentation

- [README.md](README.md) - Project overview and quick start
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development guide, testing, and workflow
- [TECHNICAL_SPECS.md](TECHNICAL_SPECS.md) - Architecture and system design

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
