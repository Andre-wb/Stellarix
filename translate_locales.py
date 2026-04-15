#!/usr/bin/env python3
"""
Translate all English fallback strings in locale files to their native languages.
Uses Google Translate via deep-translator.

Protection layers:
1. <code>...</code> → entire element becomes a placeholder (code = never translate)
2. <strong>, <em>, <br> tags → tag becomes placeholder, inner text translated
3. Gravitix keywords (emit, guard, struct, Rust…) → placeholder in protected sections
4. {placeholders} in template strings → preserved
"""

import json
import os
import sys
import time
import re

from deep_translator import GoogleTranslator

LOCALE_DIR = 'static/locales'
BATCH_SIZE = 40  # strings per API call
SEPARATOR = '\n|||SEP|||\n'
SKIP_VALUES = {'VORTEX', '', ' '}
SKIP_KEYS = {'fullReference'}  # large technical docs — keep English

# Remap our locale codes to Google Translate codes where they differ
CODE_MAP = {
    'he': 'iw',        # Hebrew
    'jv': 'jw',        # Javanese
    'zh': 'zh-CN',
    'zh-TW': 'zh-TW',
}

# ── Term protection ──────────────────────────────────────────────────────
# Gravitix language keywords, product names, and syntax that must NEVER
# be translated. Sorted longest-first so "emit_to" matches before "emit".
_PROTECTED_TERMS = sorted([
    # Product / language names
    'Gravitix', 'Vortex', 'Rust', 'Python', 'JavaScript', 'Go', 'IEEE 754',
    # Gravitix keywords (lowercase — used in code/syntax)
    'emit_to', 'emit', 'state', 'flow', 'guard', 'match', 'wait',
    'break', 'continue', 'elif', 'struct', 'enum', 'impl', 'self',
    'every', 'pipe', 'ctx', 'let', 'fn', 'msg', 'void', 'null',
    'try', 'catch', 'finally', 'throw', 'return',
    # Capitalized / plural forms (used in headings and descriptions)
    'Structs', 'Struct', 'Enums', 'Enum', 'Flows', 'Flow',
    'Guards', 'Guard', 'State', 'Emit', 'Pipe', 'Match',
    'Handlers', 'Handler',
    # Gravitix syntax / types
    '|>', 'T?', 'int', 'float', 'str', 'bool',
    # Commands used in docs
    '/start', '/help', '/echo', '/buy',
    # Style conventions
    'snake_case',
    # Technical abbreviations
    'DSL', 'FFT', 'DFT', 'UTC',
], key=len, reverse=True)

# Sections where Gravitix term protection is applied
_TERM_PROTECT_SECTIONS = {'gravitixDocs', 'gxd'}


def _protect_value(text, section):
    """
    Protect a value before sending to Google Translate.
    Returns (protected_text, replacements_list).

    Three layers:
    1. <code>content</code> → single placeholder (content is code, never translate)
    2. Standalone HTML tags (<strong>, </strong>, <em>, <br>) → placeholder each
    3. Gravitix keywords (only for _TERM_PROTECT_SECTIONS)
    """
    replacements = []

    def _add(original):
        idx = len(replacements)
        ph = f'\u27ea{idx}\u27eb'  # ⟪0⟫
        replacements.append((ph, original))
        return ph

    # Layer 1: <code>...</code> — entire element is a placeholder
    text = re.sub(
        r'<code>[^<]*</code>',
        lambda m: _add(m.group(0)),
        text
    )

    # Layer 2: remaining standalone HTML tags
    text = re.sub(
        r'</?(strong|em|br|a|span|div|ul|li|p)\b[^>]*>',
        lambda m: _add(m.group(0)),
        text
    )

    # Layer 3: Gravitix keywords (only for docs sections)
    if section in _TERM_PROTECT_SECTIONS:
        for term in _PROTECTED_TERMS:
            if term not in text:
                continue
            if len(term) <= 3 and term.isalpha():
                pattern = r'(?<![a-zA-Z])' + re.escape(term) + r'(?![a-zA-Z])'
                if re.search(pattern, text):
                    text = re.sub(pattern, lambda m: _add(term), text)
            else:
                # Replace all occurrences
                while term in text:
                    text = text.replace(term, _add(term), 1)

    return text, replacements


