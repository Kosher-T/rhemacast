# RhemaCast — Optimization Audit & Prioritized Roadmap

> **How to read this document:**
> Issues are grouped by system area, each marked with a severity badge and a priority rank.
> Severity: 🔴 Critical (causes freezes/data loss) | 🟠 High (causes lag/resource waste) | 🟡 Medium (causes jank or correctness risk) | 🟢 Low (quality-of-life)

---

## Summary

The codebase is architecturally sound at a high level — the queue/thread model is correct, the `ServiceManager` state machine is a good foundation, and the `VerseListModel` virtual model was the right call. The problems are not in the design; they're in the **integration seams**. Each feature was bolted on without reconciling it with the surrounding system, creating:

1. A WebSocket bridge that spawns a **new thread + event loop per broadcast** (the single most impactful bug)
2. A DB writer that ignores 95% of what is sent to it (dict payloads that are expected to be dataclasses)
3. Live search that runs **two full-corpus database queries on every keystroke** on the main UI thread
4. A hardware monitor that creates **two independent NVML instances** when only one exists
5. A search engine with a hard-coded `best["verse"]` key that doesn't exist (silent bug)

**Recommended order of attack:** Fix the critical bugs first, then the resource leaks, then the correctness issues.

---

## Area 1 — WebSocket Broadcasting

### 🔴 C-1 — New thread + new event loop spawned per broadcast
**File:** `ui/tabs/presentation_tab.py` → `_broadcast_to_ws()` (lines 685–707)

```python
def _fire():
    loop = asyncio.new_event_loop()         # new loop every call
    asyncio.set_event_loop(loop)
    loop.run_until_complete(broadcast_display(payload))
    loop.close()

t = threading.Thread(target=_fire, daemon=True)  # new thread every call
t.start()
```

**Problem:** Every operator action (single-click, double-click, prev, next, schedule, search, theme change — all of them) spawns a brand-new OS thread and creates a new asyncio event loop. The WebSocket server already runs its own asyncio loop in a background thread. There is no reason for this pattern at all. Under normal use you're generating dozens of idle threads.

**Fix:** Call `asyncio.run_coroutine_threadsafe(broadcast_display(payload), ws_loop)` where `ws_loop` is the loop captured from the WS server thread at startup. One thread, one loop, forever.

---

### 🟡 C-2 — XSS sanitizer breaks theme data
**File:** `core/websocket_server.py` → `sanitize_payload()` (lines 34–46)

`sanitize_payload()` only processes top-level string keys. The `theme_data` value is a nested dict of CSS variables. Any string inside `theme_data` that contains `<` or `>` would break if the function ever iterated recursively. The function should be scoped to only the broadcast-unsafe fields (`text`, `ref`).

---

## Area 2 — DB Writer

### 🔴 C-3 — DB Writer silently drops ~100% of actual write traffic
**File:** `core/db_writer.py` → `db_writer_thread()` (lines 85–88)

```python
if not isinstance(item, BaseEvent):
    logger.warning("DB Writer received unknown item type. Ignoring.")
    continue
```

**Problem:** Everything pushed to `db_write_queue` from `stt_inference.py` and `search_engine.py` is a plain `dict` (e.g. `{"type": "raw_stt", "payload": {...}}`). The DB writer checks `isinstance(item, BaseEvent)` — which every dict fails — and discards it. The SQLite `transcripts`, `search_results`, and `display_events` tables are almost certainly empty.

**Fix:** The DB writer needs to handle dict-based payloads with a `type` key, or the senders need to be updated to send proper `dataclass` events. The latter matches the existing `events.py` structure.

---

### 🟡 C-4 — DB Writer commits on every single row
**File:** `core/db_writer.py`, line 117

```python
conn.commit()  # called inside the while loop, after every item
```

SQLite's `commit()` is an I/O-bound fsync. Calling it after every row under load (every 100ms audio chunk) means ~10 commits/second. **Fix:** Batch commits every N items or every 500ms via a `time.time()` checkpoint.

---

## Area 3 — Search Engine

### 🔴 C-5 — Live search runs on the main UI thread, blocking the entire interface
**File:** `ui/panels/browser_panel.py` → `_on_search_text_changed()` (lines 767–782)

```python
def _on_search_text_changed(self, text: str):
    results = hybrid_search(query, ...)   # runs on main thread
    self._model.load_all(results)
```

`hybrid_search()` calls `search_verses_text()` (FTS5) and `bm25_search()` (full BM25 corpus scan with numpy argsort) in parallel via `ThreadPoolExecutor` — but the calling thread is blocked waiting on `.result()`. This freezes the Qt event loop on every keystroke.

