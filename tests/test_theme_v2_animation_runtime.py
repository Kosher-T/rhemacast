"""Animation runtime tests for the v2 display engine.

The pure helpers are covered in tests/test_display_js.py under node. This
file drives the real renderer in headless Chrome because the contract is
timing and DOM state, not just data:

- `entry` plays on first display, and a same-content re-broadcast is silent.
- `transition.out` plays on the old content before the swap; `in` plays after.
- Typewriter splits into `[data-rc-tw]` spans, reveals, then unwraps back to
  the original text nodes.
- `out` per block plays on clear before the container is hidden.
- A rapid second update coalesces: the superseded content never renders.
- `prefers-reduced-motion: reduce` skips every phase and renders instantly.
- A block-level outline suppresses typewriter (fade_in fallback, no split).

Timing is driven by setTimeout in the renderer, so it stays reliable under
Chrome's virtual clock. WAAPI playback itself is compositor-driven and may be
frozen in headless dumps; assertions check that the animation exists,
starts on the right element, and gates the swap, not its interpolated paint.
"""

import copy
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))

RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]

THEME = {
    "schema_version": 2,
    "name": "animation_runtime",
    "kind": "scripture",
    "canvas": {"width": 1920, "height": 1080, "fit": "contain",
               "background": "transparent"},
    "containers": [{
        "id": "main", "visible": True, "layer": 1,
        "width": "100%", "height": "100%",
        "position": {"anchor": "center"},
        # Resolved themes fill this default; the renderer writes it inline.
        "opacity": 1,
        "blocks": {
            "body": {"visible": True, "valign": "center", "gap": 12,
                     "padding": 0},
            "text": {"visible": True, "size": 64, "color": "#ffffff",
                     "line_height": 1.2, "text_align": "center",
                     "animation": {"entry": "fade_up",
                                   "transition": {"out": "fade_down",
                                                  "in": "typewriter"},
                                   "out": "fade_out"}},
            "reference": {"visible": True, "size": 28, "color": "#dddddd"},
        },
    }],
    "animations": {
        "fade_up": {
            "type": "fade_up", "duration_ms": 300, "easing": "linear",
            "keyframes": [{"at": 0, "opacity": 0, "translate_y": 20},
                          {"at": 100, "opacity": "base", "translate_y": 0}],
        },
        "fade_down": {
            "type": "fade_down", "duration_ms": 300, "easing": "linear",
            "keyframes": [{"at": 0, "opacity": "base", "translate_y": 0},
                          {"at": 100, "opacity": 0, "translate_y": 20}],
        },
        "fade_out": {
            "type": "fade_out", "duration_ms": 300, "easing": "linear",
            "keyframes": [{"at": 0, "opacity": "base"},
                          {"at": 100, "opacity": 0}],
        },
        "typewriter": {
            "type": "typewriter", "duration_ms": 400, "delay_ms": 0,
            "easing": "linear", "reveal": "char",
            "cursor": {"char": "|", "color": "currentColor",
                       "blink_ms": 0, "hide_after_ms": 50},
        },
    },
}

