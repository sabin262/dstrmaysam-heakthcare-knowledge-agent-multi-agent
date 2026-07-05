"""Compatibility facade for document ingestion."""

from .ingestion import job as _job

globals().update(
    {
        name: getattr(_job, name)
        for name in dir(_job)
        if not name.startswith("__")
    }
)
