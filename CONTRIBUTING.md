# Contributing to EVE Means of Profit

Thank you for your interest in contributing! This guide covers everything you need to know about developing for this project.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [Code Quality Standards](#code-quality-standards)
- [Testing Guide](#testing-guide)
- [Pull Request Workflow](#pull-request-workflow)
- [CI/CD Pipeline](#cicd-pipeline)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- **Python 3.13+** (required)
- **[uv](https://github.com/astral-sh/uv)** package manager (recommended)
- **Git** with pre-commit hooks

### Setup

```cmd
REM Clone the repository
git clone https://github.com/TyronDenker/eve-means-of-profit
cd eve-means-of-profit

REM Create virtual environment and install all dependencies (including dev tools)
uv sync --all-groups

REM Set up pre-commit hooks (highly recommended)
uv run pre-commit install

REM Verify setup
uv run python -m main
```

---

## Development Environment

### Dependency Management with uv

This project uses **[uv](https://github.com/astral-sh/uv)** for dependency management with a clean separation:

- **Production dependencies** (`[project.dependencies]`): Shipped with the application
- **Development dependencies** (`[dependency-groups.dev]`): All dev tools (ruff, pytest, ty, pre-commit, pip-audit)

```cmd
REM Install production dependencies only
uv sync

REM Install all dependencies including dev tools (recommended for development)
uv sync --all-groups

REM Install only specific dependency groups
uv sync --group dev
```

### Modern Astral Toolchain

This project uses the **Astral ecosystem** for all code quality needs:

#### **Ruff** - All-in-one Python tool

- **Replaces**: Black, isort, flake8, pyupgrade, autoflake, and 60+ plugins
- **Speed**: 10-100x faster than traditional tools
- **Features**: Linting + formatting + import sorting
- **Config**: `pyproject.toml` → `[tool.ruff]`

#### **ty** - Next-gen type checker

- **Replaces**: mypy, pyright
- **Speed**: Ultra-fast (written in Rust)
- **Status**: Preview (non-blocking in CI)
- **Config**: `pyproject.toml` → `[tool.ty]`

### Running Quality Checks

```cmd
REM Format, lint, and fix imports (all at once!)
uv run ruff check . --fix
uv run ruff format .

REM Type check
uv run ty check src

REM Run all checks via pre-commit
uv run pre-commit run --all-files
```

## Code Quality Standards

### Automated Enforcement

Quality checks run automatically via:

1. **Pre-commit hooks** (local, before commit)
2. **GitHub Actions** (CI, on push/PR)
3. **Branch protection** (blocks merge if checks fail)

### What Gets Checked

**Ruff** - Linting, formatting, import sorting
**ty** - Type checking (preview, non-blocking)
**pytest** - All tests passing with coverage report
**pip-audit** - Security vulnerability scanning
**Standard hooks** - Trailing whitespace, YAML syntax, etc.

### Code Style Rules

- **Line length**: 88 characters
- **Quotes**: Double quotes (`"`)
- **Imports**: Sorted by Ruff's `I` rule (isort compatible)
- **Type hints**: Encouraged, checked by ty
- **Docstrings**: Required for public APIs

---

## Testing Guide

### Philosophy: Pragmatic Testing for MVP

**Target**: Ship ASAP with confidence, not perfection.

**Principles**:

- Test what matters (business logic, data processing, critical paths)
- Start simple (basic functionality first, edge cases second)
- Use real data (actual EVE SDE samples where possible)
- Don't overthink (80% coverage of critical code beats 100% of everything)

### Running Tests

```cmd
REM Run all tests
uv run pytest

REM Run with coverage report
uv run pytest --cov=src --cov-report=term-missing

REM Run specific test file
uv run pytest tests\test_utils\test_jsonl_parser.py

REM Run specific test class
uv run pytest tests\test_utils\test_jsonl_parser.py::TestBasicParsing

REM Run specific test
uv run pytest tests\test_utils\test_jsonl_parser.py::TestBasicParsing::test_parse_single_line_jsonl
```

### Test Structure

**File naming:**

- Test files: `test_<module_name>.py`
- Test classes: `Test<Functionality>`
- Test functions: `test_<specific_behavior>`

**Example structure:**

```python
"""Tests for my_module."""

import pytest
from src.my_module import MyClass


class TestBasicFunctionality:
    """Test basic operations."""

    def test_basic_behavior(self):
        """Test that MyClass does the basic thing.

        Given: A MyClass instance
        When: Calling the main method
        Then: Should return expected result
        """
        obj = MyClass()
        result = obj.do_thing()

        assert result == "expected"
```

### Testing Patterns

#### 1. Use Fixtures for Test Data

```python
@pytest.fixture
def simple_test_data() -> list[dict]:
    """Provide reusable test data."""
    return [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"},
    ]


def test_with_fixture(simple_test_data):
    """Test using fixture data."""
    assert len(simple_test_data) == 2
```

#### 2. Factory Fixtures for Dynamic Creation

```python
@pytest.fixture
def create_temp_file(tmp_path):
    """Factory fixture to create test files."""
    def _create(filename: str, content: str) -> Path:
        file_path = tmp_path / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path
    return _create


def test_with_factory(create_temp_file):
    """Test using factory fixture."""
    file = create_temp_file("test.txt", "content")
    assert file.exists()
```

#### 3. Parametrize for Multiple Scenarios

```python
@pytest.mark.parametrize("value,expected", [
    (1000, "1,000"),
    (1000000, "1,000,000"),
    (999, "999"),
])
def test_formatting(value, expected):
    """Test number formatting with multiple inputs."""
    result = format_number(value)
    assert result == expected
```

#### 4. Test Error Handling

```python
def test_handles_invalid_input():
    """Test that invalid input raises appropriate error.

    Given: Invalid input data
    When: Processing the input
    Then: Should raise ValueError with helpful message
    """
    with pytest.raises(ValueError) as exc_info:
        process_invalid_data()

    assert "Invalid input" in str(exc_info.value)
```

### What to Test (Priority)

#### Critical (Must Have)

1. **Data Parsers** (`src/data/parsers/`) - Parse SDE/CSV correctly
2. **Core Services** (`src/core/`) - Manufacturing costs, calculations
3. **Data Providers** (`src/data/providers/`) - Caching, lookups
4. **Data Clients** (`src/data/clients/`) - ESI interactions

#### Important (Should Have)

1. **Models** (`src/models/eve/`) - Pydantic validation
2. **Utilities** (`src/utils/`) - Formatting, config, parsers

#### Nice to Have (Can Wait)

1. **UI Components** (`src/ui/`) - Manual testing is fine for MVP

---

## Pull Request Workflow

### PR Requirements

Before merging, ensure:

- All CI checks pass (green checkmarks)
- Code is properly formatted and linted (Ruff)
- Type checking passes (ty)
- Tests pass with adequate coverage (≥60%)
- No merge conflicts with main
- At least one review

### Fixing Failed Checks

If CI fails:

1. Check logs in GitHub Actions
2. Run checks locally to reproduce
3. Fix issues and commit
4. Push changes (CI re-runs automatically)

### Merging a PR

- Utilize `rebase` while working on feature branches in order to maintain a clean history that explains the parts of your contribution.
- Squash should not be used in order to maintain individual commit history.
- Deciding if a `rebase` is required before merging should be determined by the reviewer.

```cmd
REM Fix all linting and formatting issues
ruff check . --fix
ruff format .

REM Fix type errors
ty check src

REM Re-run tests
pytest --cov=src

REM Commit and push
git add .
git commit -m "Fix CI issues"
git push
```

---

## CI/CD Pipeline

The GitHub Actions workflow runs on:

- **Push to main**: Full pipeline
- **Pull requests**: Full pipeline
- **Merge groups**: Main branch protection
- **Manual trigger**: Via GitHub Actions UI

### Pipeline Jobs

1. **Ruff** (Lint + Format)
   - Combined linting, formatting, and import sorting
   - Must pass for merge

2. **Type Check** (ty)
   - Next-gen type checker
   - Currently non-blocking (preview mode)

3. **Test Suite** (pytest)
   - All unit tests
   - Coverage report

### Viewing Results

- Go to [Actions tab](https://github.com/TyronDenker/eve-means-of-profit/actions)
- Click on workflow run
- Each job shows detailed logs
- Download artifacts (coverage reports, builds)

---

## Troubleshooting

### Pre-commit hooks not running

```cmd
REM Reinstall hooks
pre-commit uninstall
pre-commit install
```

### CI passes locally but fails on GitHub

- Check Python version (must be 3.13+)
- Ensure dependencies are up to date
- Clear pip cache: `pip cache purge` or `uv sync --force`
- Check for platform differences (Windows vs Linux)
 Focus on critical paths first

### Ruff or ty not found

```cmd
REM Ensure dev dependencies are installed
uv sync --all-groups

REM Always use 'uv run' to execute tools from the virtual environment
uv run ruff check .
uv run ty check src
```

---

## Additional Resources

- [TECHNICAL_SPECS.md](TECHNICAL_SPECS.md) - Architecture documentation
- [Ruff Documentation](https://docs.astral.sh/ruff/) - Linter and formatter
- [ty Documentation](https://docs.astral.sh/ty/) - Type checker
- [pytest Documentation](https://docs.pytest.org/) - Testing framework
- [Pre-commit Documentation](https://pre-commit.com/) - Git hooks

---

## MVP Development Philosophy

**Focus areas for MVP:**

1. Prioritize critical paths (data loading, calculations)
2. Use real data (EVE SDE samples)
3. Keep tests simple (avoid over-engineering)
4. Document assumptions and shortcuts
5. Ship it (70% coverage + working app > 100% coverage + no release)

**You can always add more tests later. Focus on what gives you confidence to ship.**

---

## Questions?

- Open an [issue](https://github.com/TyronDenker/eve-means-of-profit/issues)
- Start a [discussion](https://github.com/TyronDenker/eve-means-of-profit/discussions)
- Review existing code for patterns and examples

Thank you for contributing! 🚀
