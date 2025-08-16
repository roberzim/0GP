"""
Retention policy per i backup JSON con timestamp nella cartella pratica.

Strategie supportate:
- "simple": mantieni ultime N copie, opzionalmente non più vecchie di X giorni e/o entro Y MB.
- "tiered": rotazione a livelli (consigliata):
    * keep_last: sempre le ultime N copie
    * keep_days:  mantieni 1 copia al giorno per gli ultimi D giorni
    * keep_weeks: mantieni 1 copia a settimana per le ultime W settimane
    * keep_months: mantieni 1 copia al mese per gli ultimi M mesi

Esempio filename timestamp: {ID}_gp_DDMMYYYY_HHMMSS.json
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Iterable
from datetime import datetime, timedelta
import re, os, itertools

TIMESTAMP_RE = re.compile(r'^(?P<stem>.+)_gp_(?P<dt>\d{8}_\d{6})\.json$')  # es. 14082025_112233

@dataclass
class RetentionResult:
    kept: int
    deleted: int
    bytes_freed: int
    deleted_files: List[str]

def _parse_ts(name: str) -> Optional[datetime]:
    m = TIMESTAMP_RE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group('dt'), '%d%m%Y_%H%M%S')
    except Exception:
        return None

def _list_timestamp_backups(practice_dir: Path) -> List[Path]:
    return [p for p in practice_dir.glob('*_gp_*.json') if TIMESTAMP_RE.match(p.name)]

def _bucket_key_day(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d')

def _bucket_key_week(dt: datetime) -> str:
    # ISO week => YYYY-Www
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"

def _bucket_key_month(dt: datetime) -> str:
    return dt.strftime('%Y-%m')

def _select_newest_per_bucket(items: List[Tuple[Path, datetime, int]], bucket_fn, limit: int, already_kept: set) -> Iterable[Path]:
    """Ritorna al più 'limit' file (Path) mantenendo il più recente per bucket non ancora coperto."""
    if limit is None or limit <= 0:
        return []
    chosen = []
    seen = set()
    for p, dt, _sz in items:  # items è in ordine decrescente per dt
        b = bucket_fn(dt)
        if p in already_kept:  # già tenuto
            continue
        if b in seen:
            continue
        chosen.append(p)
        seen.add(b)
        if len(chosen) >= limit:
            break
    return chosen

def enforce_retention_for_practice(
    practice_dir: Path,
    keep_last: int = 7,
    keep_days: Optional[int] = None,
    max_megabytes: Optional[int] = None,
    dry_run: bool = False,
    # Tiered options (usate solo se strategy='tiered')
    strategy: str = "simple",
    keep_weeks: Optional[int] = None,
    keep_months: Optional[int] = None,
) -> RetentionResult:
    """Applica policy di retention alle copie timestamp nella cartella pratica.

    strategy='simple':
        - Tieni sempre le ultime 'keep_last'
        - Se keep_days è impostato, tieni anche tutte le copie degli ultimi 'keep_days' giorni
        - Se max_megabytes è impostato, limita lo spazio totale dei file tenuti

    strategy='tiered':
        - Tieni sempre le ultime 'keep_last'
        - Tieni 1 copia/giorno per 'keep_days' giorni
        - Tieni 1 copia/settimana per 'keep_weeks' settimane
        - Tieni 1 copia/mese per 'keep_months' mesi
      (i livelli non si sommano duplicità: un file può coprire più bucket)
    """
    practice_dir = Path(practice_dir)
    files = _list_timestamp_backups(practice_dir)
    items = []
    for p in files:
        dt = _parse_ts(p.name) or datetime.fromtimestamp(p.stat().st_mtime)
        items.append((p, dt, p.stat().st_size))
    # Ordina per data desc (più recente prima)
    items.sort(key=lambda t: t[1], reverse=True)

    keep_set = set()

    # Regola base: tieni sempre le ultime N
    for p, _dt, _sz in items[:max(keep_last or 0, 0)]:
        keep_set.add(p)

    if strategy == "simple":
        # Giorni recenti
        if keep_days is not None and keep_days >= 0:
            threshold = datetime.now() - timedelta(days=keep_days)
            for p, dt, _sz in items:
                if dt >= threshold:
                    keep_set.add(p)

        # Limite spazio totale (opzionale): se eccede, togli i più vecchi tra i tenuti
        if max_megabytes is not None and max_megabytes > 0:
            limit_bytes = max_megabytes * 1024 * 1024
            kept_sorted = [(p, dt, sz) for (p, dt, sz) in items if p in keep_set]
            current = sum(sz for _p, _dt, sz in kept_sorted)
            if current > limit_bytes:
                # rimuovi dai kept i più vecchi fino a rientrare
                for p, _dt, sz in reversed(kept_sorted):
                    if current <= limit_bytes:
                        break
                    if p in keep_set:
                        keep_set.remove(p)
                        current -= sz

    else:  # strategy == "tiered"
        now = datetime.now()

        # Giorni (1 per giorno)
        if keep_days is not None and keep_days > 0:
            chosen = _select_newest_per_bucket(items, _bucket_key_day, keep_days, keep_set)
            keep_set.update(chosen)

        # Settimane (1 per settimana)
        if keep_weeks is not None and keep_weeks > 0:
            chosen = _select_newest_per_bucket(items, _bucket_key_week, keep_weeks, keep_set)
            keep_set.update(chosen)

        # Mesi (1 per mese)
        if keep_months is not None and keep_months > 0:
            chosen = _select_newest_per_bucket(items, _bucket_key_month, keep_months, keep_set)
            keep_set.update(chosen)

        # Limite spazio totale opzionale (comportamento come simple)
        if max_megabytes is not None and max_megabytes > 0:
            limit_bytes = max_megabytes * 1024 * 1024
            kept_sorted = [(p, dt, sz) for (p, dt, sz) in items if p in keep_set]
            current = sum(sz for _p, _dt, sz in kept_sorted)
            if current > limit_bytes:
                for p, _dt, sz in reversed(kept_sorted):
                    if current <= limit_bytes:
                        break
                    if p in keep_set:
                        keep_set.remove(p)
                        current -= sz

    # Calcola cancellazioni
    to_delete = [p for (p, _dt, _sz) in items if p not in keep_set]

    deleted = 0
    bytes_freed = 0
    deleted_files: List[str] = []
    if not dry_run:
        for p in to_delete:
            try:
                sz = p.stat().st_size
                p.unlink(missing_ok=True)
                deleted += 1
                bytes_freed += sz
                deleted_files.append(str(p))
            except Exception:
                continue

    return RetentionResult(kept=len(keep_set), deleted=deleted, bytes_freed=bytes_freed, deleted_files=deleted_files)

@dataclass
class OrphanCleanupResult:
    removed: int
    bytes_freed: int
    removed_files: List[str]

def cleanup_orphan_backups(backups_dir: Path, practices_root: Path, dry_run: bool = False) -> OrphanCleanupResult:
    """Rimuove backup app {ID}_gp.json senza corrispondente cartella pratica."""
    backups_dir = Path(backups_dir)
    practices_root = Path(practices_root)
    removed = 0
    bytes_freed = 0
    removed_files: List[str] = []

    for p in backups_dir.glob('*_gp.json'):
        idp = p.name[:-7]  # rimuove '_gp.json'
        if not (practices_root / idp).exists():
            try:
                sz = p.stat().st_size
                if not dry_run:
                    p.unlink(missing_ok=True)
                removed += 1
                bytes_freed += sz
                removed_files.append(str(p))
            except Exception:
                continue
    return OrphanCleanupResult(removed=removed, bytes_freed=bytes_freed, removed_files=removed_files)

def enforce_retention_for_all(
    practices_root: Path,
    backups_dir: Path,
    keep_last: int = 7,
    keep_days: Optional[int] = None,
    max_megabytes: Optional[int] = None,
    dry_run: bool = False,
    strategy: str = "simple",
    keep_weeks: Optional[int] = None,
    keep_months: Optional[int] = None,
) -> Dict[str, RetentionResult]:
    """Applica la retention a tutte le pratiche sotto practices_root."""
    practices_root = Path(practices_root)
    results: Dict[str, RetentionResult] = {}
    for practice_dir in practices_root.iterdir():
        if practice_dir.is_dir():
            res = enforce_retention_for_practice(
                practice_dir, keep_last, keep_days, max_megabytes, dry_run,
                strategy=strategy, keep_weeks=keep_weeks, keep_months=keep_months
            )
            results[practice_dir.name] = res
    return results

if __name__ == "__main__":
    import argparse, json as _json
    ap = argparse.ArgumentParser(description="Retention per copie timestamp e cleanup backup orfani")
    ap.add_argument("--practices", type=Path, required=True, help="Cartella 'archivio/pratiche'")
    ap.add_argument("--backups", type=Path, required=True, help="Cartella 'archivio/backups_json'")
    ap.add_argument("--strategy", choices=["simple", "tiered"], default="tiered", help="Tipo di retention (default tiered)")
    ap.add_argument("--keep-last", type=int, default=3, help="Sempre conserva le ultime N copie")
    ap.add_argument("--keep-days", type=int, default=14, help="Tiered: giorni")
    ap.add_argument("--keep-weeks", type=int, default=8, help="Tiered: settimane")
    ap.add_argument("--keep-months", type=int, default=12, help="Tiered: mesi")
    ap.add_argument("--max-mb", type=int, default=None, help="Limite dimensione (MB) per le copie timestamp per pratica (opzionale)")
    ap.add_argument("--dry-run", action="store_true", help="Non cancellare realmente, stampa solo il piano")
    args = ap.parse_args()

    res_all = enforce_retention_for_all(
        args.practices, args.backups,
        keep_last=args.keep_last, keep_days=args.keep_days, max_megabytes=args.max_mb,
        dry_run=args.dry_run, strategy=args.strategy,
        keep_weeks=args.keep_weeks, keep_months=args.keep_months
    )
    orphans = cleanup_orphan_backups(args.backups, args.practices, args.dry_run)
    print(_json.dumps({
        "per_practice": {k: vars(v) for k, v in res_all.items()},
        "orphans": vars(orphans),
    }, ensure_ascii=False, indent=2))
