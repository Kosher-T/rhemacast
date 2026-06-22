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


# ─── Hardware & Thermal Limits ───────────────────────────────────────────────

# Temperature (°C) at which the GPU will be aggressively throttled to prevent crashing
GPU_CRITICAL_TEMP = 82

# Temperature (°C) at which throttling is lifted and default power limits are restored
GPU_SAFE_TEMP = 70


# ─── Queue Depths & Backpressure ─────────────────────────────────────────────

# Max pending 100ms PCM audio chunks (500 chunks = 50 seconds of audio buffer)
QUEUE_A_MAXSIZE = 500

# Max pending 15-word STT transcript blocks awaiting search scoring
QUEUE_B_MAXSIZE = 200

# Max pending telemetry/logging events awaiting disk/SQLite write
DB_QUEUE_MAXSIZE = 1000

# Max pending verse suggestions waiting for human operator review
OPERATOR_QUEUE_MAXSIZE = 100
