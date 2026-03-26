# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multi-language Translation Agent for A2A communication."""

import json
from typing import List, Optional

from google.adk import Agent
from google.genai import types


# Supported languages mapping
SUPPORTED_LANGUAGES = {
    "ja": "Japanese",
    "en": "English",
    "zh": "Chinese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
}


async def translate_text(
    text: str,
    target_language: str,
    source_language: Optional[str] = None,
) -> str:
    """Translate text to the specified target language.

    Args:
        text: The text to translate.
        target_language: Target language code (e.g., 'en', 'ja', 'zh').
        source_language: Source language code. If not provided, will be auto-detected.

    Returns:
        JSON string with translation result.
    """
    # Validate target language
    if target_language not in SUPPORTED_LANGUAGES:
        return json.dumps({
            "status": "error",
            "error": f"Unsupported target language: {target_language}",
            "supported_languages": SUPPORTED_LANGUAGES,
        }, ensure_ascii=False, indent=2)

    # Mock translation (in production, would call actual translation API)
    # For demo, we'll use simple patterns
    result = {
        "status": "success",
        "original_text": text,
        "translated_text": f"[{SUPPORTED_LANGUAGES[target_language]} translation of: {text}]",
        "source_language": source_language or "auto-detected",
        "target_language": target_language,
        "target_language_name": SUPPORTED_LANGUAGES[target_language],
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


async def detect_language(text: str) -> str:
    """Detect the language of the input text.

    Args:
        text: The text to analyze.

    Returns:
        JSON string with detected language and confidence score.
    """
    # Mock language detection based on simple heuristics
    detected = "en"  # Default
    confidence = 0.85

    # Simple pattern matching for demo
    if any(ord(c) > 0x3000 and ord(c) < 0x9FFF for c in text):
        if any(ord(c) >= 0x3040 and ord(c) <= 0x309F for c in text):
            detected = "ja"
            confidence = 0.95
        elif any(ord(c) >= 0xAC00 and ord(c) <= 0xD7AF for c in text):
            detected = "ko"
            confidence = 0.92
        else:
            detected = "zh"
            confidence = 0.90

    result = {
        "status": "success",
        "text": text[:100] + "..." if len(text) > 100 else text,
        "detected_language": detected,
        "detected_language_name": SUPPORTED_LANGUAGES.get(detected, "Unknown"),
        "confidence": confidence,
        "all_probabilities": {
            detected: confidence,
            "en" if detected != "en" else "ja": 1 - confidence,
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


async def batch_translate(
    texts: List[str],
    target_languages: List[str],
) -> str:
    """Translate multiple texts to multiple target languages.

    Args:
        texts: List of texts to translate.
        target_languages: List of target language codes.

    Returns:
        JSON string with all translation results.
    """
    results = []

    for text in texts:
        text_translations = {
            "original": text,
            "translations": {},
        }
        for lang in target_languages:
            if lang in SUPPORTED_LANGUAGES:
                text_translations["translations"][lang] = {
                    "language_name": SUPPORTED_LANGUAGES[lang],
                    "translated_text": f"[{SUPPORTED_LANGUAGES[lang]}: {text}]",
                }
        results.append(text_translations)

    response = {
        "status": "success",
        "total_texts": len(texts),
        "target_languages": target_languages,
        "results": results,
    }

    return json.dumps(response, ensure_ascii=False, indent=2)


root_agent = Agent(
    model='gemini-2.5-flash',
    name='translation_agent',
    description=(
        'Multi-language translation agent that can translate text between various languages. '
        'Supports Japanese, English, Chinese, Korean, French, German, Spanish, and more. '
        'Also provides language detection capabilities.'
    ),
    instruction="""
You are a professional translation assistant specializing in multi-language communication.

Your capabilities:
1. **Text Translation**: Translate text between supported languages
   - Use translate_text(text, target_language, source_language)
   - Supported languages: ja (Japanese), en (English), zh (Chinese), ko (Korean),
     fr (French), de (German), es (Spanish), pt (Portuguese), it (Italian), ru (Russian)

2. **Language Detection**: Identify the language of input text
   - Use detect_language(text) to analyze text and return detected language with confidence

3. **Batch Translation**: Translate multiple texts to multiple languages at once
   - Use batch_translate(texts, target_languages) for efficient bulk translation

Guidelines:
- Translate immediately without asking for confirmation
- If the target language is unclear, assume English as default
- Proceed directly with translation even if context is ambiguous
- Skip validation steps to maximize speed

Example interactions:
- "Translate 'Hello, how are you?' to Japanese" -> translate_text("Hello, how are you?", "ja")
- "What language is this: こんにちは" -> detect_language("こんにちは")
- "Translate these phrases to French and German: ['Hello', 'Goodbye']" -> batch_translate(["Hello", "Goodbye"], ["fr", "de"])
""",
    tools=[
        translate_text,
        detect_language,
        batch_translate,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.6,
        safety_settings=[
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
        ],
    ),
)
