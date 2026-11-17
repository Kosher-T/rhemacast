"""
core/theme_catalog.py

The theme selector's one in-memory store, keyed by permanent ID.

ID and label are separate things:

- **ID** is the file name without `.json` (`default_typewriter`). It is the
  combo option's value, the loader key, the key saved settings use, and the
  key every other reference in the app uses. It never changes.
- **label** is display text only (`Standard — Typewriter`). Editing it never
  renames or moves the file.

The catalog is rebuilt from the loader at start-up and then kept current from
two sources: the designer typing a label (``set_label``) and files changing on
disk (``sync_from_disk``). Both paths write to this one store, so the dropdown
cannot hold a stale second copy.

Files: ``sync_from_disk`` compares content hashes, keeps the last good entry
when a file stops parsing, drops entries whose file disappeared, and ignores
the app's own writes (recognised by the hash ``note_written`` recorded).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Optional

import core.theme_loader as theme_loader

#: Matches the schema's label limit (core/theme_schema.py).
MAX_LABEL = 120
#: Matches the schema's description limit.
MAX_DESCRIPTION = 500

_SEPARATORS = re.compile(r"[_\-]+")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ThemeEntry:
    """Everything the selector needs about one theme."""

    id: str
    name: str
    path: Path
    kind: str
    raw_label: str = ""
    description: str = ""
    sort_order: Optional[float] = None
    label: str = ""
    duplicate: bool = False
    stale: bool = False
    warning: str = ""

    @property
    def suffix(self) -> str:
        """The muted ID shown when two themes share a label."""
        return f" ({self.id})" if self.duplicate else ""


@dataclass(frozen=True)
class FileChange:
    """One file the catalog changed during a disk sync."""

    theme_id: str
    path: Path
    action: str  # "added" | "updated" | "removed" | "invalid"
    detail: str = ""


# ─── label rules ─────────────────────────────────────────────────────────────

def prettify_id(theme_id: str) -> str:
    """`default_typewriter` → `Default Typewriter`.

    The fallback display name when a theme has no label, and the placeholder
    the designer's empty label field shows while the user is typing.
    """
    text = _SEPARATORS.sub(" ", str(theme_id or ""))
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return "Untitled"
    return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))


def clean_label(value) -> str:
    """A theme's raw label exactly as authored, trimmed; "" when absent."""
    if not isinstance(value, str):
        return ""
    return _WHITESPACE.sub(" ", value).strip()[:MAX_LABEL]


def clean_description(value) -> str:
    """A one-line description: newlines collapse so the row stays one line."""
    if not isinstance(value, str):
        return ""
    return _WHITESPACE.sub(" ", value).strip()[:MAX_DESCRIPTION]


def resolve_label(raw_label, theme_id: str) -> str:
    """Display label: the theme's label, else the prettified file name."""
    return clean_label(raw_label) or prettify_id(theme_id)


def parse_sort_order(value) -> Optional[float]:
    """A numeric `sort_order`, or None (absent, bool, garbage)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def sort_key(entry: ThemeEntry) -> tuple:
    """Explicit `sort_order` themes lead; everything else is A→Z by label."""
    if entry.sort_order is None:
        return (1, 0.0, entry.label.casefold(), entry.id)
    return (0, entry.sort_order, entry.label.casefold(), entry.id)


def build_entry(theme_id: str, name: str, path: Path, kind: str,
                theme: dict) -> ThemeEntry:
    """One entry from a raw theme dict (the shape the loader stores)."""
    theme = theme if isinstance(theme, dict) else {}
    raw_label = clean_label(theme.get("label"))
    return ThemeEntry(
        id=str(theme_id),
        name=str(name),
        path=Path(path),
        kind=str(kind),
        raw_label=raw_label,
        description=clean_description(theme.get("description")),
        sort_order=parse_sort_order(theme.get("sort_order")),
        label=resolve_label(raw_label, theme_id),
    )


def content_hash(text: str) -> str:
    """Stable digest of a file's text, used to ignore the app's own writes."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ─── catalog ─────────────────────────────────────────────────────────────────

