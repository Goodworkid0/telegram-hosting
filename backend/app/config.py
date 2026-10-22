"""Centralized environment configuration.

Fail-closed: when ENVIRONMENT is unset or unrecognized we treat the app as
running in *production*. This guarantees that a misconfigured deployment (e.g.
the ENVIRONMENT var simply forgotten) can never accidentally unlock
development-only behaviour such as dev-login, arbitrary balance deposits, or
the interactive API docs.
"""
import os

# Load .env before reading any variable. This module is imported very early
# (before database.py runs its own load_dotenv), so without this the local-dev
# ENVIRONMENT=development in .env would be missed and we'd fail closed to prod.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Normalize once. Anything that isn't an explicit, recognized non-prod value is
# considered production.
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").strip().lower()

# Recognized non-production environments. Everything else (including unset,
# "staging", or any typo) -> production, so dev-only behaviour stays locked.
_NON_PROD = {"development", "dev", "local"}

IS_PRODUCTION = ENVIRONMENT not in _NON_PROD
