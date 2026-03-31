"""Backward-compatible re-export — prefer `profiles.application.profiles_service`."""

from __future__ import annotations

from src.modules.profiles.application.profiles_service import get_active_profile_bundle

__all__ = ["get_active_profile_bundle"]
