import hashlib
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from v10.time import utc_now

from .models import AdvisoryLock


def lock_key_int64(value: str) -> int:
    digest = hashlib.sha256(str(value).encode("utf-8")).digest()[:8]
    number = int.from_bytes(digest, "big", signed=False)
    return number % (2**63 - 1)


def lock_key_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:40]


class LockNotAcquired(RuntimeError):
    pass


class AdvisoryLockManager:
    def __init__(self, session: Session, lock_name: str, owner: str | None = None):
        self.session = session
        self.lock_name = lock_name
        self.owner = owner or f"pid-{os.getpid()}"
        self.acquired = False
        self._postgres_key = lock_key_int64(lock_name)
        self._text_key = lock_key_text(lock_name)

    def acquire(self) -> bool:
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            acquired = self.session.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": self._postgres_key}).scalar()
            self.acquired = bool(acquired)
            return self.acquired
        existing = self.session.scalar(select(AdvisoryLock).where(AdvisoryLock.lock_key == self._text_key))
        if existing:
            return False
        self.session.add(AdvisoryLock(lock_key=self._text_key, owner=self.owner, acquired_at=utc_now()))
        try:
            self.session.flush()
            self.acquired = True
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def release(self) -> None:
        if not self.acquired:
            return
        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self._postgres_key})
        else:
            self.session.execute(delete(AdvisoryLock).where(AdvisoryLock.lock_key == self._text_key, AdvisoryLock.owner == self.owner))
            self.session.flush()
        self.acquired = False

    def __enter__(self) -> "AdvisoryLockManager":
        if not self.acquire():
            raise LockNotAcquired(f"lock already held: {self.lock_name}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


@contextmanager
def advisory_lock(session: Session, lock_name: str, owner: str | None = None) -> Iterator[bool]:
    manager = AdvisoryLockManager(session, lock_name, owner=owner)
    acquired = manager.acquire()
    try:
        yield acquired
    finally:
        manager.release()

