"""Compatibility facade for the agent package.

The implementation lives in :mod:`backend.app.agents.knowledge_agent`.
This module intentionally re-exports private helpers as well because existing
tests and integration code import a few of them directly.
"""

from .agents import knowledge_agent as _knowledge_agent

globals().update(
    {
        name: getattr(_knowledge_agent, name)
        for name in dir(_knowledge_agent)
        if not name.startswith("__")
    }
)
