from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import time
import uuid

from .naming import transaction_token_for_target, validate_portable_path
from .ownership import OutputOwnershipError, read_owned_output
from .safe_tree import safe_remove_tree


WINDOWS_RENAME_RETRY_SECONDS = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0)
TRANSACTION_JOURNAL_SCHEMA = "x5crop_output_transaction_v1"


class OutputTransactionError(RuntimeError):
    pass


class RecoveryRequiredError(OutputTransactionError):
    pass


class TransactionState(str, Enum):
    PREPARED = "prepared"
    OLD_MOVED = "old_moved"
    NEW_PUBLISHED = "new_published"


@dataclass(frozen=True)
class TransactionPaths:
    target: Path
    token: str
    lock: Path
    journal: Path

    @classmethod
    def for_target(cls, target: Path) -> "TransactionPaths":
        resolved = target.resolve(strict=False)
        if not resolved.parent.is_dir():
            raise OutputTransactionError(
                f"Output parent does not exist: {resolved.parent}"
            )
        validate_portable_path(resolved)
        token = transaction_token_for_target(resolved)
        return cls(
            target=resolved,
            token=token,
            lock=resolved.parent / f".{token}.lock",
            journal=resolved.parent / f".{token}.transaction.json",
        )

    def staging(self, transaction_id: str) -> Path:
        return self.target.parent / f".{self.token}.new-{transaction_id}"

    def previous(self, transaction_id: str) -> Path:
        return self.target.parent / f".{self.token}.old-{transaction_id}"


@dataclass(frozen=True)
class TransactionJournal:
    transaction_id: str
    run_id: str
    target: str
    staging: str
    previous: str
    state: TransactionState

    def as_record(self) -> dict[str, str]:
        return {
            "schema": TRANSACTION_JOURNAL_SCHEMA,
            "transaction_id": self.transaction_id,
            "run_id": self.run_id,
            "target": self.target,
            "staging": self.staging,
            "previous": self.previous,
            "state": self.state.value,
        }


class OutputLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream = None

    def __enter__(self) -> "OutputLock":
        stream = self.path.open("a+b")
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        os.set_inheritable(stream.fileno(), False)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, PermissionError) as exc:
            stream.close()
            raise OutputTransactionError(
                f"Another X5 Crop invocation owns the output lock: {self.path}"
            ) from exc
        self._stream = stream
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def _write_journal(path: Path, journal: TransactionJournal) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(journal.as_record(), stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_journal(path: Path) -> TransactionJournal:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema") != TRANSACTION_JOURNAL_SCHEMA:
            raise ValueError("unknown transaction schema")
        return TransactionJournal(
            transaction_id=str(record["transaction_id"]),
            run_id=str(record["run_id"]),
            target=str(record["target"]),
            staging=str(record["staging"]),
            previous=str(record["previous"]),
            state=TransactionState(str(record["state"])),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RecoveryRequiredError(
            f"Output transaction journal is ambiguous; preserving all data: {path}"
        ) from exc


def _rename(source: Path, destination: Path) -> None:
    delays = WINDOWS_RENAME_RETRY_SECONDS if os.name == "nt" else (0.0,)
    final_error: OSError | None = None
    for delay in delays:
        if delay:
            time.sleep(delay)
        try:
            os.rename(source, destination)
            return
        except OSError as exc:
            final_error = exc
    assert final_error is not None
    raise final_error


class OutputTransaction:
    """Same-parent two-rename publication with journaled process recovery."""

    def __init__(self, target: Path) -> None:
        self.paths = TransactionPaths.for_target(target)
        self._lock: OutputLock | None = None

    def __enter__(self) -> "OutputTransaction":
        lock = OutputLock(self.paths.lock)
        lock.__enter__()
        self._lock = lock
        try:
            self.recover()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        lock = self._lock
        self._lock = None
        if lock is not None:
            lock.__exit__(exc_type, exc, traceback)

    def create_staging(self, run_id: str) -> tuple[str, Path]:
        if not run_id:
            raise OutputTransactionError("staging requires a run id")
        transaction_id = uuid.uuid4().hex
        staging = self.paths.staging(transaction_id)
        staging.mkdir()
        return transaction_id, staging

    def publish(self, transaction_id: str, staging: Path, run_id: str) -> None:
        expected_staging = self.paths.staging(transaction_id)
        previous = self.paths.previous(transaction_id)
        if staging.resolve(strict=False) != expected_staging:
            raise OutputTransactionError("staging path does not match transaction id")
        owned_new = read_owned_output(staging)
        if owned_new.run_id != run_id:
            raise OutputTransactionError("staging manifest belongs to another run")
        if self.paths.target.exists():
            read_owned_output(self.paths.target)
        if previous.exists():
            raise RecoveryRequiredError(
                f"Previous-output path already exists; preserving data: {previous}"
            )
        journal = TransactionJournal(
            transaction_id=transaction_id,
            run_id=run_id,
            target=str(self.paths.target),
            staging=str(staging),
            previous=str(previous),
            state=TransactionState.PREPARED,
        )
        _write_journal(self.paths.journal, journal)
        old_moved = False
        try:
            if self.paths.target.exists():
                _rename(self.paths.target, previous)
                old_moved = True
            journal = TransactionJournal(
                **{**journal.__dict__, "state": TransactionState.OLD_MOVED}
            )
            _write_journal(self.paths.journal, journal)
            _rename(staging, self.paths.target)
            journal = TransactionJournal(
                **{**journal.__dict__, "state": TransactionState.NEW_PUBLISHED}
            )
            _write_journal(self.paths.journal, journal)
            published = read_owned_output(self.paths.target)
            if published.run_id != run_id:
                raise OutputTransactionError("published target identity changed")
        except Exception:
            if old_moved and not self.paths.target.exists() and previous.exists():
                try:
                    _rename(previous, self.paths.target)
                except OSError as rollback_error:
                    raise RecoveryRequiredError(
                        "Output publish and rollback both failed; preserving all data"
                    ) from rollback_error
            raise
        if previous.exists():
            read_owned_output(previous)
            safe_remove_tree(previous)
        self.paths.journal.unlink()

    def recover(self) -> None:
        parent = self.paths.target.parent
        new_candidates = tuple(parent.glob(f".{self.paths.token}.new-*"))
        old_candidates = tuple(parent.glob(f".{self.paths.token}.old-*"))
        if not self.paths.journal.exists():
            if new_candidates or old_candidates:
                raise RecoveryRequiredError(
                    "Internal transaction directories exist without a journal; "
                    "preserving all data"
                )
            return
        journal = _read_journal(self.paths.journal)
        staging = Path(journal.staging)
        previous = Path(journal.previous)
        if (
            Path(journal.target) != self.paths.target
            or staging != self.paths.staging(journal.transaction_id)
            or previous != self.paths.previous(journal.transaction_id)
            or set(new_candidates) - {staging}
            or set(old_candidates) - {previous}
        ):
            raise RecoveryRequiredError(
                "Output transaction paths are ambiguous; preserving all data"
            )

        target_exists = self.paths.target.exists()
        staging_exists = staging.exists()
        previous_exists = previous.exists()
        if journal.state == TransactionState.PREPARED:
            if target_exists and staging_exists and not previous_exists:
                read_owned_output(self.paths.target)
                read_owned_output(staging)
                safe_remove_tree(staging)
                self.paths.journal.unlink()
                return
            if not target_exists and staging_exists and not previous_exists:
                owned = read_owned_output(staging)
                if owned.run_id != journal.run_id:
                    raise RecoveryRequiredError("Prepared staging identity is ambiguous")
                _rename(staging, self.paths.target)
                self.paths.journal.unlink()
                return
        elif journal.state == TransactionState.OLD_MOVED:
            if not target_exists and staging_exists and previous_exists:
                read_owned_output(previous)
                _rename(previous, self.paths.target)
                read_owned_output(staging)
                safe_remove_tree(staging)
                self.paths.journal.unlink()
                return
        elif journal.state == TransactionState.NEW_PUBLISHED:
            if target_exists and not staging_exists:
                owned = read_owned_output(self.paths.target)
                if owned.run_id != journal.run_id:
                    raise RecoveryRequiredError("Published target identity is ambiguous")
                if previous_exists:
                    read_owned_output(previous)
                    safe_remove_tree(previous)
                self.paths.journal.unlink()
                return
        raise RecoveryRequiredError(
            "Output transaction state is ambiguous; preserving target, new, old, and journal"
        )
