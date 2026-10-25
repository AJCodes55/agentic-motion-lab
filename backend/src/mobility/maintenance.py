"""Cooperative local locking between serving apps and offline maintenance."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat


@contextmanager
def _lock(root: Path, exclusive: bool):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Maintenance requires an existing real data root')
    path = root / 'maintenance.lock'
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as error:
        raise ValueError('Unsafe maintenance lock') from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError('Unsafe maintenance lock')
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Data root is in use; stop the app and other maintenance first') from error
        try:
            if not exclusive and any((root / name).exists() for name in ('.cleanup-journal.json', '.cleanup-trash')):
                raise RuntimeError('Interrupted cleanup requires offline recovery before serving')
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def application_lock(root: Path):
    return _lock(root, exclusive=False)


def maintenance_lock(root: Path):
    return _lock(root, exclusive=True)