DRIVER = r"""
window.__log = [];
window.__renders = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});


// Test instrumentation only: records each committed render so coalescing can
// prove that a superseded payload never reached the DOM.
const _origRender = _renderDisplay;
window._renderDisplay = function (data, silent, changed, phase) {
  window.__renders.push(data.text == null ? "" : String(data.text));
  return _origRender(data, silent, changed, phase);
};

window.__snap = function (label) {
  const vt = document.getElementById("verse-text");
  const ct = document.getElementById("container");
  const cs = ct ? getComputedStyle(ct) : null;
  const anims = vt && vt.getAnimations ? vt.getAnimations() : [];
  // The typewriter cursor is decoration, not content: drop it before
  // comparing text, or the insertion point splits the asserted word.
  let text = "";
  if (vt) {
    const copy = vt.cloneNode(true);
    copy.querySelectorAll(".rc-tw-cursor").forEach(e => e.remove());
    text = copy.textContent;
  }
  const dyn = Array.prototype.map.call(
    document.querySelectorAll(".rc-dynamic-container"),
    el => ({id: el.id, hidden: el.classList.contains("hidden"),
            opacity: getComputedStyle(el).opacity,
            visibility: getComputedStyle(el).visibility}));
  window.__log.push({
    label: label, t: +performance.now().toFixed(0),
    text: text,
    tw: document.querySelectorAll("[data-rc-tw]").length,
    anims: anims.length,
    running: anims.filter(a => a.playState === "running").length,
    opacity: vt ? getComputedStyle(vt).opacity : "",
    hidden: !!(ct && ct.classList.contains("hidden")),
    containerOpacity: cs ? cs.opacity : "",
    containerVisibility: cs ? cs.visibility : "",
    dyn: dyn,
  });
};
window.__payload = function (p) {
  handlePayload({action: "display", theme_data: window.__theme, ...p});
};
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };

window.__run = async function () {
  window.__payload({text: "Jesus wept.", reference: "John 11:35"});
  window.__snap("entry-start");
  await window.__wait(500);
  window.__snap("entry-done");

  window.__payload({text: "Jesus wept.", reference: "John 11:35"});
  window.__snap("same-content");

  window.__payload({text: "Alpha beta gamma.", reference: "Gen 1:1"});
  window.__snap("trans-out-start");
  await window.__wait(150);
  window.__snap("trans-out-mid");
  await window.__wait(350);
  window.__snap("trans-swapped");
  await window.__wait(2000);
  window.__snap("trans-done");

  handlePayload({action: "clear"});
  window.__snap("clear-start");
  await window.__wait(150);
  window.__snap("clear-mid");
  await window.__wait(400);
  window.__snap("clear-done");

  window.__payload({text: "First rapid.", reference: "A 1:1"});
  await window.__wait(1000);
  window.__snap("rapid-a-done");
  window.__payload({text: "Second rapid.", reference: "B 2:2"});
  await window.__wait(100);
  window.__payload({text: "Third rapid.", reference: "C 3:3"});
  window.__snap("rapid-c-start");
  await window.__wait(1500);
  window.__snap("rapid-c-done");

  window.__log.push({label: "renders", texts: window.__renders});
  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


CLOAK_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__snap = function (label) {
  const ct = document.getElementById("container");
  const cs = ct ? getComputedStyle(ct) : null;
  const dyn = Array.prototype.map.call(
    document.querySelectorAll(".rc-dynamic-container"),
    el => ({id: el.id, hidden: el.classList.contains("hidden"),
            opacity: getComputedStyle(el).opacity,
            visibility: getComputedStyle(el).visibility}));
  window.__log.push({
    label: label, t: +performance.now().toFixed(0),
    text: (document.getElementById("verse-text") || {}).textContent || "",
    hidden: !!(ct && ct.classList.contains("hidden")),
    containerOpacity: cs ? cs.opacity : "",
    containerVisibility: cs ? cs.visibility : "",
    containerDisplay: cs ? cs.display : "",
    dyn: dyn,
  });
};
window.__payload = function (p) {
  handlePayload({action: "display", theme_data: window.__theme, ...p});
};
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };

window.__run = async function () {
  window.__payload({text: "Magnify the Lord with me",
                    reference: "Psalm 34:3"});
  await window.__wait(200);
  window.__snap("displayed");

  // Cloak: out animation (if the theme has one), then a true blank.
  handlePayload({action: "clear"});
  window.__snap("clear-start");
  await window.__wait(500);
  window.__snap("clear-done");

  // Uncloak must bring the same content back, including dynamic containers.
  window.__payload({text: "Magnify the Lord with me",
                    reference: "Psalm 34:3"});
  await window.__wait(200);
  window.__snap("reopened");

  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _script_text(rel_path: str) -> str:
    src = (ROOT / rel_path).read_text()
    if rel_path.endswith(".py"):
        html = src.split('_DISPLAY_HTML = r"""', 1)[1].split('"""', 1)[0]
        src = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    return src


def _build_page(script_path: str, *, outline: bool = False,
                theme: dict | None = None, driver: str = DRIVER) -> str:
    theme = copy.deepcopy(theme if theme is not None else THEME)
    if outline:
        theme["containers"][0]["blocks"]["text"]["text_outline"] = "2px #000000"
    html = (ROOT / "display/display.html").read_text()
    css = (ROOT / "display/themes.css").read_text()
    css = css.replace("url('./fonts/",
                      "url('file://" + str(ROOT / "display/fonts") + "/")
    html = html.replace('<link rel="stylesheet" href="themes.css">',
                        f"<style>{css}</style>")
    html = html.replace('<script src="display.js"></script>',
                        f"<script>{_script_text(script_path)}</script>")
    html = html.replace(
        "</head>",
        "<script>window.WebSocket = function () {this.close = function () {};"
        "this.send = function () {}; this.readyState = 3;}</script></head>", 1)
    boot = ("<script>window.__theme = " + json.dumps(theme) + ";\n" + driver
            + "__run();</script>")
    return html.replace("</body>", boot + "</body>", 1)


def _drive(script_path: str, *, reduced: bool = False,
           outline: bool = False, theme: dict | None = None,
           driver: str = DRIVER, budget_ms: int = 15000) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="rc-anim-runtime-"))
    try:
        page = tmp / "page.html"
        page.write_text(_build_page(script_path, outline=outline,
                                    theme=theme, driver=driver))
        args = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--window-size=1920,1080", "--force-device-scale-factor=1",
                f"--user-data-dir={tmp / 'profile'}", "--no-first-run",
                f"--virtual-time-budget={budget_ms}", "--dump-dom"]
        if reduced:
            args.insert(1, "--force-prefers-reduced-motion")
        out = subprocess.run(args + [page.as_uri()], capture_output=True,
                             text=True, timeout=120).stdout
        found = re.findall(
            r'<script[^>]*data-rc="log"[^>]*>(.*?)</script>', out, re.S)
        assert found, f"renderer produced no log: {out[:1000]}"
        log = json.loads(found[-1])
        return {entry["label"]: entry for entry in log
                if "label" in entry}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_animation_runtime(renderer):
    log = _drive(renderer)
    entry = log["entry-start"]
    assert entry["text"] == "35 Jesus wept."
    assert entry["anims"] >= 1 and entry["running"] >= 1
    assert entry["opacity"] == "0"

    assert log["entry-done"]["opacity"] == "1"
    assert log["same-content"]["anims"] == 0

    # The old content plays out before the swap.
    assert log["trans-out-start"]["text"] == "35 Jesus wept."
    assert log["trans-out-start"]["anims"] >= 1
    assert log["trans-out-mid"]["text"] == "35 Jesus wept."
    swapped = log["trans-swapped"]
    assert "Alpha beta gamma." in swapped["text"]
    assert swapped["tw"] > 0

    # Typewriter completion restores the text nodes.
    assert log["trans-done"]["tw"] == 0
    assert log["trans-done"]["text"] == "1 Alpha beta gamma."

    # Per-block out on clear, hidden only after it finishes.
    assert log["clear-start"]["hidden"] is False
    assert log["clear-start"]["anims"] >= 1
    assert log["clear-mid"]["hidden"] is False
    assert log["clear-done"]["hidden"] is True
    # Hidden means invisible, not just transformed: resolved themes write
    # `opacity` inline, so the blank state must beat that cascade.
    assert log["clear-done"]["containerOpacity"] == "0"
    assert log["clear-done"]["containerVisibility"] == "hidden"

    # Coalescing: the superseded payload never commits.
    assert log["rapid-a-done"]["text"] == "1 First rapid."
    assert "First rapid." in log["rapid-c-start"]["text"]
    assert log["rapid-c-done"]["text"] == "3 Third rapid."
    assert "Second rapid." not in log["renders"]["texts"]

    assert log["errors"]["errs"] == []


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_animation_reduced_motion(renderer):
    log = _drive(renderer, reduced=True)

    assert log["entry-start"]["anims"] == 0
    assert log["entry-start"]["opacity"] == "1"
    assert log["trans-out-start"]["text"] == "1 Alpha beta gamma."
    assert log["trans-out-start"]["anims"] == 0
    assert log["clear-start"]["hidden"] is True
    assert log["clear-start"]["containerOpacity"] == "0"
    assert log["clear-start"]["containerVisibility"] == "hidden"
    assert log["rapid-c-start"]["text"] == "3 Third rapid."
    assert log["rapid-c-start"]["anims"] == 0
    assert all(s["tw"] == 0 for s in log.values() if "tw" in s)
    assert log["errors"]["errs"] == []


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_typewriter_falls_back_under_outline(renderer):
    """A converted outline scope cannot be re-split into spans."""
    log = _drive(renderer, outline=True)
    swapped = log["trans-swapped"]
    assert swapped["tw"] == 0
    assert swapped["anims"] >= 1
    assert log["trans-done"]["tw"] == 0
    assert log["errors"]["errs"] == []


def _two_container_theme() -> dict:
    theme = copy.deepcopy(THEME)
    theme["name"] = "animation_runtime_multi"
    main = theme["containers"][0]
    main["width"] = "50%"
    main["height"] = "100%"
    main["position"] = {"anchor": "left"}
    side = copy.deepcopy(main)
    side["id"] = "side"
    side["layer"] = 2
    side["position"] = {"anchor": "right"}
    theme["containers"] = [main, side]
    return theme


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_cloak_hides_a_shipped_resolved_theme(renderer):
    """Cloak is a blank screen, not a nudge.

    Resolved themes carry `container.opacity: 1`, which the renderer writes
    inline. The cleared state must still win that cascade: the old behavior
    left the verse visible at the hidden transform, shifted 40px down.
    """
    from core.theme_loader import resolve_theme
    _, theme = resolve_theme("fullscreen")
    log = _drive(renderer, theme=theme, driver=CLOAK_DRIVER)

    shown = log["displayed"]
    assert shown["hidden"] is False
    assert shown["containerOpacity"] == "1"
    assert shown["containerVisibility"] == "visible"
    assert "Magnify the Lord with me" in shown["text"]

    blank = log["clear-done"]
    assert blank["hidden"] is True
    assert blank["containerOpacity"] == "0"
    assert blank["containerVisibility"] == "hidden"

    reopened = log["reopened"]
    assert reopened["hidden"] is False
    assert reopened["containerOpacity"] == "1"
    assert reopened["containerVisibility"] == "visible"
    assert "Magnify the Lord with me" in reopened["text"]
    assert log["errors"]["errs"] == []


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_cloak_and_uncloak_restore_dynamic_containers(renderer):
    """A clear hides every dynamic container; the next render must unhide
    them, not just rewrite their styles around a stale `.hidden` class."""
    log = _drive(renderer, theme=_two_container_theme(), driver=CLOAK_DRIVER)

    shown = log["displayed"]["dyn"]
    assert len(shown) == 2
    assert all(d["hidden"] is False for d in shown)
    assert all(d["opacity"] == "1" for d in shown)

    blank = log["clear-done"]["dyn"]
    assert len(blank) == 2
    assert all(d["hidden"] is True for d in blank)
    assert all(d["opacity"] == "0" for d in blank)
    assert all(d["visibility"] == "hidden" for d in blank)

    reopened = log["reopened"]["dyn"]
    assert len(reopened) == 2
    assert all(d["hidden"] is False for d in reopened)
    assert all(d["opacity"] == "1" for d in reopened)
    assert all(d["visibility"] == "visible" for d in reopened)
    assert log["errors"]["errs"] == []


# ─── Showcase themes: v2-only features in the real renderers ─────────
# These drive the shipped showcase themes end-to-end, not a synthetic theme:
# per-side borders, per-container block ownership and min_height panels are
# contracts of the v2 schema that a purely data-level test cannot cover.

SHOWCASE = ["fullscreen_rise", "fullscreen_pop", "fullscreen_split",
            "default_typewriter", "default_quiet", "reference_frames",
            "reference_letterbox", "slides_motion"]

STRUCTURE_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
function box(el) {
  const s = getComputedStyle(el);
  return {top: s.borderTopWidth, right: s.borderRightWidth,
          bottom: s.borderBottomWidth, left: s.borderLeftWidth,
          radius: s.borderRadius, minHeight: el.style.minHeight,
          height: Math.round(el.getBoundingClientRect().height)};
}
window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__theme,
                 text: "The Lord is my shepherd; I shall not want.",
                 reference: "Psalm 23:1", translation: "KJV"});
  await new Promise(r => setTimeout(r, 400));
  const ct = document.getElementById("container");
  window.__log.push({
    label: "shown",
    container: box(ct),
    dyn: Array.prototype.map.call(
      document.querySelectorAll(".rc-dynamic-container"),
      el => Object.assign({id: el.id,
                           texts: el.querySelectorAll(".verse-text").length,
                           refs: el.querySelectorAll(".verse-ref-text").length},
                          box(el))),
    texts: document.querySelectorAll(".verse-text").length,
    refs: document.querySelectorAll(".verse-ref-text").length,
    errors: window.__errs.slice(),
  });
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _resolve(name: str) -> dict:
    from core.theme_loader import resolve_theme
    _, theme = resolve_theme(name)
    return theme


_BAR_LONG_VERSE = (
    "And the king's scribes were called at that time in the third month, "
    "that is, the month Sivan, on the three and twentieth day thereof; and "
    "it was written according to all that Mordecai commanded unto the Jews, "
    "and to the lieutenants, and the deputies and rulers of the provinces "
    "which are from India unto Ethiopia, an hundred twenty and seven "
    "provinces, unto every province according to the writing thereof, and "
    "unto every people after their language, and to the Jews according to "
    "their writing, and according to their language."
)

_BAR_FIT_DRIVER = r"""
window.__log = [];
window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__theme,
                 text: window.__text, reference: "Esther 8:9",
                 translation: "KJV"});
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await new Promise(r => setTimeout(r, 250));
  const box = document.getElementById("container");
  const h1 = document.getElementById("verse-text");
  const ref = document.getElementById("verse-ref");
  const cs = getComputedStyle(box);
  const pad = (parseFloat(cs.paddingTop) || 0)
      + (parseFloat(cs.paddingBottom) || 0);
  const autoPx = parseFloat(getComputedStyle(h1).fontSize);
  h1.style.fontSize = window.__min + "px";
  invalidateOutlines();
  applyOutlineLayers();
  const line = parseFloat(getComputedStyle(h1).lineHeight)
      || window.__min * 1.2;
  const margin = parseInt(getComputedStyle(h1).marginBottom) || 0;
  const gap = parseFloat(cs.rowGap) || 0;
  window.__log.push({
    label: "fit", minPx: window.__min, autoPx: autoPx, line: line,
    total: h1.offsetHeight + margin + ref.offsetHeight + gap,
    contentH: box.clientHeight - pad,
    clientH: box.clientHeight, scrollH: box.scrollHeight,
  });
  const tag = document.createElement("script"); tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