**Fix:** Move the search call to a `QThread` or `QRunnable` + `QThreadPool`. Only update the model from the main thread via a signal.

---

### 🔴 C-6 — `best["verse"]` key doesn't exist in search results
**File:** `core/search_engine.py`, line 223

```python
ref = f"[{get_display_name(best['version'])}] {best['book']} {best['chapter']}:{best['verse']}"
```

`rrf_fuse()` returns dicts with key `"verse_num"`, not `"verse"`. This is a silent `KeyError` swallowed by the `except Exception` at line 252. Every high-confidence search result crashes internally — results never reach the operator queue.

**Fix:** Change `best['verse']` → `best['verse_num']` on line 223. One character fix.

---

### 🟠 C-7 — `check_lru_cache()` mutates state as a side effect of a read
**File:** `core/search_engine.py`, lines 35–48

The function writes `LRU_CACHE[verse_ref] = now` before returning `False` on a cache miss. This means the first time a verse passes the confidence threshold, it is registered in the cache and will be suppressed for the next 15 seconds on subsequent calls. The naming is misleading and the intent is undocumented. Rename to `mark_and_check_lru()` and document that it both reads and writes.

---

## Area 4 — Hardware Monitor

### 🟠 C-8 — Two independent NVML/psutil instances created for the same hardware
**File:** `core/hardware_monitor.py`, lines 142–143 and 180–184

```python
def _hardware_thread_target():
    monitor = HardwareMonitor()   # Instance #1: background thread (T5)

def get_hardware_info() -> dict:
    global _singleton_monitor
    if _singleton_monitor is None:
        _singleton_monitor = HardwareMonitor()  # Instance #2: UI polling
```

Thread 5 creates its own `HardwareMonitor`. The settings tab sidebar creates a separate one. Both call `pynvml.nvmlInit()` independently. The thermal throttling logic exists only in the T5 instance while the UI reads from the singleton — they are out of sync. **Fix:** Share one `HardwareMonitor` instance between T5 and the UI read path.

---

### 🟠 C-9 — Status bar never receives hardware data
**File:** `ui/widgets/status_bar.py`

`StatusBar.update_hardware()` exists but nothing ever calls it. The GPU/VRAM/RAM labels remain at `--` forever. The hardware monitor pushes data to `db_write_queue` (which discards it per C-3), not to the UI.

**Fix:** Add a 2s `QTimer` in `StatusBar` that calls `get_hardware_info()` from `hardware_monitor.py` and then calls `self.update_hardware(info)`.

---

## Area 5 — Audio + STT Pipeline

### 🟠 C-10 — `_paused_buffer` is a module-level list with no thread safety
**File:** `core/audio_capture.py`, line 25

```python
_paused_buffer = []
```

`_audio_callback()` runs in a PortAudio callback thread (not Thread 1). It reads and writes `_paused_buffer` without any lock, creating a data race if `capture_paused` is set/cleared mid-callback. **Fix:** Use a `threading.Lock()` around all accesses to `_paused_buffer`.

---

### 🔴 C-11 — PCM data stored as `bytes` but treated as `np.ndarray` downstream
**File:** `core/audio_capture.py` line 110 vs `core/stt_inference.py` line 54

Audio callback stores:
```python
pcm_data = indata.copy().tobytes()  # bytes object
audio_buffer.enqueue(chunk_id, pcm_data)
```

STT inference then does:
```python
audio_array = np.concatenate(pcm_accumulator).flatten()  # expects ndarray
```

`np.concatenate()` on a list of `bytes` objects produces garbage or errors. Whisper is likely receiving corrupted audio. **Fix:** Store `indata.copy()` (ndarray) in the buffer, not `.tobytes()`.

---

### 🟡 C-12 — STT `wait_state` logic is dead code
**File:** `core/stt_inference.py`, lines 67–72

```python
if wait_state:
    prior = list(trigger_buffer)[-15:]
    wait_state = False
```

`prior` is computed but never used. This is an incomplete "context window" feature that was abandoned mid-patch. Either finish it or remove the dead code.

---

## Area 6 — Bible Service & Browser

### 🟠 C-13 — New SQLite connection opened and closed per query
**File:** `core/bible_service.py` → `_get_connection()` (lines 38–42)

Every call to `get_chapter()`, `get_verse()`, `get_books()`, `get_next_verse()`, etc. opens a fresh `sqlite3.connect()` and closes it. These are called on every click, every prev/next, every schedule load. **Fix:** Use a thread-local persistent read-only connection (the URI `mode=ro` already prevents write conflicts).

