"""OS-owned exclusive lock: process death releases ownership automatically."""

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def agent_instance(identity, directory=None):
    directory = Path(directory) if directory is not None else Path.home() / ".netguardian" / "locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise RuntimeError("Agent lock directory must not be a symbolic link")
    if os.name != "nt" and directory.stat().st_mode & 0o077:
        raise RuntimeError("Agent lock directory must be private (mode 0700)")
    path = directory / (hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".lock")
    if path.is_symlink():
        raise RuntimeError("Agent lock file must not be a symbolic link")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as stream:
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "Cannot acquire agent lock; another instance may be running"
            ) from exc
        # Keep the same lock file: unlinking it would allow competing inode ownership.
        yield
