from collections.abc import Iterator
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, TypeVar

from pydantic import BaseModel


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding=encoding, newline="") as tmp:
        temporary = Path(tmp.name)
        try:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    write_text(path, encode(value) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


T = TypeVar("T", bound=BaseModel)

def read_rows(path: Path, model: type[T]) -> list[T]:
    with path.open(encoding="utf-8") as data:
        return [model.model_validate_json(line) for line in data if line.strip()]


def write_rows(path: Path, rows: list[BaseModel]) -> None:
    write_text(path, "".join(row.model_dump_json() + "\n" for row in rows))


@contextmanager
def run_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".pipeline.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield
