# Theme Switch Contract

Normative spec for the single display-switch primitive (P1 in
`docs/design-principles.md`). All code changes to switching behavior are
made against this document.

## The primitive

```
switch(content_kind, content, theme_name) -> payload -> renderer
```

One choke point (`core/display_switch.py` — to be built) owns payload
construction. Tabs supply content + theme selection only.

## Payload schema

Every switch payload carries **all** of the following; no field is
optional on the wire:

| Field          | Meaning                                                   |
|----------------|-----------------------------------------------------------|
| `action`       | `"display"` or `"clear"`                                  |
| `content_kind` | `verse` · `slide` · `image` · `video` · `pptx` (registry below) |
| `content`      | kind-specific content (text/ref for verse+slide; URI for media) |
| `slide_format` | deck-level overrides, or explicitly `null` (never absent) |
| `theme`        | theme name (audit label)                                  |
| `theme_data`   | **full theme dict, guaranteed non-null**                  |

Guarantee: `theme_data` is never null. Unknown theme name → `"default"`
theme dict + error log naming the bad configured name. A renderer must be
able to render any payload in isolation, with no memory of previous
payloads.

## Renderer three-step (all renderers, all kinds, no exceptions)

```
1. resetTheme()   — remove every --rc-* custom property (unconditional)
2. applyTheme()   — set properties from theme_data, then slide_format cascade
3. renderContent() — kind-specific content paint into the themed stage
```

Same-theme switches run all three steps (reset is never skipped —
cheap insurance against the entire stale-carryover class).

## Screen resync (tab switching)

Hidden views receive every publish but present their last committed
frame until a fresh one commits. Arriving on a tab therefore runs a
cover-gated silent refresh: opaque covers go up first, `refreshPayload`
/ `refreshClear` re-render with no animation replay and no
transition-memory writes, and covers come down only after 2 presented
frames ack (500ms timer as fallback). Replaying the enter animation on
arrival is its own flicker — silent means silent.

## Convergence requirement

Renderer state after a payload is a pure function of that payload:

- Applying payload B after payload A yields state(B) — never
  state(A)+state(B).
- Applying the same payload twice yields identical state (idempotent).
- A→B→A yields the exact pre-A state (no drift).
- A payload arriving with `theme_data` but no other history renders
  correctly (late joiners, reconnects, cache-cleared OBS all converge).

## Content-kind registry

| Kind    | Status   | Notes                                              |
|---------|----------|----------------------------------------------------|
| `verse` | live     | scripture text + reference + translation           |
| `slide` | live     | deck text + `slide_format` cascade + title rules   |
| `clear` | live     | blank (invisibility cloak; model advances, no pixels) |
| `image` | future   | stills under the same three-step switch            |
| `video` | future   | motion under the same three-step switch            |
| `pptx`  | documented future — **no UI, no code**. Slot reserved here so the switch stays kind-agnostic. Theme-section sketch: title/body text map onto the existing `--rc-text-*` vars; per-slide master styles map onto `slide_format`-shaped overrides. Nothing is implemented; nothing is shown. |

Rule: adding a kind registers a `renderContent` branch. It must not add a
broadcast path, a payload builder, or a theme namespace.

## Per-machine state (inputs, not preconditions)

The switch must be correct regardless of these; they vary per machine
and are gitignored or cached, so they can never be preconditions:

- settings DB / `config.json` theme names (may name missing themes →
  fallback rule applies);
- `themes/*.json` files (operator-editable; parse failure → theme
  missing → fallback rule applies);
- OBS / browser caches of `display.js` / `themes.css` (assets versioned;
  stale renderer still converges because every payload is complete).

## Current-code gap map (what implementing this changes)

1. `display/display.js:597-602` + `ui/widgets/display_view.py` mirror —
   add reset-before-className-fallback (immediate hardening).
2. `ui/tabs/presentation_tab.py:287-318` `_build_payload` and
   `ui/tabs/slides_tab.py:243-268` — retire into thin callers of the
   choke point. `presentation_tab.py:1151-1161` rebuild must preserve
   `content`/`deck_id` (today drops them, defaults `verse`).
3. Theme namespaces (`_themes_by_output` vs slides/verse dual maps) —
   merge into per-output resolution inside the choke point.
4. `core/theme_loader.py:128-132` `get_theme` silent-`None` + live refs —
   add `resolve_theme()` (fallback + loud warning + deepcopy).
5. `display/display.html:35` unversioned `display.js` — version query/hash.
6. Unify the two JS copies (single source; embedded copy generated).
7. Tests: payload-completeness contract test; `resetTheme` ⊇
   `applyTheme` coverage test over both copies (then over the single
   source).