@pytest.mark.parametrize("theme_name", ["reference_frames", "reference_letterbox"])
def test_v2_reference_bars_fit_a_long_verse_at_min_size(renderer, theme_name):
    """Esther 8:9 (527 chars) must fit with a line to spare at the floor."""
    theme = _resolve(theme_name)
    text = theme["containers"][0]["blocks"]["text"]
    min_px = float(str(text["min_size"]).replace("px", ""))
    driver = ("window.__text = " + json.dumps(_BAR_LONG_VERSE)
              + "; window.__min = " + str(min_px) + ";\n" + _BAR_FIT_DRIVER)
    log = _drive(renderer, theme=theme, driver=driver)["fit"]
    # Autofit may not go below the authored floor.
    assert log["autoPx"] >= log["minPx"] - 0.5
    # At the floor the verse, margin, gap, reference and one more line fit.
    assert log["total"] + log["line"] <= log["contentH"] + 1
    assert log["scrollH"] <= log["clientH"] + 1


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_reference_frames_renders_authored_border_sides(renderer):
    """border.sides is a per-side contract, not decoration.

    reference_frames declares 1px top/bottom and 5px left/right. A renderer
    that only understands the base shorthand paints four equal sides (or the
    previous container's border) while the schema still validates.
    """
    log = _drive(renderer, theme=_resolve("reference_frames"),
                 driver=STRUCTURE_DRIVER)
    shown = log["shown"]
    assert shown["errors"] == []
    box = shown["container"]
    assert (box["top"], box["bottom"]) == ("1px", "1px")
    assert (box["left"], box["right"]) == ("5px", "5px")
    assert box["radius"] == "18px"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_multi_container_blocks_stay_in_their_container(renderer):
    """A container renders only the blocks it declares.

    fullscreen_split's citation panel declares `reference`/`translation` and
    no `text`; `_getContainerBlocks` fills missing keys with `{}` (truthy), so
    the panel used to duplicate the verse and paint it with the verse panel's
    gold frame.
    """
    log = _drive(renderer, theme=_resolve("fullscreen_split"),
                 driver=STRUCTURE_DRIVER)
    shown = log["shown"]
    assert shown["errors"] == []
    assert shown["texts"] == 1
    assert shown["refs"] == 1
    containers = {d["id"]: d for d in shown["dyn"]}
    verse = containers["rc-cont-verse"]
    cite = containers["rc-cont-cite"]
    assert (verse["texts"], verse["refs"]) == (1, 0)
    assert (cite["texts"], cite["refs"]) == (0, 1)
    assert verse["top"] == "2px"
    assert cite["top"] == "1px"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_min_height_panel_is_applied(renderer):
    """`height: auto` + `min_height` must produce the authored panel height.

    The single-container path writes --rc-width/--rc-height only; without an
    inline min/max height the panel collapses to its content (~360px) instead
    of the 860px fullscreen_rise asks for.
    """
    log = _drive(renderer, theme=_resolve("fullscreen_rise"),
                 driver=STRUCTURE_DRIVER)
    shown = log["shown"]
    assert shown["errors"] == []
    assert shown["container"]["minHeight"] == "860px"
    # The preview scales the 1080px stage into its viewport; both renderers
    # must still be clearly taller than the collapsed content height.
    assert shown["container"]["height"] > 700


