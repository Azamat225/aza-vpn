"""Durable atomic file operations used for state and secret material."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator

from aza_vpn.errors import StateError


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_text(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise StateError(f"Cannot atomically write {path}: {exc}") from exc


def atomic_write_json(path: Path, data: Any, mode: int = 0o600) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, content, mode=mode)


def atomic_replace(source: Path, destination: Path) -> None:
    try:
        os.replace(source, destination)
        _fsync_directory(destination.parent)
    except OSError as exc:
        raise StateError(f"Cannot atomically replace {destination}: {exc}") from exc


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise StateError(f"Required state file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"State file is not valid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise StateError(f"Cannot read state file {path}: {exc}") from exc


def replace_backup(source: Path, backup: Path, mode: int = 0o640) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{backup.name}.", dir=backup.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, mode)
        # Windows requires a writable descriptor for fsync/FlushFileBuffers.
        with temporary.open("rb+") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, backup)
        _fsync_directory(backup.parent)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StateError(f"Cannot create backup {backup}: {exc}") from exc


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        os.chmod(path, 0o600)
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
