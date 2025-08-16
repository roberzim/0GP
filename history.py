
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import json
import hashlib
import difflib
from typing import Any, Dict, Optional

def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)

def append_history(folder: Path, actor: str, action: str,
                   before: Optional[Dict[str, Any]], after: Dict[str, Any]) -> None:
    """Appende una riga JSON (JSONL) con metadati + diff unified tra stato precedente e successivo."""
    folder.mkdir(parents=True, exist_ok=True)
    hist = folder / "history.jsonl"
    ts = datetime.now().isoformat(timespec="seconds")
    before_str = _pretty(before) if before is not None else ""
    after_str = _pretty(after)
    diff = "\n".join(difflib.unified_diff(
        before_str.splitlines(), after_str.splitlines(),
        fromfile="before", tofile="after", lineterm=""
    ))
    row = {
        "timestamp": ts,
        "actor": actor or "system",
        "action": action,
        "before_hash": _sha256_text(before_str) if before is not None else None,
        "after_hash": _sha256_text(after_str),
        "diff": diff,
    }
    with hist.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