def _showcase_driver(themes: dict) -> str:
    return r"""
window.__themes = __THEMES__;
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__run = async function () {
  for (const name of Object.keys(window.__themes)) {
    handlePayload({action: "display", theme_data: window.__themes[name],
                   text: "The Lord is my shepherd; I shall not want.",
                   reference: "Psalm 23:1", translation: "KJV"});
    await new Promise(r => setTimeout(r, 2600));
    const ct = document.getElementById("container");
    window.__log.push({
      label: name,
      hidden: ct.classList.contains("hidden"),
      dyn: Array.prototype.map.call(
        document.querySelectorAll(".rc-dynamic-container"),
        el => ({id: el.id, hidden: el.classList.contains("hidden"),
                opacity: getComputedStyle(el).opacity,
                visibility: getComputedStyle(el).visibility})),
      // Static markup names these by id (#verse-text); multi-container
      // themes build class-named elements. Count either, with content.
      texts: Array.prototype.filter.call(
        document.querySelectorAll(
          "#verse-text, .verse-text, #verse-ref-text, .verse-ref-text"),
        el => (el.textContent || "").trim().length > 0).length,
      errors: window.__errs.slice(),
    });
    handlePayload({action: "clear"});
    await new Promise(r => setTimeout(r, 1400));
    window.__log.push({
      label: name + ":cleared",
      hidden: ct.classList.contains("hidden"),
      dynHidden: Array.prototype.map.call(
        document.querySelectorAll(".rc-dynamic-container"),
        el => el.classList.contains("hidden")),
      errors: window.__errs.slice(),
    });
  }
  window.__log.push({label: "errors", errs: window.__errs.slice()});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
""".replace("__THEMES__", json.dumps(themes))




