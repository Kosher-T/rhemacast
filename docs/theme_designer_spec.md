# Theme Designer — Specification

> living document — update as design decisions are made

---

## 1. Two Modes

### Light (Quick Edit)
- **Trigger**: Right-click a theme card in the ThemesPanel
- **UI**: Floating popup panel, 1280×720 (720p), centered over the Presentation tab
- **Backdrop**: Semi-transparent overlay with blur, dimming the presentation behind it
- **Content**: Left column (properties) + Right column (single live preview)
- **Preview verse**: Psalm 100:4 KJV
- **"Edit in Full Designer" button** in the title bar — switches to the Full tab with the same theme loaded
- **Save/Reset** buttons persist to `themes/{name}.json`, hot-reload picks it up

### Full (Dedicated Tab)
- **Trigger**: "THEME DESIGNER" tab in the main tab bar
- **UI**: Three-column layout (Properties | Three Previews | Animations + JSON)
- **Preview layout**: Triangle formation — one on top, two below
  - **Top**: Matthew 3:11 (medium verse, centered)
  - **Bottom left**: John 11:35 (shortest verse)
  - **Bottom right**: Esther 8:9 (longest verse)
- **Viewport definition**: Identical to Live/Preview screens:
  - QFrame: `background: black`, `border: 1px solid rgba(255,255,255,0.08)`, `border-radius: 8px`
  - AspectRatioWidget: `aspect_ratio=16/9`, `min_width=320`, `max_width=840`
  - Contains DisplayView (QWebEngineView) rendering the same HTML/CSS/JS as OBS
- All three previews are KJV, hot-reload simultaneously
- **Everything in Light** plus:
  - Display start / between-slide / end animations
  - Direct JSON editor with syntax highlighting
  - Import/Export JSON

---

## 2. Container System

Every visual element lives inside its own **container** (a `div` in the display HTML). Containers are the unit of layout — they hold position, dimensions, and background independently.

### Container Properties
Each container has:
- Position (x, y offsets from parent)
- Dimensions (width, height — **fixed, never flex**)
- Background, border, border-radius, backdrop-filter, box-shadow
- Padding

### Transform Controls
Containers are directly manipulable in the preview viewport:

| Control | Location | Behavior |
|---------|----------|----------|
| Corner handles | 4 corners | Resize (width + height simultaneously) |
| Edge mid-points | 4 edges | Resize single axis (width or height) |
| Center handle | Center of container | Move (drag to reposition) |

All transform controls appear when a container is **selected/focused**.

**Value editing**: Every property editable via numeric inputs in the properties panel. Changes sync bidirectionally with the visual controls.

### Container Capabilities by Element

Not every element needs full container treatment. Some are content-only (position follows parent flow), others are fully transformable.

| Element | Move | Resize | Notes |
|---------|------|--------|-------|
| **Container** (outer wrapper) | Yes | Yes | The main box. Controls overall theme shape. |
| **Scripture Text** | Yes | Yes | Full transform. Text inside respects container bounds. |
| **Reference** | Yes | Yes | Full transform. Independent positioning. |
| **Translation** | Yes | No | Can be moved (e.g., reposition relative to reference), but not resized — it's just a label. |
| **Verse Number** | No | No | Follows parent flow (inside Scripture Text container). Only font/color edits. |

> **Decision**: Nerf verse number container. It's inline with the text, no independent positioning needed.

---

## 3. Element Focus System

When the user clicks an element's row in the properties panel (or clicks the container in the preview):

1. **Focused element** gets a blue left-border accent, full opacity
2. **All other elements** grey out (opacity ~0.35)
3. **Property sections** for unfocused elements collapse/hide
4. **Transform controls** in the preview show only for the focused element's container
5. Clicking another element switches focus
6. Clicking empty space in the preview deselects all (no focus)

This creates a clear "edit mode" per element without visual clutter.

---

## 4. Auto-Resize Text Toggle

Each text element (Scripture Text, Reference) has an **Auto Fit** toggle:

### When ON (default)
- Text font-size is dynamically calculated to fill the container
- Uses the existing `autoFitText()` binary search between `min_size` and `max_size`
- Container dimensions are the constraint; text scales to fit

### When OFF
- Text uses the manually set `font-size`
- **Text that overflows the container is clipped** — disappears behind the container boundary
- Container dimensions **never flex** to accommodate text
- The overflow is hidden, not scrolled — this is a display overlay, not a document

