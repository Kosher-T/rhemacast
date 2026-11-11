"""M1 batch 1 — showcase audit (M1-02).

Drives the eight showcase themes through the real Full Designer tab and the
real Quick Editor, on an offscreen Qt display, and records:

* which leaf keys have a Designer control, and which do not;
* animation slots per container/block and whether the Designer can reach them;
* key loss after a real Save + cold reload;
* resolved-theme differences (what OBS would render differently) caused by a
  load/save with no operator edit;
* save refusals / exceptions.

The loader is redirected to a temporary copy of ``themes/``, so the audit never
writes the repository themes. Writes ``dev/m1_batch1_audit.json`` and a compact
``dev/m1_batch1_audit.md``. Not part of the app; safe to delete.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6 import QtWebEngineWidgets  # noqa: F401,E402

APP = QApplication(["m1-batch1-audit"])

from core import theme_loader  # noqa: E402
from core import theme_schema as schema  # noqa: E402
from ui.tabs.theme_designer_tab import ThemeDesignerTab  # noqa: E402
from ui.widgets.theme_quick_editor import ThemeQuickEditor  # noqa: E402

SHOWCASE = (
    "fullscreen_rise",
    "fullscreen_pop",
    "fullscreen_split",
    "default_typewriter",
    "default_quiet",
    "reference_frames",
    "reference_letterbox",
    "slides_motion",
)

METADATA = {"schema_version", "name", "label", "description", "author", "kind"}
LEGACY_CONTAINER = {
    "padding", "display", "flex_direction", "justify_content", "align_items",
    "x", "y",
}
CARD_OWNED = {"duration_ms", "delay_ms", "easing", "origin", "type", "label"}


# ── helpers ──────────────────────────────────────────────────────────────────

def flatten(value, prefix=""):
    """Yield (dotted path, leaf value). Lists use [index]."""
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def leaves(value):
    return {path: item for path, item in flatten(value)}


def resolve(raw, name):
    kind = raw.get("kind")
    if kind not in (schema.SCRIPTURE, schema.FREEFORM):
        kind = schema.FREEFORM if name in ("slides", "slides_motion") \
            else schema.SCRIPTURE
    resolved, report = schema.normalize_theme(
        copy.deepcopy(raw), kind=kind, name=name)
    return resolved, report


def render_leaves(raw, name):
    resolved, report = resolve(raw, name)
    return leaves(resolved), report


def render_diff(before, after, name):
    """Resolved leaves that differ, ignoring non-rendered metadata."""
    a, _ = render_leaves(before, name)
    b, report = render_leaves(after, name)
    changed = []
    for path in sorted(set(a) | set(b)):
        root = path.split(".")[0].split("[")[0]
        if root in METADATA:
            continue
        if path not in a:
            changed.append({"path": path, "before": "<absent>",
                            "after": b[path]})
        elif path not in b:
            changed.append({"path": path, "before": a[path],
                            "after": "<absent>"})
        elif a[path] != b[path]:
            changed.append({"path": path, "before": a[path],
                            "after": b[path]})
    return changed, report


def key_loss(before, after):
    a = set(leaves(before))
    b = set(leaves(after))
    return sorted(a - b)


def added_keys(before, after):
    a = set(leaves(before))
    b = set(leaves(after))
    return sorted(b - a)


def value_changes(before, after):
    a = leaves(before)
    b = leaves(after)
    out = []
    for path in sorted(set(a) & set(b)):
        if a[path] != b[path]:
            out.append({"path": path, "before": a[path], "after": b[path]})
    return out


def slot_name(value):
    if value is None:
        return "none"
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("type"):
            return f"inline:{value['type']}"
        if value.get("use"):
            return f"use:{value['use']}"
    return json.dumps(value, ensure_ascii=False)[:60]


def animation_slots(theme):
    """Every assignment slot in the raw document, with reachability."""
    found = []
    for index, container in enumerate(theme.get("containers") or []):
        if not isinstance(container, dict):
            continue
        cid = str(container.get("id", f"container{index}"))
        animation = container.get("animation")
        if isinstance(animation, dict):
            for phase in ("entry", "out"):
                if phase in animation:
                    found.append(_slot(
                        f"containers[{index}] ({cid})", f"container.{phase}",
                        animation[phase],
                        "editable" if index == 0 else
                        "uneditable — AnimationPanel hardcodes containers[0]"))
            transition = animation.get("transition")
            if isinstance(transition, dict):
                for phase in ("in", "out"):
                    if phase in transition:
                        found.append(_slot(
                            f"containers[{index}] ({cid})",
                            f"container.transition.{phase}",
                            transition[phase],
                            "editable" if index == 0 else
                            "uneditable — AnimationPanel hardcodes containers[0]"))
        for block_id, block in (container.get("blocks") or {}).items():
            if not isinstance(block, dict):
                continue
            banim = block.get("animation")
            if not isinstance(banim, dict):
                continue
            for phase in ("entry", "out"):
                if phase in banim:
                    found.append(_slot(
                        f"containers[{index}].blocks.{block_id}",
                        f"block.{phase}", banim[phase],
                        "uneditable — no block animation UI"))
            transition = banim.get("transition")
            if isinstance(transition, dict):
                for phase in ("in", "out"):
                    if phase in transition:
                        found.append(_slot(
                            f"containers[{index}].blocks.{block_id}",
                            f"block.transition.{phase}", transition[phase],
                            "uneditable — no block animation UI"))
            if "split" in banim and block_id in schema.SPLIT_BLOCKS:
                found.append(_slot(
                    f"containers[{index}].blocks.{block_id}", "block.split",
                    banim["split"], "editable — SplitEditor"))
    return found


def _slot(where, phase, value, designer):
    return {"where": where, "phase": phase, "slot": slot_name(value),
            "designer": designer}


def control_prefixes(theme):
    """Leaf-level control paths the Full Designer exposes for this document."""
    paths: set[str] = set()
    # Canvas page.
    for key in ("width", "height", "background", "fit"):
        paths.add(f"canvas.{key}")
    # Container page + workspace + split editors.
    for index, container in enumerate(theme.get("containers") or []):
        if not isinstance(container, dict):
            continue
        base = f"containers[{index}]"
        for key in ("label", "kind", "layer", "visible", "min_width",
                    "max_width", "min_height", "max_height", "background",
                    "border", "border_radius", "box_shadow",
                    "backdrop_filter", "opacity", "overflow"):
            paths.add(f"{base}.{key}")
        for key in ("anchor", "x", "y"):
            paths.add(f"{base}.position.{key}")
        for key in ("width", "height", "layer", "visible"):
            paths.add(f"{base}.{key}")
        for block_id, block in (container.get("blocks") or {}).items():
            if not isinstance(block, dict):
                continue
            bbase = f"{base}.blocks.{block_id}"
            if block_id == "body":
                for key in ("visible", "valign", "gap", "padding"):
                    paths.add(f"{bbase}.{key}")
                for side in ("top", "right", "bottom", "left"):
                    paths.add(f"{bbase}.padding_{side}")
                continue
            for key in (
                "visible", "color", "font_family", "size", "min_size",
                "max_size", "weight", "line_height", "letter_spacing",
                "word_spacing", "text_shadow", "text_outline",
                "text_transform", "text_align", "font_style",
                "text_decoration", "opacity", "max_lines", "direction",
                "margin_top", "margin_right", "margin_bottom", "margin_left",
                "padding", "padding_top", "padding_right", "padding_bottom",
                "padding_left",
            ):
                paths.add(f"{bbase}.{key}")
            if block_id == "text":
                paths.add(f"{bbase}.autosize")
            if block_id in ("reference", "title"):
                for key in ("position", "color", "font_family", "size",
                            "weight", "letter_spacing", "text_transform"):
                    paths.add(f"{bbase}.{key}")
            if block_id == "translation":
                for key in ("position", "color", "margin_left"):
                    paths.add(f"{bbase}.{key}")
            if block_id == "verse_num":
                for key in ("mode", "position", "vertical_align",
                            "margin_right", "size", "weight", "opacity",
                            "line_height", "color", "font_family"):
                    paths.add(f"{bbase}.{key}")
            if block_id in schema.SPLIT_BLOCKS:
                paths.add(f"{bbase}.animation.split")
                paths.add(f"{bbase}.animation.split.look")
    # Container-0 phase cards.
    for key in ("entry", "out"):
        paths.add(f"containers[0].animation.{key}")
    for key in ("in", "out"):
        paths.add(f"containers[0].animation.transition.{key}")
    # Editable fields of local definitions reached from container 0.
    for name in _container_zero_definitions(theme):
        paths.add(f"animations.{name}.keyframes")
        paths.add(f"animations.{name}.reveal")
        paths.add(f"animations.{name}.cursor")
    return paths


def _container_zero_definitions(theme):
    containers = theme.get("containers") or []
    if not containers or not isinstance(containers[0], dict):
        return set()
    names = set()
    animation = containers[0].get("animation")
    if not isinstance(animation, dict):
        return names
    slots = [animation.get("entry"), animation.get("out")]
    transition = animation.get("transition")
    if isinstance(transition, dict):
        slots += [transition.get("in"), transition.get("out")]
    for slot in slots:
        if isinstance(slot, str):
            names.add(slot)
        elif isinstance(slot, dict) and isinstance(slot.get("use"), str):
            names.add(slot["use"])
    return names


def covered(path, prefixes):
    for prefix in prefixes:
        if path == prefix:
            return True
        if path.startswith(prefix + ".") or path.startswith(prefix + "["):
            return True
    return False


def classify_uncovered(path, theme):
    if path in METADATA:
        return "metadata (preserve/raw)"
    if re.fullmatch(r"containers\[\d+\]\.id", path):
        return "identity (preserve-only)"
    if path == "slide.show_title":
        return "needs control — freeform switch"
    match = re.fullmatch(r"containers\[(\d+)\]\.animation\.(.*)", path)
    if match:
        index = int(match.group(1))
        if index == 0:
            return "no control (unexpected)"
        return "needs control — container animation beyond containers[0]"
    match = re.fullmatch(
        r"containers\[(\d+)\]\.blocks\.([^.]+)\.animation\.(.*)", path)
    if match:
        block = match.group(2)
        if ".split" in path:
            return "no control (unexpected split)"
        return f"needs control — {block} animation slots"
    if path.startswith("animations."):
        parts = path.split(".")
        field = parts[-1].split("[")[0]
        if field in CARD_OWNED:
            return "needs control/raw — animation library definition"
        return "no control (unexpected animation field)"
    if re.match(r"containers\[\d+\]\.(padding|display|flex_direction|"
                r"justify_content|align_items|x|y)(\.|$)", path):
        return "preserve-only — legacy container key"
    if re.match(r"containers\[\d+\]\.position\.(top_left|top_right|"
                r"bottom_left|bottom_right)$", path):
        return "preserve-only — v1 corner boolean"
    return "no control"


# ── audit ────────────────────────────────────────────────────────────────────

def audit_theme(tab, name):
    raw = theme_loader.get_theme(name)
    if raw is None:
        raise SystemExit(f"missing theme: {name}")

    # ── Full Designer load ────────────────────────────────────────────────
    tab.set_theme(name)
    APP.processEvents()
    loaded = copy.deepcopy(tab._working_theme)
    prefixes = control_prefixes(raw)
    uncovered = {}
    for path in leaves(raw):
        if not covered(path, prefixes):
            uncovered[path] = classify_uncovered(path, raw)

    # ── Full Designer Save + cold reload ──────────────────────────────────
    save_error = None
    try:
        tab._on_save()
    except Exception as error:  # noqa: BLE001 - audit records the failure
        save_error = f"{type(error).__name__}: {error}"
    theme_loader.reload_themes()
    cold = theme_loader.get_theme(name)
    if cold is None:
        cold = {}
    save_loss = key_loss(raw, cold)
    save_added = added_keys(raw, cold)
    save_changes = value_changes(raw, cold)
    save_render, save_report = render_diff(raw, cold, name)

    # ── Quick Editor load/collect ─────────────────────────────────────────
    quick = ThemeQuickEditor(name)
    APP.processEvents()
    collected = quick._props.get_theme()
    quick_error = None
    quick_saved_loss = []
    try:
        # Exactly what the Quick Editor's Save button does: write the theme
        # back under its own name with the same writer.
        theme_loader.save_theme(name, collected)
        theme_loader.reload_themes()
        cold_quick = theme_loader.get_theme(name) or {}
        quick_saved_loss = key_loss(collected, cold_quick)
    except Exception as error:  # noqa: BLE001
        quick_error = f"{type(error).__name__}: {error}"
    quick.close()
    quick.deleteLater()
    APP.processEvents()
    quick_loss = key_loss(raw, collected)
    quick_added = added_keys(raw, collected)
    quick_changes = value_changes(raw, collected)
    quick_render, quick_report = render_diff(raw, collected, name)

    return {
        "name": name,
        "kind": raw.get("kind"),
        "containers": [
            {"index": index, "id": container.get("id"),
             "blocks": sorted((container.get("blocks") or {}).keys())}
            for index, container in enumerate(raw.get("containers") or [])
            if isinstance(container, dict)
        ],
        "animation_slots": animation_slots(raw),
        "full_designer": {
            "load_key_loss": key_loss(raw, loaded),
            "uncovered_leaves": [
                {"path": path, "group": group}
                for path, group in sorted(uncovered.items())
            ],
            "save_error": save_error,
            "save_key_loss": save_loss,
            "save_added_keys": save_added,
            "save_value_changes": save_changes,
            "save_render_diffs": save_render,
            "resolve_errors": list(save_report.errors),
            "resolve_warnings": len(save_report.warnings),
        },
        "quick_editor": {
            "save_error": quick_error,
            "saved_key_loss": quick_saved_loss,
            "key_loss": quick_loss,
            "added_keys": quick_added,
            "value_changes": quick_changes,
            "render_diffs": quick_render,
            "resolve_errors": list(quick_report.errors),
            "resolve_warnings": len(quick_report.warnings),
            "unselectable": [
                "container add/duplicate/delete/reorder (workspace not mounted)",
                "container canvas drag/resize (workspace not mounted)",
                "animations (separate animation panel not mounted)",
                "slide.show_title",
                "metadata (label/description/author)",
            ],
        },
    }


def summarize(results):
    return {
        "themes": len(results),
        "full_save_key_loss": sum(len(r["full_designer"]["save_key_loss"])
                                  for r in results),
        "quick_key_loss": sum(len(r["quick_editor"]["key_loss"])
                              for r in results),
        "quick_save_key_loss": sum(len(r["quick_editor"]["saved_key_loss"])
                                   for r in results),
        "save_errors": [r["name"] for r in results
                        if r["full_designer"]["save_error"]],
        "quick_save_errors": [r["name"] for r in results
                              if r["quick_editor"]["save_error"]],
        "themes_with_render_diffs": [
            r["name"] for r in results
            if r["full_designer"]["save_render_diffs"]
            or r["quick_editor"]["render_diffs"]
        ],
        "uneditable_animation_slots": sum(
            1 for r in results for slot in r["animation_slots"]
            if slot["designer"].startswith("uneditable")),
        "editable_animation_slots": sum(
            1 for r in results for slot in r["animation_slots"]
            if slot["designer"].startswith("editable")),
    }


def write_markdown(results, summary, path):
    lines = [
        "# M1 batch 1 — showcase audit",
        "",
        "Generated by `dev/m1_batch1_audit.py` (offscreen Qt, real Full "
        "Designer tab and real Quick Editor, temp theme tree).",
        "",
        f"- Themes: {summary['themes']}",
        f"- Full Designer save key loss: {summary['full_save_key_loss']}",
        f"- Quick Editor collect key loss: {summary['quick_key_loss']}",
        f"- Quick Editor save key loss: {summary['quick_save_key_loss']}",
        f"- Save errors: {summary['save_errors'] or 'none'}",
        f"- Quick Editor save errors: "
        f"{summary['quick_save_errors'] or 'none'}",
        f"- Editable animation slots: "
        f"{summary['editable_animation_slots']}",
        f"- Uneditable animation slots: "
        f"{summary['uneditable_animation_slots']}",
        "",
    ]
    for result in results:
        full = result["full_designer"]
        quick = result["quick_editor"]
        lines += [
            f"## {result['name']} ({result['kind']})",
            "",
            f"Containers: {len(result['containers'])}; "
            f"blocks: "
            f"{'; '.join(f'{c['id']}={','.join(c['blocks'])}' for c in result['containers'])}",
            "",
            "| Animation slot | Designer |",
            "|---|---|",
        ]
        for slot in result["animation_slots"]:
            lines.append(
                f"| `{slot['where']} · {slot['phase']}` = "
                f"`{slot['slot']}` | {slot['designer']} |")
        lines += [
            "",
            f"- Full Designer: save key loss "
            f"{full['save_key_loss'] or 'none'}; render diffs "
            f"{len(full['save_render_diffs'])}; resolve warnings "
            f"{full['resolve_warnings']}; resolve errors "
            f"{full['resolve_errors'] or 'none'}; save error "
            f"{full['save_error'] or 'none'}.",
            f"- Uncovered leaves ({len(full['uncovered_leaves'])}): "
            + (", ".join(
                f"`{item['path']}` ({item['group']})"
                for item in full["uncovered_leaves"][:12])
               + (" …" if len(full["uncovered_leaves"]) > 12 else "")
               if full["uncovered_leaves"] else "none"),
            f"- Quick Editor: collect key loss "
            f"{quick['key_loss'] or 'none'}; added keys "
            f"{len(quick['added_keys'])}; value changes "
            f"{len(quick['value_changes'])}; render diffs "
            f"{len(quick['render_diffs'])}; save error "
            f"{quick['save_error'] or 'none'}.",
            "",
        ]
        if quick["render_diffs"]:
            lines.append("Quick Editor render differences:")
            lines.append("")
            for diff in quick["render_diffs"][:12]:
                lines.append(
                    f"- `{diff['path']}`: `{diff['before']}` → "
                    f"`{diff['after']}`")
            if len(quick["render_diffs"]) > 12:
                lines.append(f"- … and {len(quick['render_diffs']) - 12} more")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    temp_root = Path(tempfile.mkdtemp(prefix="rhemacast-m1-audit-"))
    try:
        shutil.copytree(ROOT / "themes", temp_root / "themes")
        theme_loader._THEMES_DIR = temp_root / "themes"
        theme_loader.reload_themes()

        tab = ThemeDesignerTab()
        tab.resize(1400, 900)
        tab.show()
        APP.processEvents()
        results = []
        try:
            for name in SHOWCASE:
                results.append(audit_theme(tab, name))
        finally:
            tab.close()
            tab.deleteLater()
            APP.processEvents()

        summary = summarize(results)
        payload = {"summary": summary, "results": results}
        (ROOT / "dev" / "m1_batch1_audit.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
        write_markdown(results, summary, ROOT / "dev" / "m1_batch1_audit.md")

        print(json.dumps(summary, indent=2))
        ok = (summary["full_save_key_loss"] == 0
              and summary["quick_key_loss"] == 0
              and summary["quick_save_key_loss"] == 0
              and not summary["save_errors"]
              and not summary["quick_save_errors"])
        print("M1 BATCH1 AUDIT PASS" if ok else "M1 BATCH1 AUDIT FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
