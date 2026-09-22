"""gpconf -- runner for the GP/OMM conformance corpus (standard library only, Python 3.9+)."""

__version__ = "0.2.0"

from .tle import to_alpha5, from_alpha5, checksum  # noqa: F401
from .reference import read_file  # noqa: F401
