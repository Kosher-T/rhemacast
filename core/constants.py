"""
core/constants.py

Single source of truth for all magic numbers and central constants across RhemaCast.
"""

# ─── Audio & STT Settings ──────────────────────────────────────────────────────

# Sample rate expected by Faster-Whisper and Vosk
SAMPLE_RATE = 16000

# Number of audio frames per read chunk (1600 frames at 16kHz = 100ms blocks)
BLOCK_SIZE = 1600

# Number of words required to trigger a transcription window evaluation
WORD_WINDOW = 15

# Number of trailing words kept in the buffer to maintain context across windows
WORD_OVERLAP = 6


# ─── Search & Display Thresholds ─────────────────────────────────────────────

# Minimum confidence % required for a result to bypass the queue and display instantly (if intent matches)
TOP_OF_QUEUE_THRESHOLD = 85

# Results below this confidence % are discarded and not shown to the operator
DISCARD_THRESHOLD = 40


# ─── Network / Display Links ─────────────────────────────────────────────────

# How often the LAN-address watcher re-reads the machine's preferred source
# address (milliseconds). It emits only when the address CHANGES, so a stable
# network costs one cheap UDP route lookup per tick and no UI work. Short
# enough that joining a different Wi-Fi mid-service updates the display URL
# before the operator can reach for a phone.
NETWORK_WATCH_INTERVAL_MS = 2000

# WebSocket keepalive for browser display clients. The server pings every
# client on this interval and drops it when no pong arrives within the
# timeout. websockets' defaults (20 s / 20 s) leave a pulled cable invisible
# for up to ~40 s; 2 s / 2 s detects a silent drop within a few seconds while
# adding negligible LAN traffic. The close cap matters as much as the ping:
# websockets waits close_timeout (default 10 s) for a dead peer to acknowledge
# the Close frame, and the client count only drops when the handler returns.
WS_PING_INTERVAL_S = 2.0
WS_PING_TIMEOUT_S = 2.0
WS_CLOSE_TIMEOUT_S = 1.0

# How often the shared connection monitor re-reads the client count. The
# status-bar badge and the Live border update from the same tick.
WS_STATUS_POLL_MS = 1000


# ─── Hardware & Thermal Limits ───────────────────────────────────────────────

# Temperature (°C) at which the GPU will be aggressively throttled to prevent crashing
GPU_CRITICAL_TEMP = 82

# Temperature (°C) at which throttling is lifted and default power limits are restored
GPU_SAFE_TEMP = 70


# ─── Outline / Shadow Ranges ───────────────────────────────────────────────

# Outline thickness bounds (px) shared by the ribbon spin box, the deck
# format parser, and both display renderers. Over-max stored values clamp to
# the max (old decks keep rendering) while the GUI cannot enter more.
OUTLINE_MIN_PX = 1
OUTLINE_MAX_PX = 12

# Shadow size/distance bounds (px). Same contract as outline: GUI caps here,
# stored over-max values clamp. Opacity (0-100%) and angle (0-359deg) are
# unit ranges, not lengths, and stay as they are.
SHADOW_SIZE_MIN_PX = 1
SHADOW_SIZE_MAX_PX = 12
SHADOW_DISTANCE_MIN_PX = 0
SHADOW_DISTANCE_MAX_PX = 12


# ─── Search Index Translation Sets ─────────────────────────────────────────────

# FTS lane: WHICH translations to search, and the hard ceiling on how many.
#
# Every verse of every translation lives in one Porter-stemmed FTS5 table,
# so this list is not an index build — it is the per-query translation
# fan-out (fts_search runs once per entry) and it is the single biggest
# cost lever the operator has. Searching one translation instead of six is
# roughly a 6x saving on every keystroke.
#
# FTS_TRANSLATIONS is only the DEFAULT. The operator picks the set in
# Settings → Database → "FTS5 Index"; the choice is stored in
# `search.fts_translations` and read live via
# core.bible_service.fts_translations().
FTS_TRANSLATIONS = ["KJV", "NKJV", "ESV", "NLT", "AMP", "BSB"]

# Ceiling on the fan-out. Past this the fan-out stops being a search and
# starts being a corpus scan per keystroke.
FTS_MAX_TRANSLATIONS = 6

# Keyword lane (Nave's topics + Strong's lemmas) still scores a BM25
# postings index: final = bm25 * (mix + (1 - mix) * coverage), where
# coverage = fraction of query terms matched. Rewards verses matching MORE
# of the query. The FTS lane does NOT use this — it ranks on FTS5's own
# bm25 plus coverage tier.
KEYWORD_COVERAGE_MIX = 0.5

# Ceiling on the single-word BM25-index pool the keyword lane still reads.
# The FTS lane no longer uses a prefilter — it scores with FTS5's own
# bm25 over the stemmed index.
KEYWORD_POOL_LIMIT = 400

