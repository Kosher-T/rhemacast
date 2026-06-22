"""
core/intent_classifier.py
Phase 6 - Intent Classification
Compiles intent triggers into Token-Window Regex patterns and evaluates STT chunks.
"""
import os
import re
import json
import logging

logger = logging.getLogger(__name__)

class IntentClassifier:
    def __init__(self):
        self.trigger_patterns = []
        self.ignore_patterns = []
        self._load_and_compile()

    def _compile_phrase(self, phrase: str) -> re.Pattern:
        """
        Compiles a phrase into a Token-Window Regex.
        Allows up to 2 intervening words between target words.
        """
        words = phrase.strip().split()
        if not words:
            return None
        
        escaped_words = [r'\b' + re.escape(w) + r'\b' for w in words]
        pattern_str = r'(?:\s+\w+){0,2}\s+'.join(escaped_words)
        return re.compile(pattern_str, re.IGNORECASE)

    def _load_and_compile(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(root_dir, "data", "intent_triggers.json")
        
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load intent_triggers.json: {e}")
            config = {"trigger_intent": [], "ignore_intent": []}
            
        for phrase in config.get("ignore_intent", []):
            pat = self._compile_phrase(phrase)
            if pat: self.ignore_patterns.append((pat, phrase))
            
        for phrase in config.get("trigger_intent", []):
            pat = self._compile_phrase(phrase)
            if pat: self.trigger_patterns.append((pat, phrase))
            
        logger.info(f"Compiled {len(self.trigger_patterns)} trigger intents and {len(self.ignore_patterns)} ignore intents.")

    def evaluate_intent(self, text_chunk: str) -> tuple[bool, bool, str]:
        """
        Returns (is_triggered: bool, is_ignored: bool, matched_phrase: str).
        Evaluates negative overrides first.
        """
        # Step 1: Negative override
        for pat, phrase in self.ignore_patterns:
            if pat.search(text_chunk):
                return False, True, phrase
                
        # Step 2: Positive evaluation
        for pat, phrase in self.trigger_patterns:
            if pat.search(text_chunk):
                return True, False, phrase
                
        return False, False, None

# Singleton
intent_classifier = IntentClassifier()
