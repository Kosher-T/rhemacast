"""Session-wide test isolation.

The application's settings live in `data/app.db`, and `core.database`
reads its module-level `DB_PATH` on every connection — so any test that
calls `set_setting` without redirecting that path writes the OPERATOR'S
real settings. That has happened for real: `search.fts_translations` was
silently rewritten by test runs, which then made the FTS index and the
search lane disagree with each other and produced failures that looked
like product bugs.

Redirecting the path once, for the whole session, is the only reliable
place to do it — per-test monkeypatching misses every test that reaches
`get_setting` indirectly (through `core.bible_service`, a panel, or a
settings helper), and misses all of them once a connection was opened
before the patch.
"""

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _guard_unstubbed_dialogs():
    """Fail fast when a test opens a real modal dialog.

    A forgotten stub otherwise parks the test run on a dialog nobody can
    click. Every public entry point in ``ui.dialogs`` is replaced for the
    session; a test that needs one must monkeypatch it (as
    ``test_tab_unload.guard_messages`` does). Direct ``MessageDialog.exec``
    is covered too, so a hand-built box cannot block either.
    """
    import ui.dialogs as dialogs

    patch = pytest.MonkeyPatch()

    def _raise(name):
        def _blocked(*args, **kwargs):
            raise AssertionError(
                f"Unstubbed modal dialog: ui.dialogs.{name}(...). "
                "Stub it in this test.")
        return _blocked

    for name in ("information", "warning", "critical", "question",
                 "get_text", "get_double", "edit_text"):
        patch.setattr(dialogs, name, _raise(name))
    # Every app dialog derives from ``Dialog``; patch the base class so a
    # hand-built MessageDialog, input dialog or editor cannot block either.
    patch.setattr(dialogs.Dialog, "exec", _raise("Dialog.exec"))
    try:
        yield
    finally:
        patch.undo()


@pytest.fixture(autouse=True)
def _revive_a_deleted_kit_tooltip_manager():
    """Recreate the kit's TooltipManager singleton if Qt deleted its C++ side.

    ``ui.theme_kit.popup`` keeps one application-wide QObject. A test that
    tears down the popups (or the tooltipped widgets) it created can take that
    object with it, and the next test in the same process then attaches a new
    widget to a dead wrapper: ``RuntimeError: wrapped C/C++ object of type
    TooltipManager has been deleted``. The app has one manager for its whole
    life, so this is a test-isolation repair, not a behaviour change.
    """
    try:
        from PyQt6 import sip
        from ui.theme_kit import popup
    except ImportError:               # no Qt, or no kit, in this environment
        yield
        return
    manager = popup.TooltipManager._instance
    if manager is not None and sip.isdeleted(manager):
        popup.TooltipManager._instance = None
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolated_app_db():
    """Point core.database at a throwaway DB for the entire session."""
    import core.database as db

    original = db.DB_PATH
    tmpdir = tempfile.mkdtemp(prefix="rhemacast-tests-")
    db.DB_PATH = os.path.join(tmpdir, "app.db")
    db.init_db()
    try:
        yield db.DB_PATH
    finally:
        db.DB_PATH = original
