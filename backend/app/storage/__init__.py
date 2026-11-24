from __future__ import annotations

from functools import lru_cache

from app.config import StorageProvider, get_settings
from app.storage.base import ObjectStorage
from app.storage.local import LocalObjectStorage


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.storage_provider is StorageProvider.local:
        return LocalObjectStorage(settings.objects_dir)
    # The Supabase adapter is written in Outcome 10. Fail loudly instead of pretending.
    raise RuntimeError(f"storage provider {settings.storage_provider} is not implemented yet")
