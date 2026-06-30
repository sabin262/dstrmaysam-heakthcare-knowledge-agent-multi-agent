from pathlib import Path
import sys

_package_src = Path(__file__).resolve().parents[1] / "packages" / "healthcare_tools_core" / "src"
if _package_src.exists() and str(_package_src) not in sys.path:
    sys.path.insert(0, str(_package_src))

from healthcare_tools_core import deterministic_lookup as _core
from healthcare_tools_core.deterministic_lookup import *  # noqa: F401,F403

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))
