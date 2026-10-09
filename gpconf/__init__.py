"""gpconf, the GP/OMM conformance corpus: its runner (standard library only, Python 3.9+)."""

__version__ = "0.6.2"

from .tle import to_alpha5, from_alpha5, checksum  # noqa: F401
from .reference import read_file  # noqa: F401
