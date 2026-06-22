"""
core/config_schema.py

Defines the structure, default values, and migration logic for config.json.
Validates the configuration on startup.
"""

import json
import os
import shutil
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# The current expected schema version
CURRENT_CONFIG_VERSION = 1

DEFAULT_CONFIG = {
    "config_version": CURRENT_CONFIG_VERSION,
    "operational_mode": "NORMAL",  # NORMAL, SAFE_MODE, CPU_ONLY, REHEARSAL, HEADLESS, DEBUG, BENCHMARK
    "models": {
        "stt_primary": "tiny.en",
        "stt_fallback": "vosk-model-small-en-us",
        "embedding_primary": "all-MiniLM-L6-v2",
        "embedding_fallback": "paraphrase-MiniLM-L3-v2"
    },
    "thresholds": {
        "top_of_queue_confidence": 85,
        "discard_confidence": 40
    },
    "queues": {
        "queue_a_maxsize": 500,
        "queue_b_maxsize": 200,
        "db_queue_maxsize": 1000,
        "operator_queue_maxsize": 100
    },
    "poll_intervals_ms": {
        "gpu_temp_poll": 2000,
        "system_ram_poll": 30000
    },
    "hotkeys": {
        "display": "F1",
        "clear_recall": "F2",
        "theme_forward": "F3",
        "theme_back": "F4",
        "theme_reset": "F5"
    },
    "theme": {
        "default": "standard"
    }
}

class ConfigValidationError(Exception):
    """Raised when the configuration is invalid or missing required fields."""
    pass

def migrate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate an older config dictionary to the current schema version."""
    version = config.get("config_version", 0)
    
    if version == CURRENT_CONFIG_VERSION:
        return config
    
    # If the version is newer than this code understands, that's a problem
    if version > CURRENT_CONFIG_VERSION:
        raise ConfigValidationError(f"Config version {version} is newer than supported version {CURRENT_CONFIG_VERSION}.")
    
    # Fallback: if we can't migrate smoothly, just fill missing keys from default
    migrated = DEFAULT_CONFIG.copy()
    
    # Deep merge would be better, but for v1 this shallow update is okay to start.
    # In future migrations (e.g. v1 -> v2), implement explicit transforms here.
    for key, value in config.items():
        if key in migrated and isinstance(migrated[key], dict) and isinstance(value, dict):
            migrated[key].update(value)
        else:
            migrated[key] = value
            
    migrated["config_version"] = CURRENT_CONFIG_VERSION
    return migrated

def validate_config(config: Dict[str, Any]) -> None:
    """Validate that the configuration has all required fields with correct types."""
    required_keys = ["config_version", "operational_mode", "models", "thresholds", "queues", "hotkeys"]
    for key in required_keys:
        if key not in config:
            raise ConfigValidationError(f"Missing required key: '{key}'")
            
    if not isinstance(config["thresholds"], dict):
        raise ConfigValidationError("'thresholds' must be an object")
        
    if "top_of_queue_confidence" not in config["thresholds"]:
        raise ConfigValidationError("Missing 'thresholds.top_of_queue_confidence'")
        
    if not isinstance(config["thresholds"]["top_of_queue_confidence"], (int, float)):
        raise ConfigValidationError("'thresholds.top_of_queue_confidence' must be a number")
        
    if "discard_confidence" not in config["thresholds"]:
        raise ConfigValidationError("Missing 'thresholds.discard_confidence'")

def load_and_validate_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    Load the config.json file, migrate if necessary, validate, and return it.
    If the file doesn't exist, it creates it with default values.
    """
    if not os.path.exists(config_path):
        logger.info(f"Config file not found at {config_path}. Creating default config.")
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
        
    with open(config_path, "r") as f:
        try:
            raw_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Failed to parse {config_path}: {e}")
            
    # Check if migration is needed
    migrated_config = migrate_config(raw_config)
    
    # If we migrated, save the new config
    if migrated_config.get("config_version") != raw_config.get("config_version"):
        backup_path = f"{config_path}.bak"
        logger.info(f"Migrating config from version {raw_config.get('config_version', 0)} to {CURRENT_CONFIG_VERSION}.")
        shutil.copy(config_path, backup_path)
        with open(config_path, "w") as f:
            json.dump(migrated_config, f, indent=4)
            
    # Final validation - raises ConfigValidationError on failure
    validate_config(migrated_config)
    
    return migrated_config
