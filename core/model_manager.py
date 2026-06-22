import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

class ModelManager:
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.whisper_model = None
        self.vosk_model = None
        self.embedding_model = None
        
        self.stt_mode = "unknown"
        self.embedding_mode = "unknown"
        
    def load_all_models(self):
        """Loads all required models. Logs appropriately."""
        logger.info("Initializing ModelManager...")
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
            logger.critical("Running in CPU-only mode (Vosk).")
            print("\n*** ERROR: CUDA Toolkit not found. Running in CPU-only mode (Vosk) ***\n")
            self.stt_mode = "vosk_primary"
            self.whisper_model = None
            
            if self.vosk_model is None:
                logger.critical("FATAL: Neither Faster-Whisper nor Vosk models are available!")

    def _load_embedding(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading primary embedding model (all-MiniLM-L6-v2)...")
            self.embedding_model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                backend="onnx",
                model_kwargs={"provider": "CPUExecutionProvider"}
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
                    model_kwargs={"provider": "CPUExecutionProvider"}
                )
                self.embedding_mode = "backup"
                logger.info("Backup embedding model loaded.")
            except Exception as e2:
                logger.critical(f"Backup embedding model also failed: {e2}")

# Global singleton
model_manager = ModelManager()
