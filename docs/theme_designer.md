# Theme Designer — Architecture & Implementation Plan

> **Goal:** A visual WYSIWYG theme editor for RhemaCast that lets operators design OBS overlay themes without writing code. Two modes: a **Full Designer** (dedicated tab) and a **Quick Editor** (inline widget embedded in other tabs for hot changes). Both must be lightweight, lag-free, and GPU-accelerated — the anti-Elementor.

---

## 1. Why Not Elementor's Approach

| Elementor Problem | Our Solution |
|---|---|
| **Div soup** — deep nested wrappers for flexibility | Fixed, flat DOM: exactly 4 elements (`#container`, `#verse-text`, `#verse-ref-text`, `#verse-ref-translation`). No wrappers. |
| **Layout thrashing** — reflow on every drag pixel | `transform: translate3d()` for all drag/resize. Zero reflow. GPU compositor thread only. |
| **Massive CSS/JS bundles** loaded regardless of use | Single inline `<style>` block + ~400 lines of vanilla JS. No framework, no bundler. |
| **Tangled state** — DOM is the source of truth | **JSON-first**: the theme JSON file is the single source of truth. DOM is a pure projection. |
| **Heavy serialization** — saving = scraping the entire DOM | Saving = `JSON.stringify(state)` → `themes/{name}.json`. Instant. |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    PyQt6 Host                           │
│                                                         │
│  ┌──────────────┐    ┌────────────────────────────────┐ │
│  │ Python Bridge │◄──►│ QWebEngineView (Designer HTML) │ │
│  │  theme_loader │    │   Vanilla JS + CSS             │ │
│  │  save/load    │    │   JSON ↔ DOM projection        │ │
│  └──────────────┘    └────────────────────────────────┘ │
│         │                        │                       │
│         ▼                        ▼                       │
│  themes/*.json            OBS Display                    │
│  (source of truth)     (reads same JSON)                 │
└─────────────────────────────────────────────────────────┘
```

### The Two Apps (Already Exist)

1. **The Builder** — runs inside `QWebEngineView` in the PyQt6 operator UI. Handles drag/drop, property editing, live preview. Writes JSON.
2. **The Viewer** — `display/display.html` (already built). Reads JSON theme data via WebSocket and renders with CSS custom properties. Zero builder code.

### Communication: PyQt ↔ WebEngine

All communication uses `QWebEnginePage.runJavaScript()` (Python → JS) and `QWebChannel` (JS → Python). No HTTP server needed — it's all in-process.

| Direction | Mechanism | Example |
|---|---|---|
| Python → JS | `page.runJavaScript("loadTheme(" + json + ")")` | Load theme for editing |
| JS → Python | `QWebChannel` callback: `bridge.saveTheme(jsonString)` | Save edited theme |
| Python → JS | `page.runJavaScript("setPreviewVerse(...)")` | Update preview text |

---

## 3. JSON Schema (Extended Theme Format)

The current theme schema (`themes/default.json`) defines 4 groups: `container`, `text`, `reference`, `translation`. The designer extends this with **layout positioning** and **element visibility**, while remaining backward-compatible.

```json
{
  "name": "my_theme",
  "label": "My Custom Theme",
  "description": "User-created theme",
  "author": "Operator",
  "version": 2,

  "canvas": {
    "width": 1920,
    "height": 1080,
    "background": "transparent"
  },

  "container": {
    "background": "rgba(15, 23, 42, 0.6)",
    "border": "1px solid rgba(255, 255, 255, 0.1)",
    "border_radius": "24px",
    "box_shadow": "0 25px 50px -12px rgba(0,0,0,0.5)",
    "backdrop_filter": "blur(16px)",
    "padding": "40px",
    "max_width": "80%",
    "min_width": "60%",
    "x": 960, "y": 920,
    "anchor": "bottom-center",
    "visible": true
  },

  "text": {
    "color": "#f8fafc",
    "font_family": "Inter",
    "size": "2.5rem",
    "weight": 800,
    "line_height": "1.4",
    "text_shadow": "0 4px 12px rgba(0,0,0,0.4)",
    "letter_spacing": "-0.02em",
    "margin_bottom": "24px",
    "text_align": "center",
    "visible": true
  },

  "reference": {
    "color": "#94a3b8",
    "font_family": "Inter",
    "size": "1.5rem",
    "weight": 600,
    "text_transform": "uppercase",
    "letter_spacing": "0.1em",
    "visible": true
  },

  "translation": {
    "color": "#64748b",
    "margin_left": "8px",
    "visible": true
  }
}
```

### Backward Compatibility

- **v1 themes** (current): No `canvas`, `x`, `y`, `anchor`, or `visible` fields. The designer fills defaults when loading. The OBS viewer ignores unknown fields.
- **v2 themes**: Include layout positioning. The viewer uses `x`/`y`/`anchor` if present; falls back to CSS defaults if not.

---

## 4. Performance Contract

Every interaction must complete within a single frame (16.67ms). Here's how:

### 4.1 GPU-Accelerated Dragging

```javascript
// WRONG — forces CPU layout recalc on every pixel:
element.style.left = x + "px";
element.style.top = y + "px";

// RIGHT — GPU compositor, zero reflow:
element.style.transform = `translate3d(${x}px, ${y}px, 0)`;
```

All movable elements get `will-change: transform` on drag start, removed on drag end.

### 4.2 Batched State Updates

Property changes are debounced to a single `requestAnimationFrame` per frame:

```javascript
let _dirty = false;
function markDirty() {
    if (_dirty) return;
    _dirty = true;
    requestAnimationFrame(() => {
        applyStateToDOM(state);
        _dirty = false;
    });
}
```

### 4.3 No Framework Tax

- **Zero dependencies**: No React, Vue, Svelte. Pure vanilla JS.
- **No virtual DOM diffing**: Direct DOM property writes via CSS custom properties (same system the OBS viewer uses).
- **No layout engine**: Fixed 4-element DOM. The only thing that changes is CSS custom property values on `:root`.

### 4.4 Memory Budget

- Full Designer HTML: < 50KB (inline, no external fetches except Google Fonts)
- JSON state object: < 2KB per theme
- DOM nodes: < 30 total (canvas + 4 elements + inspector controls)

---

## 5. Full Theme Designer (Dedicated Tab)

### 5.1 Layout: Three-Pane Editor

```
┌──────────────┬──────────────────────────┬───────────────┐
│              │                          │               │
│  INSPECTOR   │       CANVAS             │   ELEMENTS    │
│  (Left)      │    (1920×1080 scaled)    │   & ACTIONS   │
│              │                          │   (Right)     │
│  Context-    │    ┌──────────────────┐  │               │
│  aware       │    │  [verse text]    │  │  Draggable    │
│  property    │    │  [reference]     │  │  base types   │
│  editor      │    │  [translation]   │  │               │
│              │    └──────────────────┘  │  Save/Reset/  │
│              │                          │  Export/Import │
│              │                          │               │
└──────────────┴──────────────────────────┴───────────────┘
```

### 5.2 Inspector Panel (Left Sidebar)

Context-sensitive. Shows different controls based on selection state:

**No Selection → Global Theme Settings:**
- Theme name, label, description, author
- Canvas background color/image
- Container background, border, border-radius, box-shadow, backdrop-filter
- Container padding, max-width, min-width

**Element Selected → Element Properties:**
- Position: X, Y (numeric inputs + drag)
- Font family (dropdown: system fonts + Google Fonts subset)
- Font size (slider: 0.5rem–6rem)
- Font weight (dropdown: 400/600/700/800/900)
- Color (color picker)
- Text shadow (preset dropdown + custom)
- Letter spacing (slider)
- Line height (slider)
- Text transform (none/uppercase/lowercase/capitalize)
- Visibility toggle (on/off)
- Z-index (bring forward/send back buttons)

### 5.3 Canvas (Center)

- Fixed 1920×1080 virtual resolution
- Scaled to fit the `QWebEngineView` via `transform: scale()` (same technique already used in `display_view.py`)
- Checkerboard background for transparency visualization
- Click to select elements; selected elements show resize handles + bounding box
- Drag elements using `translate3d()` — updates `x`/`y` in JSON state
- Snap-to-grid toggle (16px grid)
- Alignment guides (center, edges of other elements)

### 5.4 Elements & Actions Panel (Right Sidebar)

**Element Palette:**
- Scripture Text (verse body)
- Reference (book chapter:verse)
- Translation Badge
- Container (the glassmorphism card)

Each has a visibility toggle and a "select" click.

**Actions:**
- 💾 Save Theme — writes JSON to `themes/{name}.json` via `QWebChannel` → Python
- 🔄 Reset — reloads from last saved state
- 📤 Export — copies JSON to clipboard
- 📥 Import — paste JSON to load
- 🗑 Delete Theme — removes file (with confirmation)
- ➕ New Theme — clones current or starts from `default.json`

### 5.5 Live Preview

The canvas IS the live preview. It renders with the same CSS custom properties as the OBS viewer, using sample verse text:

> *"For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life."*
> **JOHN 3:16** KJV

The operator sees exactly what OBS will display.

---

## 6. Quick Editor (Inline Widget)

The lightweight version that appears inside the Themes sub-tab of the Queue Panel and potentially other tabs.

### 6.1 What It Is

A compact property editor — **no canvas, no drag-and-drop**. Just the inspector controls from the Full Designer, collapsed into a scrollable form with a small preview thumbnail.

### 6.2 Layout

```
┌─────────────────────────────────┐
│  [Theme Selector Dropdown]  ✏️  │  ← opens Full Designer
├─────────────────────────────────┤
│  ┌───────────────────────────┐  │
│  │    Mini Preview           │  │  ← 320×180 scaled canvas
│  │    (read-only, no drag)   │  │
│  └───────────────────────────┘  │
├─────────────────────────────────┤
│  ▸ Container                    │  ← collapsible sections
│    Background: [color picker]   │
│    Border Radius: [slider]      │
│    Blur: [slider]               │
│  ▸ Text                         │
│    Color: [color picker]        │
│    Size: [slider]               │
│    Weight: [dropdown]           │
│  ▸ Reference                    │
│    Color: [color picker]        │
│    Size: [slider]               │
│  ▸ Translation                  │
│    Color: [color picker]        │
│                                 │
│  [Save] [Reset]                 │
└─────────────────────────────────┘
```

### 6.3 How It Differs from Full Designer

| Feature | Full Designer | Quick Editor |
|---|---|---|
| Canvas with drag/drop | ✅ | ❌ |
| Resize handles | ✅ | ❌ |
| Position (x/y) editing | ✅ | ❌ |
| Snap-to-grid | ✅ | ❌ |
| Alignment guides | ✅ | ❌ |
| Property sliders/pickers | ✅ | ✅ |
| Live preview | Full 1920×1080 | Mini 320×180 |
| Create new theme | ✅ | ❌ (clone only) |
| Delete theme | ✅ | ❌ |
| Export/Import JSON | ✅ | ❌ |
| Element visibility | ✅ | ✅ |
| DOM nodes | ~30 | ~15 |
| JS payload | ~400 lines | ~150 lines |
| Load time | < 100ms | < 50ms |

### 6.4 Integration Points

The Quick Editor replaces the current `ThemesPanel` (theme card list) with a richer but still lightweight interface. It:
- Lives inside the Queue Panel's "Themes" sub-tab (already lazy-loaded)
- Emits the same `theme_changed` and `theme_double_clicked` signals
- Can be embedded anywhere via `QuickThemeEditor(parent)` — it's a standard `QWidget`
- Changes are immediately reflected in the Preview viewport (same signal wiring)

---

## 7. Implementation: File-by-File

### 7.1 New Files

| File | Purpose | Size Est. |
|---|---|---|
| `designer/designer.html` | Full Designer — single HTML file with inline CSS/JS | ~25KB |
| `designer/quick_editor.html` | Quick Editor — compact inline HTML | ~10KB |
| `ui/tabs/designer_tab.py` | PyQt wrapper for Full Designer QWebEngineView + QWebChannel bridge | ~200 lines |
| `ui/panels/quick_theme_editor.py` | PyQt wrapper for Quick Editor, replaces ThemesPanel in queue | ~150 lines |
| `core/theme_manager.py` | Extended theme CRUD: load, save, validate, clone, delete, list | ~120 lines |

### 7.2 Modified Files

| File | Change |
|---|---|
| `ui/main_window.py` | Replace `_init_theme_designer()` placeholder with real `DesignerTab` |
| `ui/panels/queue_panel.py` | Swap `ThemesPanel` for `QuickThemeEditor` in the themes sub-tab |
| `core/theme_loader.py` | Add `save_theme()`, `delete_theme()`, `validate_theme()` functions |
| `display/display.js` | Handle `visible: false` fields — hide elements with `display: none` |
| `display/themes.css` | No changes needed (CSS vars already handle everything) |
| `themes/*.json` | No changes needed (v1 format remains valid) |

### 7.3 Dependencies

**Zero new pip dependencies.** Everything uses:
- `QWebEngineView` (already installed — used by `DisplayView`)
- `QWebChannel` (part of `PyQt6-WebEngine`, already installed)
- Vanilla JS (no npm, no node, no build step)

---

## 8. Designer HTML Architecture

The Full Designer is a single self-contained HTML file. No external JS dependencies.

### 8.1 State Machine

```javascript
const state = {
    theme: { /* the full JSON theme object */ },
    selection: null,        // "container" | "text" | "reference" | "translation" | null
    isDragging: false,
    dragOffset: { x: 0, y: 0 },
    snapToGrid: true,
    gridSize: 16,
    undoStack: [],
    redoStack: [],
    dirty: false            // unsaved changes
};
```

### 8.2 Core Loop

```
User Input → Update state.theme → requestAnimationFrame → Apply CSS vars to :root → DOM reflects instantly
```

No intermediate DOM manipulation. The same `applyTheme()` function from `display.js` is reused.

### 8.3 Undo/Redo

Every state change pushes a deep clone of `state.theme` onto `undoStack`. Ctrl+Z pops and restores. Max 50 levels.

---

## 9. PyQt Bridge (QWebChannel)

```python
class ThemeDesignerBridge(QObject):
    """Python ↔ JS bridge for the theme designer."""

    theme_saved = pyqtSignal(str)  # theme name

    @pyqtSlot(str, result=str)
    def saveTheme(self, json_string: str) -> str:
        """Called from JS when user clicks Save."""
        data = json.loads(json_string)
        name = data.get("name", "untitled")
        path = THEMES_DIR / f"{name}.json"
        path.write_text(json.dumps(data, indent=4))
        reload_themes()
        self.theme_saved.emit(name)
        return "ok"

    @pyqtSlot(result=str)
    def loadThemeList(self) -> str:
        """Return all theme names + data for the theme selector."""
        return json.dumps(get_all_themes())

    @pyqtSlot(str, result=str)
    def loadTheme(self, name: str) -> str:
        """Load a specific theme for editing."""
        theme = get_theme(name)
        return json.dumps(theme) if theme else "{}"

    @pyqtSlot(str, result=str)
    def deleteTheme(self, name: str) -> str:
        """Delete a theme file. Cannot delete 'default'."""
        if name == "default":
            return "error: cannot delete default theme"
        path = THEMES_DIR / f"{name}.json"
        if path.exists():
            path.unlink()
            reload_themes()
            return "ok"
        return "error: not found"

    @pyqtSlot(str, str, result=str)
    def cloneTheme(self, source_name: str, new_name: str) -> str:
        """Clone a theme with a new name."""
        source = get_theme(source_name)
        if not source:
            return "error: source not found"
        clone = dict(source)
        clone["name"] = new_name
        clone["label"] = new_name.replace("_", " ").title()
        path = THEMES_DIR / f"{new_name}.json"
        path.write_text(json.dumps(clone, indent=4))
        reload_themes()
        return "ok"
