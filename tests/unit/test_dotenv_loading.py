"""Verify that .env loading uses override=True.

AWS_SESSION_TOKEN rotates frequently. If override=True is missing, restarting the
app with a fresh .env will silently keep the old (expired) token from os.environ.
"""

from __future__ import annotations

import os
import tempfile

from dotenv import load_dotenv


def test_load_dotenv_override_replaces_existing_env_var() -> None:
    """load_dotenv(override=True) must overwrite vars already in os.environ."""
    key = "_TEST_DOTENV_OVERRIDE_VAR"
    os.environ[key] = "old_value"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(f"{key}=new_value\n")
            tmp_path = f.name
        load_dotenv(tmp_path, override=True)
        assert os.environ[key] == "new_value", (
            "load_dotenv(override=True) must replace the existing env var value; "
            "without override=True, expired AWS tokens survive app restart"
        )
    finally:
        os.environ.pop(key, None)
        os.unlink(tmp_path)


def test_load_dotenv_without_override_keeps_existing_env_var() -> None:
    """Confirms the pitfall: load_dotenv() without override=True silently keeps old values."""
    key = "_TEST_DOTENV_NO_OVERRIDE_VAR"
    os.environ[key] = "old_value"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(f"{key}=new_value\n")
            tmp_path = f.name
        load_dotenv(tmp_path, override=False)
        assert os.environ[key] == "old_value", (
            "Without override=True, load_dotenv must NOT replace an existing env var"
        )
    finally:
        os.environ.pop(key, None)
        os.unlink(tmp_path)
