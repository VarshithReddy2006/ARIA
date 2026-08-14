# Contributing Guide

We welcome contributions to ARIA! Please follow these guidelines to set up your environment, write tests, and submit pull requests.

## Development Workflow

1. **Format & Style Checks**:
   Ruff is used for linting and formatting. Run the following checks before committing code:
   ```bash
   ruff check .
   ruff format --check .
   ```

2. **Format Code Automatically**:
   ```bash
   ruff format .
   ruff check --fix .
   ```

3. **Running the Test Suite**:
   Run the full pytest suite to verify you did not introduce regressions:
   ```bash
   pytest tests/ -v
   ```
   > Always target `pytest tests/` explicitly — running bare `pytest` from the root will traverse `data/` and fail on import errors from cloned repositories.

---

## Coding Standards

- **Backward Compatibility**: Ensure 100% backward compatibility. Do not modify existing API routers or payload schemas.
- **Centralized Configuration**: Fetch all environment variables via `backend/settings.settings`. Do not write direct `os.environ.get()` calls in business logic.
- **Logging**: Use standard loggers `logging.getLogger(__name__)`. Do not use `print()` statements for diagnostic messages.
- **Middlewares**: Make sure new HTTP features are implemented as modular Starlette/FastAPI middlewares where possible.
