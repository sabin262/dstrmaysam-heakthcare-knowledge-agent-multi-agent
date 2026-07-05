"""Compatibility facade for chat history repositories."""

from .repositories import history as _history

globals().update(
    {
        name: getattr(_history, name)
        for name in dir(_history)
        if not name.startswith("__")
    }
)