STYLE_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
function report(id) {
  const h1 = document.querySelector("#rc-cont-" + id + " .verse-text");
  const s = h1 ? getComputedStyle(h1) : null;
  return {
    found: !!h1,
    wordSpacing: s ? s.wordSpacing : "",
    fontStyle: s ? s.fontStyle : "",
    decoration: s ? s.textDecorationLine : "",
    direction: s ? s.direction : "",
    clamp: s ? (s.webkitLineClamp || "") : "",
    inlineDisplay: h1 ? h1.style.display : "",
    display: s ? s.display : "",
    overflow: s ? s.overflow : "",
    clientH: h1 ? h1.clientHeight : -1,
    scrollH: h1 ? h1.scrollHeight : -1,
    svg: h1 ? h1.querySelectorAll("svg").length : -1,
    attempted: !!(h1 && h1.dataset && h1.dataset.rcOcSrc !== undefined),
    text: h1 ? h1.textContent.replace(/\s+/g, " ").trim() : "",
  };
}
window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__theme,
                 text: "The Lord is my shepherd; I shall not want. He maketh "
                       + "me to lie down in green pastures; he leadeth me "
                       + "beside the still waters. He restoreth my soul.",
                 reference: "Psalm 23:1", translation: "KJV"});
  await new Promise(r => setTimeout(r, 500));
  window.__log.push({label: "shown", main: report("main"), side: report("side"),
                     errors: window.__errs.slice()});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_multi_container_text_block_typography(renderer):
    """Per-block typography and line clamp survive the split renderer.

    The single-container path gets these from CSS variables; the
    multi-container path builds its own h1 and used to apply only colour,
    size, weight, family, line-height, spacing and alignment. The outline
    case also proves the block scope converts on a panel element, whose
    text is measured while #verse-text is display:none.
    """
    theme = _two_container_theme()
    main_text = theme["containers"][0]["blocks"]["text"]
    main_text.update({"word_spacing": 6, "font_style": "italic",
                      "text_decoration": "underline", "direction": "rtl",
                      "max_lines": 2})
    theme["containers"][1]["blocks"]["text"]["text_outline"] = "2px #ff0000"

    shown = _drive(renderer, theme=theme, driver=STYLE_DRIVER)["shown"]
    assert shown["errors"] == []

    main = shown["main"]
    assert main["found"] is True
    assert main["wordSpacing"] == "6px"
    assert main["fontStyle"] == "italic"
    assert main["decoration"] == "underline"
    assert main["direction"] == "rtl"
    assert main["inlineDisplay"] == "-webkit-box"
    assert main["clamp"] == "2"
    assert main["overflow"] == "hidden"
    # Clamping is paint-level: the box keeps two lines while the content
    # overflows it. Chromium reports the computed display as flow-root even
    # for -webkit-box, so the inline declaration plus the clipped box are
    # the contract.
    assert main["scrollH"] > main["clientH"] > 0
    assert "The Lord is my shepherd" in main["text"]

    side = shown["side"]
    assert side["attempted"] is True
    assert side["svg"] >= 1
    assert "TheLordismyshepherd" in side["text"].replace(" ", "")




