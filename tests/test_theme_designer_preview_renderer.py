"""Renderer page-hook tests for the Theme Designer replay API.

These use the same headless-Chrome harness as the v2 animation runtime tests,
so they drive the real display.js and embedded DisplayView renderer.
"""

from __future__ import annotations

import pytest

from tests.test_theme_v2_animation_runtime import RENDERERS, _drive

PREVIEW_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };
window.__payload = function (p) {
  return {action: "display", theme_data: window.__theme, ...p};
};
window.__snap = function (label) {
  window.__log.push({label: label, state: previewState()});
};
window.__run = async function () {
  const current = window.__payload({text: "Jesus wept.", reference: "John 11:35"});
  const alternate = window.__payload({text: "Alpha beta gamma.", reference: "Gen 1:1"});
  handlePayload(current);
  await window.__wait(500);

  previewReplay("entry", current, alternate);
  await window.__wait(40);
  window.__snap("entry-running");
  await window.__wait(400);
  window.__snap("entry-done");

  const before = previewState().token;
  applyTheme(window.__theme);
  window.__log.push({label: "style-only", token: before,
                     state: previewState()});

  previewReplay("transition_in", current, alternate);
  await window.__wait(40);
  window.__snap("transition-in-running");
  await window.__wait(500);
  window.__snap("transition-in-done");

  previewReplay("transition_out", current, alternate);
  await window.__wait(40);
  window.__snap("transition-out-running");
  await window.__wait(400);
  window.__snap("transition-out-done");

  previewReplay("out", current, alternate);
  await window.__wait(40);
  window.__snap("out-running");
  await window.__wait(400);
  window.__snap("out-done");

  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


@pytest.mark.skipif(
    __import__("tests.test_theme_v2_animation_runtime", fromlist=["CHROME"]).CHROME
    is None,
    reason="no Chrome/Chromium available",
)
@pytest.mark.parametrize("renderer", RENDERERS)
def test_preview_replay_hook_reports_each_phase(renderer):
    log = _drive(renderer, driver=PREVIEW_DRIVER, budget_ms=7000)

    entry = log["entry-running"]["state"]
    assert entry["phase"] == "entry"
    assert entry["status"] == "running"
    assert entry["animations"] >= 1
    assert log["entry-done"]["state"]["status"] == "finished"

    style = log["style-only"]
    assert style["state"]["token"] == style["token"]
    assert style["state"]["phase"] == "entry"

    for name in ("transition-in", "transition-out", "out"):
        running = log[name + "-running"]["state"]
        assert running["phase"] == name.replace("-", "_")
        assert running["status"] == "running"
        assert running["animations"] >= 1
        assert log[name + "-done"]["state"]["status"] == "finished"

    assert log["errors"]["errs"] == []