# Partial-match recall for the FTS lane.
#
# When the strict AND comes back thin, one OR sweep over the query's most
# discriminating words fills the candidate pool. Longer stems
# discriminate ("mountain", "church"); two- and three-letter function
# words ("we", "by", "for") match nearly every verse and only make the
# scan bigger, so they seed the pool only when the query has too few
# long words to stand on their own. The cap keeps cost independent of how
# much the operator has typed.
FTS_PARTIAL_MIN_STEM = 4
FTS_PARTIAL_TERMS = 6
FTS_PARTIAL_POOL = 240

# Over-fetch the strict AND before the adjacency tie-break.
#
# bm25's top `limit` is not the final top `limit`: a verse holding the
# query as an exact phrase can sit just below the cutoff and never get the
# tie-break that would promote it ("ten commandments" ranks 11th for a
# six-row request; the literal phrase is at 11, the tent/commandment
# scatter above it). These are full-coverage rows, so the extra pool costs
# one slightly larger fetch, not another scoring pass.
FTS_AND_POOL_EXTRA = 20

# How many query words may contribute a final per-term top-up when even
# the OR pool comes back short (a query made mostly of rare words).
#
# Each probe is a prefix scan over 548k verses, so this stays a last
# resort filler rather than the main partial-match path.
FTS_TOPUP_TERMS = 3

# ─── Verse popularity (operator learning) ───────────────────────────────

# Points per pick action (navigate/single-click lowest, live highest).
POPULARITY_POINTS_NAVIGATE = 1
POPULARITY_POINTS_SCHEDULE = 3
POPULARITY_POINTS_LIVE = 5

# Confidence-space boost per log(1 + points) × similarity unit. Tuned
# against clustered RRF confidences (sub-point gaps): one pick nudges
# ~1 rank without topping; dozens eventually dominate. Scenario-tested.
POPULARITY_WEIGHT = 2.0

# Minimum prompt overlap (intersection over smaller token set) for a
# logged prompt to count toward the current query.
POPULARITY_SIM_THRESHOLD = 0.5

# Cap on stored prompt rows (oldest pruned); bounds per-search cost.
POPULARITY_MAX_PROMPTS = 2000

# ─── Scripture rerank knobs ─────────────────────────────────────────────

# Translations covered by the fuzzy (FAISS + BM25) search lane.
# Modern-language translations — semantic search queries arrive as conversational English.
FUZZY_TRANSLATIONS = ["NLT", "BIBLE_ENGLISH_MSG", "BSB", "AMP", "NIV"]
# NOTE: ERV (ENGLISHERVBIBLE) replaced by topical/stories index in data/indexes/topical_*


# ─── Bible quick-verse typing ─────────────────────────────────────────────

# Gap (ms) allowed between quick-verse keystrokes before the buffer is
# discarded. Configurable in Settings (bible.quick_verse_timeout_ms).
QUICK_VERSE_TIMEOUT_MS_DEFAULT = 500
QUICK_VERSE_TIMEOUT_MS_MIN = 50
QUICK_VERSE_TIMEOUT_MS_MAX = 2000

# ─── Search-box history ────────────────────────────────────────────────────

# Typing that stops this long qualifies a search query for the session-only
# Up/Down history (FTS / Fuzzy / deck search). 2s: long enough that
# mid-word pauses don't each qualify, short enough that a finished query
# lands before the operator wanders off.
SEARCH_HISTORY_IDLE_MS = 2000

# Session-sized cap per search box (entries, newest first).
SEARCH_HISTORY_MAX_ENTRIES = 50


# ─── Search auto-run delay ────────────────────────────────────────────────

# How long the Keyword lane waits after the last keystroke before it
# searches (search.auto_delay_ms). 0 = every keystroke. Read live on each
# keystroke, so a change in Settings applies without a restart.
SEARCH_AUTO_DELAY_MS_DEFAULT = 100

# Selectable slots (ms) offered in Settings, 80 ms up to 700 ms. 0 is the
# "every keystroke" option and is prepended by the UI, not stored here.
SEARCH_AUTO_DELAY_MS_SLOTS = (80, 100, 150, 200, 250, 300, 400, 500, 600, 700)


# ─── Queue Depths & Backpressure ─────────────────────────────────────────────

# Max pending 100ms PCM audio chunks (500 chunks = 50 seconds of audio buffer)
QUEUE_A_MAXSIZE = 500

# Max pending 15-word STT transcript blocks awaiting search scoring
QUEUE_B_MAXSIZE = 200

# Max pending telemetry/logging events awaiting disk/SQLite write
DB_QUEUE_MAXSIZE = 1000

# Max pending verse suggestions waiting for human operator review
OPERATOR_QUEUE_MAXSIZE = 100