def _restore_value(text, replacements):
    """Restore all placeholders after translation."""
    for placeholder, original in replacements:
        # Google Translate sometimes adds/removes spaces around placeholders
        text = text.replace(f' {placeholder} ', f' {original} ')
        text = text.replace(f' {placeholder}', f' {original}')
        text = text.replace(f'{placeholder} ', f'{original} ')
        text = text.replace(placeholder, original)
    return text


def get_google_code(locale_code):
    """Map our locale code to Google Translate code."""
    return CODE_MAP.get(locale_code, locale_code)


def collect_fallback_strings(en_data, locale_data):
    """Find all keys where locale value == en value (untranslated fallback)."""
    fallbacks = []  # list of (section, key, en_value)
    for section, keys in en_data.items():
        if isinstance(keys, dict):
            # For nested sections like gxd.intro.h1, flatten
            for k, v in keys.items():
                if isinstance(v, dict):
                    # Two-level nesting: gxd -> section -> key
                    loc_sub = locale_data.get(section, {}).get(k, {})
                    if isinstance(loc_sub, dict):
                        for k2, v2 in v.items():
                            if isinstance(v2, str) and v2 and loc_sub.get(k2) == v2:
                                if v2 not in SKIP_VALUES and k2 not in SKIP_KEYS:
                                    fallbacks.append((section, f'{k}.{k2}', v2))
                elif isinstance(v, str) and v and locale_data.get(section, {}).get(k) == v:
                    if v not in SKIP_VALUES and k not in SKIP_KEYS:
                        fallbacks.append((section, k, v))
        elif isinstance(keys, list):
            loc_list = locale_data.get(section, [])
            if isinstance(loc_list, list) and loc_list == keys:
                for i, v in enumerate(keys):
                    if isinstance(v, str) and v:
                        fallbacks.append((section, f'__arr_{i}', v))
    return fallbacks


def batch_translate(strings, target_lang, retries=3):
    """Translate a batch of strings by joining with separator."""
    if not strings:
        return strings

    text = SEPARATOR.join(strings)
    for attempt in range(retries):
        try:
            translator = GoogleTranslator(source='en', target=target_lang)
            result = translator.translate(text)
            if not result:
                return strings  # fallback to original

            parts = result.split('|||SEP|||')
            # Clean up parts
            parts = [p.strip() for p in parts]

            if len(parts) != len(strings):
                # Separator got mangled, try one by one
                return translate_one_by_one(strings, target_lang)

            # Restore {placeholders} that might have been translated
            restored = []
            for orig, translated in zip(strings, parts):
                orig_placeholders = re.findall(r'\{[^}]+\}', orig)
                trans_placeholders = re.findall(r'\{[^}]+\}', translated)
                if len(orig_placeholders) != len(trans_placeholders):
                    for ph in orig_placeholders:
                        if ph not in translated:
                            translated = translated  # keep as is, best effort
                restored.append(translated)
            return restored

        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f'    ERROR translating batch: {e}')
                return strings  # fallback to original


def translate_one_by_one(strings, target_lang):
    """Fallback: translate strings individually."""
    results = []
    translator = GoogleTranslator(source='en', target=target_lang)
    for s in strings:
        try:
            r = translator.translate(s)
            results.append(r if r else s)
            time.sleep(0.1)
        except:
            results.append(s)
    return results


def _check_supported(google_code):
    """Quick check: try translating one word. Returns False if unsupported."""
    try:
        r = GoogleTranslator(source='en', target=google_code).translate('hello')
        return bool(r)
    except:
        return False

# Cache supported status per session
_supported_cache = {}