FIT_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__theme,
    text: "So the king's scribes were called at that time, in the third month, "
          + "which is the month of Sivan, on the twenty-third day; and it was "
          + "written, according to all that Mordecai commanded, to the Jews, "
          + "the satraps, the governors, and the princes of the provinces from "
          + "India to Ethiopia, one hundred and twenty-seven provinces in all, "
          + "to every province in its own script, to every people in their own "
          + "language, and to the Jews in their own script and language.",
    reference: "Esther 8:9", translation: "KJV"});
  await new Promise(r => setTimeout(r, 900));
  const ct = document.getElementById("container");
  const cs = getComputedStyle(ct);
  const vt = document.getElementById("verse-text");
  const ref = document.getElementById("verse-ref");
  const pad = (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
  const contentH = ct.clientHeight - pad;
  const margin = parseInt(getComputedStyle(vt).marginBottom) || 0;
  const total = vt.offsetHeight + margin + ref.offsetHeight;
  window.__log.push({label: "shown",
    clientH: ct.clientHeight,
    contentH: Math.round(contentH),
    fontPx: parseFloat(vt.style.fontSize) || 0,
    total: Math.round(total),
    fits: total <= contentH + 2,
    errors: window.__errs.slice()});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_min_height_panel_autosizes_long_text(renderer):
    """`autosize` on a min_height panel must shrink text, not grow the panel.

    `height:auto` + `min-height` lets an overflowing verse expand the panel
    until the stage clips it (the preview showed exactly that). The fit target
    is the authored min_height/max_height minus the panel's own padding and
    border, and the fit repeats on the next frame and after webfonts settle.
    """
    shown = _drive(renderer, theme=_resolve("default_typewriter"),
                   driver=FIT_DRIVER)["shown"]
    assert shown["errors"] == []
    assert shown["fits"] is True
    assert shown["fontPx"] < 78          # shrank from the authored size
    assert shown["fontPx"] >= 52         # but never below min_size
    # The panel stays at its authored ~840px (a few px of refit tolerance)
    # instead of growing to the overflowing text's height.
    assert shown["clientH"] <= 900




PANEL_FIT_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__theme,
    text: "The king's scribes were called at that time, in the third month, "
          + "which is the twenty-third day; and it was written according to "
          + "all that Mordecai commanded, to the Jews, and to the governors, "
          + "and officials of the 127 provinces from India to Ethiopia. This "
          + "letters were written to each province in its own language and "
          + "system of writing and to the Jews in their language and system "
          + "of writing.",
    reference: "Esther 8:9", translation: "GNB"});
  // The renderer refits panels once webfonts settle; measure after that,
  // otherwise the snapshot can catch the pre-font metrics.
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  await new Promise(r => setTimeout(r, 300));
  const panels = Array.from(document.querySelectorAll(".rc-dynamic-container"))
    .map(function (el) {
      const cs = getComputedStyle(el);
      const h1 = el.querySelector(".verse-text");
      const ref = el.querySelector(".verse-ref");
      const pad = (parseFloat(cs.paddingTop) || 0)
        + (parseFloat(cs.paddingBottom) || 0);
      const gap = parseFloat(cs.rowGap) || 0;
      const contentH = el.clientHeight - pad;
      const total = h1 ? h1.offsetHeight
        + (parseInt(getComputedStyle(h1).marginBottom) || 0)
        + (ref ? ref.offsetHeight : 0) + (ref ? gap : 0) : 0;
      return {id: el.id, clientH: el.clientHeight,
              font: h1 ? parseFloat(h1.style.fontSize) : null,
              hasText: !!h1, total: Math.round(total),
              fits: !h1 || total <= contentH + 2};
    });
  window.__log.push({label: "shown", panels,
                     errors: window.__errs.slice()});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_multi_container_autosizes_each_panel(renderer):
    """Each split panel fits its own text block, not the authored size.

    The multi-container path skipped autosize entirely: `fullscreen_split`
    rendered its 76px verse at 1067px tall inside a 780px panel and clipped
    both edges. Every panel now fits between its block's min_size/max_size
    against its own content box, independent of the other panels.
    """
    shown = _drive(renderer, theme=_resolve("fullscreen_split"),
                   driver=PANEL_FIT_DRIVER)["shown"]
    assert shown["errors"] == []
    panels = {p["id"]: p for p in shown["panels"]}
    verse = panels["rc-cont-verse"]
    assert verse["fits"] is True
    assert verse["font"] < 76        # shrank from the authored size
    assert verse["font"] >= 46       # never below the block's min_size
    assert verse["clientH"] >= 770   # fixed panel height held
    # The cite panel authors no text block, so it must never receive a verse
    # copy; its reference/translation still fit.
    cite = panels["rc-cont-cite"]
    assert cite["hasText"] is False
    assert cite["fits"] is True