class ThemeCatalog:
    """In-memory theme entries keyed by permanent ID."""

    def __init__(self) -> None:
        self._entries: dict[str, ThemeEntry] = {}
        # file path -> last content hash we stored
        self._hashes: dict[str, str] = {}
        # file path -> hash of the bytes this app wrote (own-save marker)
        self._owned: dict[str, str] = {}

    # ── reads ────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, theme_id: object) -> bool:
        return theme_id in self._entries

    def ids(self) -> list[str]:
        return list(self._entries)

    def get(self, theme_id: str) -> Optional[ThemeEntry]:
        return self._entries.get(str(theme_id))

    def by_name(self, name: str) -> Optional[ThemeEntry]:
        """Find an entry by loader key (legacy callers pass names)."""
        for entry in self._entries.values():
            if entry.name == name:
                return entry
        return None

    def by_path(self, path: Path) -> Optional[ThemeEntry]:
        key = Path(path)
        for entry in self._entries.values():
            if entry.path == key:
                return entry
        return None

    def resolve(self, theme_id_or_name: str) -> Optional[ThemeEntry]:
        """Accept an ID or a legacy loader name."""
        if not theme_id_or_name:
            return None
        entry = self.get(theme_id_or_name)
        return entry if entry is not None else self.by_name(theme_id_or_name)

    def entries(self) -> list[ThemeEntry]:
        """Options in display order: `sort_order` first, then label A→Z."""
        return sorted(self._entries.values(), key=sort_key)

    # ── writes ───────────────────────────────────────────────────────────────

    def upsert(self, entry: ThemeEntry) -> None:
        self._entries[entry.id] = entry
        self._recompute_duplicates()

    def remove(self, theme_id: str) -> Optional[ThemeEntry]:
        entry = self._entries.pop(str(theme_id), None)
        if entry is not None:
            self._hashes.pop(str(entry.path), None)
            self._owned.pop(str(entry.path), None)
            self._recompute_duplicates()
        return entry

    def set_label(self, theme_id: str, raw_label: str) -> bool:
        """Live label edit (per keystroke). Returns True when it changed.

        An empty label is stored as empty: the display falls back to the
        prettified ID, and the save path drops the key instead of writing
        `"label": ""`.
        """
        entry = self.get(theme_id)
        if entry is None:
            return False
        cleaned = clean_label(raw_label)
        if cleaned == entry.raw_label:
            return False
        self._entries[entry.id] = replace(
            entry,
            raw_label=cleaned,
            label=resolve_label(cleaned, entry.id),
            stale=entry.stale,
            warning=entry.warning,
        )
        self._recompute_duplicates()
        return True

    def note_written(self, path: Path, theme: dict, text: str) -> ThemeEntry:
        """Record the app's own save so the watcher ignores its echo."""
        path = Path(path)
        digest = content_hash(text)
        self._hashes[str(path)] = digest
        self._owned[str(path)] = digest
        entry = self.by_path(path)
        theme_id = entry.id if entry is not None else path.stem
        name = theme_loader.theme_name_for(theme, path)
        refreshed = build_entry(
            theme_id, name, path, theme_loader.theme_kind_for(path), theme)
        self._entries[refreshed.id] = refreshed
        self._recompute_duplicates()
        return refreshed

    def mark_stale(self, theme_id: str, message: str) -> Optional[ThemeEntry]:
        """Keep the last good entry but flag it (invalid JSON on disk)."""
        entry = self.get(theme_id)
        if entry is None:
            return None
        flagged = replace(entry, stale=True, warning=str(message or ""))
        self._entries[flagged.id] = flagged
        return flagged

    # ── disk sync ────────────────────────────────────────────────────────────

    def load(self) -> list[FileChange]:
        """Initial fill straight from the loader's file index."""
        return self.sync_from_disk(theme_loader.iter_theme_files())

    def sync_from_disk(self, files: Iterable[Path]) -> list[FileChange]:
        """Reconcile the store with the theme files on disk.

        Reads only files that are new or whose content hash changed. A file
        that stops parsing keeps its last good entry (flagged stale); a file
        that disappears is removed; a file this app just wrote is skipped
        (its bytes are already in the store). Loader caches follow the same
        decisions so the rest of the app sees exactly what the dropdown says.
        """
        files = [Path(path) for path in files]
        present = {str(path) for path in files}
        changes: list[FileChange] = []

        for theme_id, entry in list(self._entries.items()):
            if str(entry.path) in present:
                continue
            self._entries.pop(theme_id, None)
            self._hashes.pop(str(entry.path), None)
            self._owned.pop(str(entry.path), None)
            theme_loader.forget_theme_file(entry.path)
            changes.append(FileChange(theme_id, entry.path, "removed"))

        for path in files:
            key = str(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                # A sync tool may be mid-replace; the next signal retries.
                continue
            digest = content_hash(text)
            if self._hashes.get(key) == digest:
                continue
            self._hashes[key] = digest
            if self._owned.pop(key, None) == digest:
                # Our own write: the store already holds these exact bytes.
                continue

            try:
                theme = json.loads(text)
                if not isinstance(theme, dict):
                    raise ValueError("theme root is not an object")
            except (TypeError, ValueError) as exc:
                entry = self.by_path(path)
                if entry is None:
                    # A brand-new unparsable file has no good version to keep;
                    # it appears once it parses.
                    changes.append(FileChange(
                        path.stem, path, "invalid", str(exc)))
                    continue
                self.mark_stale(entry.id, str(exc))
                changes.append(FileChange(
                    entry.id, path, "invalid", str(exc)))
                continue

            existed = self.by_path(path) is not None
            name = theme_loader.update_theme_from_disk(path, theme)
            entry = build_entry(
                path.stem, name, path, theme_loader.theme_kind_for(path), theme)
            self._entries[entry.id] = entry
            changes.append(FileChange(
                entry.id, path, "updated" if existed else "added"))

        self._recompute_duplicates()
        return changes

    # ── internals ────────────────────────────────────────────────────────────

    def _recompute_duplicates(self) -> None:
        """Flag every theme whose label another theme also resolves to."""
        counts: dict[str, int] = {}
        for entry in self._entries.values():
            key = entry.label.casefold()
            counts[key] = counts.get(key, 0) + 1
        for theme_id, entry in list(self._entries.items()):
            duplicate = counts.get(entry.label.casefold(), 0) > 1
            if duplicate != entry.duplicate:
                self._entries[theme_id] = replace(entry, duplicate=duplicate)