def process_locale(fname, en_data):
    """Process a single locale file."""
    locale_code = fname.replace('.json', '')
    google_code = get_google_code(locale_code)

    # Skip unsupported languages (check once, cache result)
    if google_code not in _supported_cache:
        _supported_cache[google_code] = _check_supported(google_code)
    if not _supported_cache[google_code]:
        print(f'  SKIP {fname} — {google_code} not supported by deep-translator', flush=True)
        return 0

    path = os.path.join(LOCALE_DIR, fname)
    locale_data = json.load(open(path, encoding='utf-8'))

    fallbacks = collect_fallback_strings(en_data, locale_data)
    if not fallbacks:
        print(f'  {fname}: no fallbacks to translate', flush=True)
        return 0

    print(f'  {fname}: {len(fallbacks)} fallback strings → translating to {google_code}...', flush=True)

    # Protect HTML + Gravitix terms before translation
    strings = []
    protection_maps = []
    for section, key, value in fallbacks:
        protected_text, pmap = _protect_value(value, section)
        strings.append(protected_text)
        protection_maps.append(pmap)

    # Translate in batches
    translated = []
    for i in range(0, len(strings), BATCH_SIZE):
        batch = strings[i:i + BATCH_SIZE]
        result = batch_translate(batch, google_code)
        translated.extend(result)
        if i + BATCH_SIZE < len(strings):
            time.sleep(0.3)  # rate limit

    # Restore protected terms and HTML after translation
    for i, pmap in enumerate(protection_maps):
        if pmap and i < len(translated):
            translated[i] = _restore_value(translated[i], pmap)

    # Apply translations back to locale data
    changed = 0
    for (section, key, orig), trans in zip(fallbacks, translated):
        if trans and trans != orig:
            if key.startswith('__arr_'):
                idx = int(key.replace('__arr_', ''))
                if isinstance(locale_data.get(section), list) and idx < len(locale_data[section]):
                    locale_data[section][idx] = trans
                    changed += 1
            elif '.' in key and not key.startswith('__'):
                # Nested key like "intro.h1" → gxd.intro.h1
                parts = key.split('.', 1)
                sub = locale_data.get(section, {}).get(parts[0], {})
                if isinstance(sub, dict):
                    sub[parts[1]] = trans
                    changed += 1
            else:
                if section in locale_data and isinstance(locale_data[section], dict):
                    locale_data[section][key] = trans
                    changed += 1

    if changed > 0:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(locale_data, f, ensure_ascii=False, indent=2)
            f.write('\n')

    print(f'  {fname}: {changed}/{len(fallbacks)} strings translated', flush=True)
    return changed


def main():
    en_data = json.load(open(os.path.join(LOCALE_DIR, 'en.json'), encoding='utf-8'))

    # Priority order: most common languages first
    priority = [
        'ru', 'es', 'de', 'fr', 'zh', 'ja', 'ko', 'pt', 'it', 'ar',
        'hi', 'tr', 'pl', 'nl', 'uk', 'id', 'th', 'vi', 'sv', 'da',
        'fi', 'no', 'cs', 'ro', 'hu', 'el', 'he', 'fa', 'bg', 'hr',
        'sr', 'sk', 'sl', 'lt', 'lv', 'et', 'ka', 'hy', 'az', 'kk',
        'uz', 'ky', 'mn', 'ms', 'tl', 'sw', 'af', 'ak', 'am', 'as',
        'ay', 'ba', 'be', 'bho', 'bm', 'bn', 'bo', 'bs', 'bua', 'ca',
        'ce', 'ceb', 'ckb', 'co', 'crh', 'cv', 'cy', 'doi', 'dv', 'ee',
        'eo', 'eu', 'ff', 'fy', 'ga', 'gd', 'gl', 'gn', 'gu', 'ha',
        'haw', 'hmn', 'ht', 'ig', 'ilo', 'is', 'jv', 'km', 'kn', 'kri',
        'ku', 'kv', 'la', 'lb', 'lg', 'ln', 'lo', 'lus', 'mai', 'mg',
        'mhr', 'mi', 'mk', 'ml', 'mr', 'mt', 'my', 'ne', 'nso', 'ny',
        'oc', 'om', 'or', 'os', 'pa', 'ps', 'qu', 'rw', 'sa', 'sah',
        'sd', 'si', 'sm', 'sn', 'so', 'sq', 'st', 'su', 'ta', 'te',
        'tg', 'ti', 'tk', 'tn', 'tt', 'tyv', 'udm', 'ug', 'ur', 'wo',
        'xh', 'yi', 'yo', 'zh-TW', 'zu',
    ]

    # Add any remaining files not in priority list
    all_files = [f.replace('.json', '') for f in os.listdir(LOCALE_DIR)
                 if f.endswith('.json') and f != 'en.json']
    for code in all_files:
        if code not in priority:
            priority.append(code)

    total_changed = 0
    total_files = 0

    for code in priority:
        fname = code + '.json'
        if not os.path.exists(os.path.join(LOCALE_DIR, fname)):
            continue
        try:
            changed = process_locale(fname, en_data)
            total_changed += changed
            total_files += 1
        except Exception as e:
            print(f'  ERROR processing {fname}: {e}')

    print(f'\nDONE: {total_changed} strings translated across {total_files} files')


if __name__ == '__main__':
    main()