---

### 🟡 C-14 — No debounce on live search — full reload triggered on every keystroke including backspace
**File:** `ui/panels/browser_panel.py`, lines 769–771

```python
if not query:
    self._load_bible()  # triggers beginResetModel/endResetModel on 31k items
    return
```

Pressing backspace to clear the search field triggers a full view repaint of 31k items on every call. A 150ms `QTimer` debounce would coalesce rapid keystrokes into a single search.

---

## Area 7 — Architectural

### 🟡 C-15 — `preload_search()` re-loads already-loaded indexes
**File:** `core/model_manager.py`, lines 146–157

`preload_search()` calls `_load_indexes()` and `_load_embedding()` in a background thread. But `load_all_models()` (called at startup) already calls both. If `preload_search()` is called after `load_all_models()`, it double-loads everything. Add a guard: `if self.bm25_index is not None: return`.

---

### 🔴 C-16 — No asyncio event loop reference stored from WS server thread (root cause of C-1)
**File:** `core/websocket_server.py` + `ui/tabs/presentation_tab.py`

The WS server thread starts `asyncio.run(start_servers())` but never exposes its event loop. The correct fix: store the loop at module level so other threads can dispatch to it without creating new ones:

```python
# websocket_server.py
_server_loop: asyncio.AbstractEventLoop | None = None

def run_server_thread():
    global _server_loop
    _server_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_server_loop)
    _server_loop.run_until_complete(start_servers())
```

Then in `presentation_tab.py`:
```python
from core.websocket_server import _server_loop, broadcast_display
asyncio.run_coroutine_threadsafe(broadcast_display(payload), _server_loop)
```

No new threads. No new event loops. Sub-millisecond dispatch.

---

## Priority Ranking

| # | Issue | Severity | Effort | Impact |
|---|-------|----------|--------|--------|
| 1 | C-6 — `best['verse']` KeyError kills search pipeline | 🔴 | Trivial | STT suggestions never reach operator |
| 2 | C-11 — PCM stored as bytes, treated as ndarray | 🔴 | Low | STT is transcribing corrupted audio |
| 3 | C-1 + C-16 — Broadcast spawns new thread/loop per call | 🔴 | Low | Stops resource leak immediately |
| 4 | C-3 — DB Writer discards all real write traffic | 🔴 | Medium | All session observability data is lost |
| 5 | C-5 — Live search blocks UI thread | 🔴 | Medium | Interface freezes on every keystroke |
| 6 | C-4 — DB commit on every row | 🟠 | Trivial | 10x reduction in SQLite I/O |
| 7 | C-9 — Status bar hardware labels never update | 🟠 | Low | Fix broken telemetry display |
| 8 | C-8 — Dual NVML instances | 🟠 | Low | Halves hardware monitor overhead |
| 9 | C-10 — `_paused_buffer` data race | 🟠 | Low | Prevent rare audio corruption |
| 10 | C-13 — New SQLite conn per query | 🟠 | Medium | Reduces I/O overhead on navigation |
| 11 | C-14 — No debounce on live search | 🟡 | Low | Smoother typing experience |
| 12 | C-7 — LRU cache mutates on read | 🟡 | Low | Clarify intent, prevent misuse |
| 13 | C-12 — `wait_state` dead code | 🟡 | Low | Remove or complete |
| 14 | C-2 — Sanitizer doesn't recurse into theme_data | 🟡 | Low | Correctness/security hardening |
| 15 | C-15 — `preload_search()` double-loads models | 🟡 | Low | Save startup memory |

---

## Recommended Three-Pass Approach

**Pass 1 — Zero-risk, zero-effort (1–2 hours)**
- C-6: Change one word (`verse` → `verse_num`) in `search_engine.py:223`
- C-4: Batch SQLite commits with a 500ms timer
- C-9: Add a 2s QTimer in `StatusBar` calling `get_hardware_info()`

These three changes fix a broken search pipeline, eliminate I/O waste, and restore a broken UI widget — with essentially zero regression risk.

**Pass 2 — Core pipeline fixes (half day)**
- C-11 + C-1 + C-16: Fix PCM storage format, expose WS event loop, collapse broadcast to a single line
- C-3: Align the DB writer to handle dict payloads

These touch thread boundaries but are well-contained and the fixes are mechanical.

**Pass 3 — UI responsiveness (half day)**
- C-5: Offload `hybrid_search` to a `QRunnable` worker with a debounce
- C-8 + C-10: Unify hardware monitor instances, add `_paused_buffer` lock
- C-13: Persistent thread-local SQLite connection in `bible_service`
