"""Validated disk cache keyed by SHA-256 of canonical model input.

Filenames depend only on the input snapshot, as promised by the implementation
plan.  Each entry also carries a contract hash over the prompt, schema, model,
and effort.  A prompt or schema change therefore invalidates a same-input entry
instead of silently replaying output produced under an older contract.

Only successful model output is stored.  Deterministic fallback proposals are
never cached, because doing so would cause a later keyed run to mistake fallback
output for model output forever.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from recoup.domain.models import canonical_json

CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE_ROOT = Path("data/llm_cache")
_SAFE_NAMESPACE = re.compile(r"^[a-z0-9-]+$")
OutputModel = TypeVar("OutputModel", bound=BaseModel)


class CacheEntry(BaseModel):
    """Self-describing entry so committed cache drift is detectable."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    namespace: str
    input_sha256: str
    contract_sha256: str
    output: dict[str, Any]


@dataclass
class CacheStats:
    """Small operational surface used by tests and the CLI."""

    lookups: int = 0
    hits: int = 0
    misses: int = 0
    writes: int = 0
    invalid_entries: int = 0

    @property
    def hit_rate(self) -> float:
        """Fraction of lookups served from disk; zero when none occurred."""
        return self.hits / self.lookups if self.lookups else 0.0


def sha256_canonical(value: Any) -> str:
    """Hash a JSON-shaped value independently of dictionary insertion order."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ReasonerCache:
    """Read and atomically replace validated structured-output entries."""

    def __init__(self, root: Path = DEFAULT_CACHE_ROOT) -> None:
        self.root = root
        self.stats = CacheStats()

    def path_for(self, namespace: str, model_input: Any) -> Path:
        """Return the stable path for an input without touching the filesystem."""
        self._validate_namespace(namespace)
        return self.root / namespace / f"{sha256_canonical(model_input)}.json"

    def get(
        self,
        namespace: str,
        model_input: Any,
        *,
        contract: Any,
        output_type: type[OutputModel],
    ) -> OutputModel | None:
        """Return one valid, current entry or a cache miss."""
        self.stats.lookups += 1
        input_hash = sha256_canonical(model_input)
        path = self.path_for(namespace, model_input)
        if not path.exists():
            self.stats.misses += 1
            return None

        try:
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
            if (
                entry.schema_version != CACHE_SCHEMA_VERSION
                or entry.namespace != namespace
                or entry.input_sha256 != input_hash
                or entry.contract_sha256 != sha256_canonical(contract)
            ):
                self.stats.misses += 1
                self.stats.invalid_entries += 1
                return None
            output = output_type.model_validate(entry.output)
        except (OSError, ValueError, ValidationError, json.JSONDecodeError):
            self.stats.misses += 1
            self.stats.invalid_entries += 1
            return None

        self.stats.hits += 1
        return output

    def put(
        self,
        namespace: str,
        model_input: Any,
        output: BaseModel,
        *,
        contract: Any,
    ) -> bool:
        """Persist successful model output; return false if disk writing fails."""
        input_hash = sha256_canonical(model_input)
        path = self.path_for(namespace, model_input)
        entry = CacheEntry(
            schema_version=CACHE_SCHEMA_VERSION,
            namespace=namespace,
            input_sha256=input_hash,
            contract_sha256=sha256_canonical(contract),
            output=output.model_dump(mode="json"),
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                canonical_json(entry.model_dump(mode="json")) + "\n",
                encoding="utf-8",
                newline="",
            )
            temporary.replace(path)
        except OSError:
            return False
        self.stats.writes += 1
        return True

    @staticmethod
    def _validate_namespace(namespace: str) -> None:
        if not _SAFE_NAMESPACE.fullmatch(namespace):
            raise ValueError(f"unsafe cache namespace: {namespace!r}")
