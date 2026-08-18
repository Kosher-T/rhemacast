import os
import logging
import numpy as np

os.environ["HF_HUB_OFFLINE"] = "1"  # All models are local — no network calls

logger = logging.getLogger(__name__)

class ModelManager:
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.whisper_model = None
        self.vosk_model = None
        self.embedding_model = None
        self.bm25_index = None
        self.verse_lookup = None
        self.fuzzy_bm25_index = None  # Fuzzy lane BM25 (same translations as FAISS)
        self.fuzzy_verse_lookup = None
        self.faiss_index = None
        self.faiss_verse_lookup = None  # Separate lookup for FAISS (6 translations only)
        # Topical/stories search indexes
        self.topical_faiss_index = None  # FAISS index for semantic search on topics
        self.topical_bm25_index = None   # BM25 index for keyword search on topics
        self.topical_lookup = None       # Index → topic + verses mapping
        
        self.stt_mode = "unknown"
        self.embedding_mode = "unknown"
        
    def load_all_models(self):
        """Loads all required models. Logs appropriately."""
        logger.info("Initializing ModelManager...")
        self._load_indexes()
        self._load_vosk()
        self._load_whisper()
        self._load_embedding()
        logger.info("ModelManager initialization complete.")

    def _load_vosk(self):
        try:
            from vosk import Model
            vosk_path = os.path.join(self.root_dir, "models", "vosk-model-small-en-us")
            if not os.path.exists(vosk_path):
                logger.warning(f"Vosk model not found at {vosk_path}. Failover will be unavailable.")
                return
            
            # Cap OpenBLAS/MKL threads before Vosk activation
            os.environ["OMP_NUM_THREADS"] = "2"
            os.environ["OPENBLAS_NUM_THREADS"] = "2"
            
            logger.info("Loading Vosk failover model (warm standby)...")
            self.vosk_model = Model(vosk_path)
            logger.info("Vosk model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")

    def _load_whisper(self):
        try:
            import ctranslate2
            from faster_whisper import WhisperModel
            
            if not ctranslate2.get_cuda_device_count() > 0:
                raise RuntimeError("No CUDA devices found via ctranslate2.")
                
            logger.info("Loading Faster-Whisper model (tiny.en, cuda, int8)...")
            self.whisper_model = WhisperModel("tiny.en", device="cuda", compute_type="int8")
            
            logger.info("Running dummy inference for CUDA verification...")
            dummy_audio = np.zeros(16000, dtype=np.float32)
            segments, _ = self.whisper_model.transcribe(dummy_audio)
            list(segments) # Force evaluation
            
            self.stt_mode = "whisper_primary"
            logger.info("Faster-Whisper CUDA verification passed. Running in GPU mode.")
            
        except Exception as e:
            logger.critical(f"CUDA Toolkit not found or Whisper load failed: {e}")
            logger.critical(
                "GPU detected but CUDA Toolkit not installed. "
                "Install CUDA Toolkit 12.x from https://developer.nvidia.com/cuda-downloads "
                "then restart. Falling back to CPU-only mode (Vosk)."
            )
            print("\n*** CUDA Toolkit not found — install CUDA 12.x for GPU transcription. ***")
            print("*** Falling back to CPU-only mode (Vosk). ***\n")
            self.stt_mode = "vosk_primary"
            self.whisper_model = None
            
            if self.vosk_model is None:
                logger.critical("FATAL: Neither Faster-Whisper nor Vosk models are available!")

    def _load_embedding(self):
        model_path = os.path.join(self.root_dir, "models", "all-MiniLM-L6-v2")
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading primary embedding model from {model_path}...")
            self.embedding_model = SentenceTransformer(
                model_path,
                backend="onnx",
                model_kwargs={"provider": "CPUExecutionProvider", "file_name": "onnx/model.onnx"}
            )
            self.embedding_mode = "primary"
            logger.info("Primary embedding model loaded.")
        except Exception as e:
            logger.warning(f"Primary embedding model failed: {e}")
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading backup embedding model (paraphrase-MiniLM-L3-v2)...")
                self.embedding_model = SentenceTransformer(
                    "paraphrase-MiniLM-L3-v2",
                    backend="onnx",
                    model_kwargs={"provider": "CPUExecutionProvider", "file_name": "onnx/model.onnx"}
                )
                self.embedding_mode = "backup"
                logger.info("Backup embedding model loaded.")
            except Exception as e2:
                from core.errors import StartupCheckError
                logger.critical(f"Backup embedding model also failed: {e2}")
                raise StartupCheckError(f"Embedding models failed to load: {e2}")

    def _load_indexes(self):
        import pickle
        import logging
        from core.errors import StartupCheckError
        # Suppress noisy faiss AVX2 fallback messages
        logging.getLogger("faiss.loader").setLevel(logging.WARNING)
        try:
            import faiss
        except ImportError:
            faiss = None
            
        data_dir = os.path.join(self.root_dir, "data", "indexes")
        bm25_path = os.path.join(data_dir, "bm25.pkl")
        lookup_path = os.path.join(data_dir, "verse_lookup.pkl")
        fuzzy_bm25_path = os.path.join(data_dir, "fuzzy_bm25.pkl")
        fuzzy_lookup_path = os.path.join(data_dir, "fuzzy_verse_lookup.pkl")
        faiss_path = os.path.join(data_dir, "faiss.index")
        faiss_lookup_path = os.path.join(data_dir, "faiss_verse_lookup.pkl")

        # Load BM25
        try:
            logger.info(f"Loading BM25 index from {bm25_path}...")
            with open(bm25_path, "rb") as f:
                self.bm25_index = pickle.load(f)
            with open(lookup_path, "rb") as f:
                self.verse_lookup = pickle.load(f)
            logger.info("BM25 index loaded successfully.")
        except FileNotFoundError:
            logger.critical("BM25 index not found at data/indexes/bm25.pkl — run Phase 1 offline build first")
            raise StartupCheckError("BM25 index missing")
        except Exception as e:
            logger.critical(f"Failed to load BM25 index: {e}")
            raise StartupCheckError(f"BM25 index corrupted: {e}")

        # Load fuzzy-lane BM25 (optional — FAISS-only degradation if missing)
        try:
            if os.path.exists(fuzzy_bm25_path) and os.path.exists(fuzzy_lookup_path):
                with open(fuzzy_bm25_path, "rb") as f:
                    self.fuzzy_bm25_index = pickle.load(f)
                with open(fuzzy_lookup_path, "rb") as f:
                    self.fuzzy_verse_lookup = pickle.load(f)
                logger.info(f"Fuzzy BM25 index loaded ({len(self.fuzzy_verse_lookup):,} entries).")
            else:
                self.fuzzy_bm25_index = None
                self.fuzzy_verse_lookup = None
                logger.warning(
                    "Fuzzy BM25 index not found at data/indexes/fuzzy_bm25.pkl — "
                    "fuzzy search will degrade to FAISS-only. Rebuild with "
                    "'python data/bible/build_bm25.py --fuzzy'."
                )
        except Exception as e:
            self.fuzzy_bm25_index = None
            self.fuzzy_verse_lookup = None
            logger.warning(f"Failed to load fuzzy BM25 index: {e}")

        # Load FAISS
        try:
            logger.info(f"Loading FAISS index from {faiss_path}...")
            if not faiss:
                raise ImportError("faiss module is not installed.")
            self.faiss_index = faiss.read_index(faiss_path)

            # Load FAISS-specific verse lookup (required — FAISS translations
            # differ from the FTS BM25 set, so the FTS lookup cannot map them)
            if os.path.exists(faiss_lookup_path):
                with open(faiss_lookup_path, "rb") as f:
                    self.faiss_verse_lookup = pickle.load(f)
                logger.info(f"FAISS verse lookup loaded ({len(self.faiss_verse_lookup):,} entries).")
                logger.info("FAISS index loaded successfully.")
            else:
                self.faiss_index = None
                self.faiss_verse_lookup = None
                logger.critical(
                    "FAISS verse lookup not found at data/indexes/faiss_verse_lookup.pkl — "
                    "FAISS search disabled. Rebuild indexes with 'python data/bible/build_faiss.py'."
                )
        except FileNotFoundError:
            logger.critical("FAISS index not found at data/indexes/faiss.index — run Phase 1 offline build first")
            raise StartupCheckError("FAISS index missing")
        except Exception as e:
            logger.critical(f"Failed to load FAISS index: {e}")
            raise StartupCheckError(f"FAISS index corrupted: {e}")

        # Load topical/stories search indexes (optional — search degrades gracefully if missing)
        topical_faiss_path = os.path.join(data_dir, "topical_faiss.index")
        topical_bm25_path = os.path.join(data_dir, "topical_bm25.pkl")
        topical_lookup_path = os.path.join(data_dir, "topical_lookup.pkl")

        try:
            if (os.path.exists(topical_faiss_path) and 
                os.path.exists(topical_bm25_path) and 
                os.path.exists(topical_lookup_path)):
                logger.info(f"Loading topical search indexes...")
                self.topical_faiss_index = faiss.read_index(topical_faiss_path)
                with open(topical_bm25_path, "rb") as f:
                    self.topical_bm25_index = pickle.load(f)
                with open(topical_lookup_path, "rb") as f:
                    self.topical_lookup = pickle.load(f)
                logger.info(f"Topical indexes loaded ({len(self.topical_lookup):,} topics).")
            else:
                logger.warning(
                    "Topical search indexes not found — topic/story search disabled. "
                    "Rebuild with 'python data/bible/build_topical.py'."
                )
        except Exception as e:
            logger.warning(f"Failed to load topical indexes: {e}")

    def preload_search(self):
        """Preload search indexes + embedding model in a background thread."""
        import threading
        def _worker():
            try:
                self._load_indexes()
                self._load_embedding()
                logger.info("Search preload complete.")
            except Exception as e:
                logger.error(f"Search preload failed: {e}")
        thread = threading.Thread(target=_worker, name="SearchPreload", daemon=True)
        thread.start()

    def preload_stt(self):
        """Load STT models (Vosk + Whisper) in parallel background threads."""
        import threading
        self._stt_ready = threading.Event()
        self._stt_errors = []

        def _load_vosk_thread():
            try:
                self._load_vosk()
            except Exception as e:
                self._stt_errors.append(f"Vosk: {e}")

        def _load_whisper_thread():
            try:
                self._load_whisper()
            except Exception as e:
                self._stt_errors.append(f"Whisper: {e}")

        t_vosk = threading.Thread(target=_load_vosk_thread, name="STT-Preload-Vosk", daemon=True)
        t_whisper = threading.Thread(target=_load_whisper_thread, name="STT-Preload-Whisper", daemon=True)

        t_vosk.start()
        t_whisper.start()

        def _watch():
            t_vosk.join()
            t_whisper.join()
            logger.info(f"STT preload complete: mode={self.stt_mode}")
            self._stt_ready.set()

        threading.Thread(target=_watch, name="STT-Preload-Watch", daemon=True).start()

    def wait_for_stt(self, timeout=None):
        """Block until STT preload finishes. Returns True if ready, False if timed out."""
        if not hasattr(self, '_stt_ready'):
            return True  # No preload in progress
        return self._stt_ready.wait(timeout=timeout)

# Global singleton
model_manager = ModelManager()
