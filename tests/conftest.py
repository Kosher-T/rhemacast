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