```

---

## 10. Integration with Existing Display Pipeline

### The Key Insight

The designer doesn't need a new rendering path. It uses the **exact same CSS custom property system** already powering:
- `display/display.html` (OBS viewer)
- `ui/widgets/display_view.py` (operator preview)

When the user edits a property in the designer, it calls `applyTheme(state.theme)` — the same function. When they save, `theme_loader.reload_themes()` is called, and the next verse broadcast picks up the new theme data automatically.

### Hot-Reload Flow

```
Designer Save → themes/name.json written
              → theme_loader.reload_themes()
              → If this theme is active, re-broadcast current verse with new theme_data
              → OBS viewer receives updated theme via WebSocket
              → Preview viewports update via JS injection
```

---

## 11. Quick Editor in Other Tabs

The Quick Editor can be instantiated anywhere:

```python
from ui.panels.quick_theme_editor import QuickThemeEditor

# In any tab or panel:
editor = QuickThemeEditor()
editor.theme_changed.connect(self._on_theme_changed)  # same signal as ThemesPanel
layout.addWidget(editor)
```

It's a `QWebEngineView` loading `designer/quick_editor.html` — approximately 10KB of self-contained HTML. The mini preview uses the same `applyTheme()` + CSS vars system, scaled to 320×180 via `transform: scale()`.

---

## 12. Phased Implementation

### Phase A — Core Infrastructure (foundation)
1. Create `core/theme_manager.py` — CRUD operations, validation, clone
2. Extend `core/theme_loader.py` — add `save_theme()`, `delete_theme()`
3. Create the `designer/` directory

### Phase B — Quick Editor (ship first, used most)
1. Build `designer/quick_editor.html` — compact form with mini preview
2. Build `ui/panels/quick_theme_editor.py` — QWebEngineView + QWebChannel bridge
3. Replace `ThemesPanel` usage in `queue_panel.py`
4. Wire signals: `theme_changed`, `theme_double_clicked`

### Phase C — Full Designer (dedicated tab)
1. Build `designer/designer.html` — three-pane editor with canvas
2. Implement drag/drop with `translate3d()` + snap-to-grid
3. Implement inspector panel with all property controls
4. Build `ui/tabs/designer_tab.py` — QWebEngineView + QWebChannel bridge
5. Replace placeholder in `main_window.py` → `_init_theme_designer()`
6. Implement undo/redo stack

### Phase D — Polish
1. Alignment guides + snap-to-center
2. Font picker with Google Fonts preview
3. Preset shadow/glow effects dropdown
4. Theme import/export (JSON clipboard)
5. Hot-reload to OBS on save

---

## 13. Testing Strategy

### Automated
```bash
# Theme manager CRUD
python -m pytest tests/test_theme_designer.py -v

