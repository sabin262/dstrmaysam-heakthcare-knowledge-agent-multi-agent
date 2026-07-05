"""Compatibility alias for FastAPI application assembly."""

import sys

from .api import app as _app_module

sys.modules[__name__] = _app_module
