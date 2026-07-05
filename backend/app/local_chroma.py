"""Compatibility facade for local Chroma ingestion and retrieval."""

from .ingestion import local_chroma as _local_chroma

globals().update(
    {
        name: getattr(_local_chroma, name)
        for name in dir(_local_chroma)
        if not name.startswith("__")
    }
)