SPLIT_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});

// Record the schedule each unit asks for. Reading live WAAPI objects races
// font/layout work; the recorded calls are the same per-unit mapping.
window.__animLog = new WeakMap();
const _origAnimate = Element.prototype.animate;
Element.prototype.animate = function (frames, opts) {
  if (!window.__animLog.has(this)) window.__animLog.set(this, []);
  window.__animLog.get(this).push({
    delay: (opts && opts.delay) || 0,
    duration: (opts && opts.duration) || 0,
  });
  return _origAnimate.call(this, frames, opts);
};

function _textEl() {
  return document.querySelector("#rc-cont-main .verse-text")
      || document.getElementById("verse-text");
}

function _unitReport() {
  const el = _textEl();
  if (!el) return {found: false};
  const units = Array.from(el.querySelectorAll('[data-rc-unit="1"]'));
  const wordOf = function (u) {
    return u.classList.contains("rc-split-word")
        ? u : u.querySelector(".rc-split-word");
  };
  return {
    found: true,
    split: el.dataset.rcSplit || "",
    count: units.length,
    texts: units.map(u => (u.textContent || "").trim()),
    firstColor: units.length
        ? getComputedStyle(wordOf(units[0]) || units[0]).color : "",
    restColor: units.length > 1
        ? getComputedStyle(wordOf(units[1]) || units[1]).color : "",
    restOpacity: units.length > 1 ? getComputedStyle(units[1]).opacity : "",
    anims: units.slice(0, 6).map(function (u) {
      return (window.__animLog && window.__animLog.get(u)) || [];
    }),
  };
}

