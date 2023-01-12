"""SaveState file storage."""

from .savestate import SaveStateChecksumError, SaveStateError, SaveStateLoadError, open

__all__ = [
    "open",
    "SaveStateError",
    "SaveStateLoadError",
    "SaveStateChecksumError",
]