### Implementation
```css
/* Container always clips */
.container {
    overflow: hidden;
    /* width/height are fixed — never auto */
}

/* When auto-fit is OFF, text has explicit size and may overflow */
.container.auto-fit-off .verse-text {
    font-size: var(--rc-text-size);  /* user-set, fixed */
    overflow: hidden;
}
```

---

## 5. Theme JSON Schema (Current)

All 37 CSS custom properties map 1:1 to JSON keys:

```
{
  name, label, description, author,

  container: {
    background, border, border_radius, box_shadow, backdrop_filter,
    padding, max_width, min_width, width, height,
    display, flex_direction, justify_content, align_items
  },

  body: {
    vertical_align, padding_bottom
  },

  text: {
    color, font_family, size, min_size, max_size, weight,
    line_height, text_shadow, letter_spacing, margin_bottom
  },

  reference: {
    color, font_family, size, weight, text_transform, letter_spacing
  },

  translation: {
    color, margin_left
  },

  verse_num: {
    color, font_family
  }
}
```

### New keys for container positions (future)
```json
{
  "containers": {
    "text":      { "x": "50%", "y": "45%", "width": "1200px", "height": "400px" },
    "reference": { "x": "50%", "y": "75%", "width": "800px",  "height": "120px" },
    "translation": { "follows": "reference" }
  }
}
```

### New keys for animations
```json
{
  "animations": {
    "display_enter": { "type": "fade_up", "duration_ms": 600, "easing": "ease-out" },
    "between_slides": { "out_type": "fade_down", "in_type": "fade_up", "duration_ms": 400, "easing": "ease-in-out" },
    "display_exit": { "type": "fade_down", "duration_ms": 400, "easing": "ease-out" }
  }
}
```

---

## 6. Preview Verses (Hardcoded)

These are embedded directly in the designer widgets, not fetched from the Bible database.
All KJV. Viewports match Live/Preview screen definition (16:9, 320–840px width).

| Position | Verse | KJV Text |
|----------|-------|----------|
| Light popup | Psalm 100:4 | "Enter his gates with thanksgiving, and into his courts with praise." |
| Full top | Matthew 3:11 | "I indeed baptize you with water unto repentance..." |
| Full bottom-left | John 11:35 | "Jesus wept." |
| Full bottom-right | Esther 8:9 | (full text — longest verse) |

---

## 7. Data Flow (Staged Save)

```
User edits property in designer
    ↓
ThemePropertiesPanel._collect_theme() builds in-memory dict
    ↓
theme_changed(dict) signal emitted
    ↓
Designer holds _working_theme (deep copy)
    ↓
Preview.apply_theme(_working_theme) — live preview updates
    ↓
User clicks Save
    ↓
core.theme_loader.save_theme(name, _working_theme) → writes themes/{name}.json
    ↓
theme_loader._check_for_changes() detects mtime change
    ↓
Hot-reloads into _cache
    ↓
Next get_theme() call returns updated dict
```

---

## 8. Files

### New files
- `ui/tabs/theme_designer_tab.py` — Full Theme Designer tab (three-column layout)
- `ui/widgets/theme_quick_editor.py` — Light popup panel (1280×720, right-click on theme card)
- `ui/widgets/theme_preview.py` — Reusable preview widget (DisplayView + AspectRatioWidget, 16:9)
- `ui/widgets/theme_properties_panel.py` — Shared property editors (element tree, color/font/weight inputs)
- `ui/widgets/theme_animations_panel.py` — Animation cards (Display Enter, Between Slides, Display Exit)

### Modified files
- `core/theme_loader.py` — Added `save_theme()` and `create_theme()` functions
- `ui/main_window.py` — Replaced `_init_theme_designer` stub with real ThemeDesignerTab, added `_open_theme_quick_editor`
- `ui/panels/themes_panel.py` — Added `contextMenuEvent` to `ThemeCard`, `theme_edit_requested` signal chain
- `ui/panels/queue_panel.py` — Bridged `theme_edit_requested` signal from ThemesPanel
- `display/display.js` — Added animation CSS injection, keyframe definitions, enter/cycle/exit animation support

---

## 9. Open Questions

- [ ] Container drag: snap to grid? pixel-nudge with arrow keys?
- [ ] Undo/redo support?
- [ ] Theme versioning / history?
- [ ] Animation preview: play/pause/scrub in the designer?
- [ ] Should "Edit in Full Designer" pass unsaved changes, or require save first?