window.__run = async function () {
  handlePayload({action: "display", theme_data: window.__themes.line,
    text: "The Lord is my shepherd; I shall not want. ".repeat(12),
    reference: "Psalm 23:1", translation: "KJV"});
  await new Promise(r => setTimeout(r, 120));
  window.__log.push({label: "line", main: _unitReport(),
                     errors: window.__errs.slice()});

  // look.opacity is the resting state; the entry animation owns opacity while
  // it plays. Cancel back to rest (what finish cleanup does) and read again.
  const lineUnits = Array.from(_textEl().querySelectorAll('[data-rc-unit="1"]'));
  const restUnit = lineUnits.length > 1 ? lineUnits[1] : null;
  const restWord = restUnit && (restUnit.classList.contains("rc-split-word")
    ? restUnit : restUnit.querySelector(".rc-split-word"));
  lineUnits.forEach(function (u) {
    if (!u.getAnimations) return;
    u.getAnimations().forEach(function (a) {
      try { a.cancel(); } catch (e) {}
    });
  });
  await new Promise(r => setTimeout(r, 0));
  window.__log.push({label: "line_rest", restOpacity: restUnit
    ? getComputedStyle(restUnit).opacity : "",
    // Opacity multiplies: a line look must not repaint its own words.
    restWordOpacity: restWord ? getComputedStyle(restWord).opacity : ""});

  handlePayload({action: "display", theme_data: window.__themes.word,
    text: "One two three four five six",
    reference: "Psalm 23:1", translation: "KJV"});
  await new Promise(r => setTimeout(r, 120));
  window.__log.push({label: "word", main: _unitReport(),
                     errors: window.__errs.slice()});

  // Same resting-style read as the line pass: a running entry animation owns
  // opacity, so cancel before asserting the authored look.
  const wordUnits = Array.from(_textEl().querySelectorAll('[data-rc-unit="1"]'));
  const wordRestUnit = wordUnits.length > 1 ? wordUnits[1] : null;
  wordUnits.forEach(function (u) {
    if (!u.getAnimations) return;
    u.getAnimations().forEach(function (a) {
      try { a.cancel(); } catch (e) {}
    });
  });
  await new Promise(r => setTimeout(r, 0));
  window.__log.push({label: "word_rest", restOpacity: wordRestUnit
    ? getComputedStyle(wordRestUnit).opacity : ""});

  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _split_theme(by: str) -> dict:
    theme = copy.deepcopy(THEME)
    # Keep the authored 64px: a raw "100%" height makes autoFitText chase a
    # percentage target and collapse the text to the 12px floor.
    theme["containers"][0]["height"] = "auto"
    theme["containers"][0]["blocks"]["text"]["animation"] = {
        "entry": {"type": "fade_in", "duration_ms": 400},
        "transition": {"in": {"type": "fade_in", "duration_ms": 400}},
        "split": {
            "by": by,
            "stagger_ms": 40,
            "first": {
                "entry": {"type": "scale_up", "duration_ms": 200,
                          "easing": "linear"},
                "transition": {"in": {"type": "scale_up", "duration_ms": 200,
                                      "easing": "linear"}},
            },
            "rest": {
                "entry": {"type": "fade_up", "duration_ms": 500,
                          "easing": "linear"},
                "transition": {"in": {"type": "fade_up", "duration_ms": 500,
                                      "easing": "linear"}},
            },
            "look": {"first": {"color": "rgb(255, 209, 102)"},
                     "rest": {"opacity": 0.7}},
        },
    }
    return theme


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_split_animation_is_computed_per_line_and_word(renderer):
    """`split` builds units from the rendered layout, not the source text.

    Line units are the browser's own line boxes after autofit; each unit
    resolves its own first/rest assignment and look, and the stagger delay
    is index * stagger_ms on top of the definition delay.
    """
    driver = SPLIT_DRIVER.replace(
        "window.__themes.word", json.dumps(_split_theme("word")))
    driver = ("window.__themes = {line: " + json.dumps(_split_theme("line"))
              + ", word: " + json.dumps(_split_theme("word")) + "};\n"
              + driver)

    log = _drive(renderer, theme=_split_theme("line"), driver=driver)
    line = log["line"]["main"]
    assert log["line"]["errors"] == []
    assert line["split"] == "line"
    assert line["count"] >= 4
    assert all(t for t in line["texts"])
    # First line: scale_up/200; rest: fade_up/500, 40ms apart.
    assert line["anims"][0][0] == {"delay": 0, "duration": 200}
    assert line["anims"][1][0] == {"delay": 40, "duration": 500}
    assert line["anims"][2][0] == {"delay": 80, "duration": 500}
    assert line["firstColor"] == "rgb(255, 209, 102)"
    assert line["restColor"] != line["firstColor"]
    assert log["line_rest"]["restOpacity"] == "0.7"
    assert log["line_rest"]["restWordOpacity"] == "1"

    word = log["word"]["main"]
    assert log["word"]["errors"] == []
    assert word["split"] == "word"
    assert word["count"] == 6
    assert [a[0]["delay"] for a in word["anims"][:4]] == [0, 40, 80, 120]
    assert [a[0]["duration"] for a in word["anims"][:4]] == [200, 500, 500, 500]
    assert word["firstColor"] == "rgb(255, 209, 102)"
    assert log["word_rest"]["restOpacity"] == "0.7"
    # The line count is a layout result, not the word count.
    assert line["count"] != word["count"]


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_showcase_themes_render_and_cloak(renderer):
    """Every shipped showcase theme displays content and cloaks to a blank."""
    themes = {name: _resolve(name) for name in SHOWCASE}
    log = _drive(renderer, theme=themes[SHOWCASE[0]],
                 driver=_showcase_driver(themes), budget_ms=60000)

    assert log["errors"]["errs"] == []
    for name in SHOWCASE:
        shown = log[name]
        assert shown["errors"] == [], name
        assert shown["texts"] >= 1, name
        if shown["dyn"]:
            # Multi-container themes hide #container by design; the panels
            # themselves are the visible surface.
            assert all(not d["hidden"] for d in shown["dyn"]), name
            assert all(d["visibility"] == "visible" for d in shown["dyn"]), name
        else:
            assert shown["hidden"] is False, name

        cleared = log[name + ":cleared"]
        assert cleared["hidden"] is True, name
        assert all(cleared["dynHidden"]), name