# Test cases:
# - save_theme() writes valid JSON
# - load_theme() returns correct data
# - clone_theme() creates independent copy
# - delete_theme() removes file + cache entry
# - delete_theme("default") is rejected
# - v1 themes load without errors (backward compat)
# - v2 themes with position data round-trip correctly
```

### Manual / Browser
- Open Full Designer tab → verify canvas renders at correct aspect ratio
- Drag elements → verify 60fps (no dropped frames in Chrome DevTools)
- Edit properties → verify Preview viewport updates in real-time
- Save → verify `themes/name.json` written correctly
- Save → verify OBS display updates on next verse broadcast
- Quick Editor in Queue → verify same signals fire as old ThemesPanel
- Resize window → verify canvas scales correctly

---

## 14. Performance Targets

| Metric | Target | How |
|---|---|---|
| Designer load time | < 100ms | Single inline HTML, no external fetches |
| Quick Editor load time | < 50ms | Minimal DOM, no canvas |
| Drag frame rate | 60fps | `translate3d()`, `will-change: transform` |
| Property change → preview update | < 16ms | `requestAnimationFrame` batch |
| Save to disk | < 5ms | `JSON.stringify()` + single file write |
| Theme hot-reload | < 50ms | Cache invalidation + re-broadcast |
| Memory (Full Designer) | < 10MB | No framework, no virtual DOM |
| Memory (Quick Editor) | < 5MB | Minimal DOM |

---

## Cross-References

- **Current theme system**: [display_and_broadcast.md](display_and_broadcast.md)
- **Theme JSON files**: `themes/*.json`
- **Theme loader**: `core/theme_loader.py`
- **OBS display renderer**: `display/display.html` + `display/display.js` + `display/themes.css`
- **Operator preview**: `ui/widgets/display_view.py`
- **Theme selection UI**: `ui/panels/themes_panel.py` (to be superseded by Quick Editor)
- **Queue panel integration**: `ui/panels/queue_panel.py`
- **Main window tab**: `ui/main_window.py` → `_init_theme_designer()`
