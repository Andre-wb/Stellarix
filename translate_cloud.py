#!/usr/bin/env python3
"""
Translate unsupported-by-free-Google locales via Google Cloud Translation API.
Uses the v2 REST API with an API key.

Usage:
    python3 translate_cloud.py                  # all 17 languages
    python3 translate_cloud.py ba ce cv         # specific languages only

Requires: requests (pip install requests)
"""

import json
import os
import sys
import time
import re

import requests

# ── Config ──
API_KEY = os.environ.get('GOOGLE_TRANSLATE_API_KEY', '')
LOCALE_DIR = 'static/locales'
BATCH_SIZE = 80        # strings per API call (Cloud API handles larger batches)
SKIP_VALUES = {'VORTEX', '', ' '}
SKIP_KEYS = {'fullReference'}

# Languages not supported by free deep-translator but supported by Cloud API
CLOUD_LANGS = [
    'ba', 'ce', 'cv', 'sah', 'mhr', 'os', 'crh', 'udm', 'tyv', 'bua',
    'kv', 'bo', 'ff', 'oc', 'wo', 'tn',
]

# Cloud API uses slightly different codes for some languages
CLOUD_CODE_MAP = {
    'sah': 'sah',   # Yakut — supported as 'sah'
    'mhr': 'mhr',   # Mari
    'crh': 'crh',   # Crimean Tatar
    'udm': 'udm',   # Udmurt
    'tyv': 'tyv',   # Tuvan
    'bua': 'bua',   # Buryat
    'tok': 'tok',   # Tok Pisin
}

TRANSLATE_URL = 'https://translation.googleapis.com/language/translate/v2'


def get_cloud_code(locale_code):
    return CLOUD_CODE_MAP.get(locale_code, locale_code)


def cloud_translate(texts, target_lang, retries=3):
    """Translate a list of strings via Google Cloud Translation API v2."""
    if not texts:
        return texts

    for attempt in range(retries):
        try:
            resp = requests.post(TRANSLATE_URL, params={'key': API_KEY}, json={
                'q': texts,
                'source': 'en',
                'target': target_lang,
                'format': 'text',
            }, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                translations = data['data']['translations']
                return [t['translatedText'] for t in translations]
            else:
                error = resp.json().get('error', {})
                msg = error.get('message', resp.text[:200])
                print(f'      API error {resp.status_code}: {msg}', flush=True)
                if resp.status_code == 403 or resp.status_code == 401:
                    return texts  # auth error, don't retry
                if resp.status_code == 400 and 'unsupported' in msg.lower():
                    return texts  # language not supported

        except Exception as e:
            print(f'      Request error: {e}', flush=True)

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    return texts  # fallback to original


def collect_fallbacks(en_data, locale_data):
    """Find keys where locale value == en value (untranslated fallback)."""
    fallbacks = []
    for section, keys in en_data.items():
        if isinstance(keys, dict):
            for k, v in keys.items():
                if isinstance(v, str) and v and k not in SKIP_KEYS and v not in SKIP_VALUES:
                    if locale_data.get(section, {}).get(k) == v:
                        fallbacks.append((section, k, v))
    return fallbacks


def process_locale(code, en_data):
    cloud_code = get_cloud_code(code)
    path = os.path.join(LOCALE_DIR, code + '.json')
    if not os.path.exists(path):
        print(f'  {code}: file not found, skipping', flush=True)
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        loc = json.load(f)

    fallbacks = collect_fallbacks(en_data, loc)
    if not fallbacks:
        print(f'  {code}: no fallbacks to translate', flush=True)
        return 0

    strings = [fb[2] for fb in fallbacks]
    total_chars = sum(len(s) for s in strings)
    print(f'  {code}: {len(fallbacks)} strings ({total_chars:,d} chars) → {cloud_code}', flush=True)

    # Translate in batches
    translated = []
    for i in range(0, len(strings), BATCH_SIZE):
        batch = strings[i:i + BATCH_SIZE]
        result = cloud_translate(batch, cloud_code)
        translated.extend(result)
        done = min(i + BATCH_SIZE, len(strings))
        print(f'    [{done}/{len(strings)}]', flush=True)
        if i + BATCH_SIZE < len(strings):
            time.sleep(0.2)

    # Apply translations
    changed = 0
    for (section, key, orig), trans in zip(fallbacks, translated):
        if trans and trans != orig:
            if section in loc and isinstance(loc[section], dict):
                loc[section][key] = trans
                changed += 1

    if changed > 0:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(loc, f, ensure_ascii=False, indent=2)
            f.write('\n')

    print(f'  {code}: {changed}/{len(fallbacks)} translated', flush=True)
    return changed


def main():
    if not API_KEY:
        print('ERROR: set GOOGLE_TRANSLATE_API_KEY environment variable')
        print('  export GOOGLE_TRANSLATE_API_KEY="AIza..."')
        sys.exit(1)

    en_data = json.load(open(os.path.join(LOCALE_DIR, 'en.json'), encoding='utf-8'))

    targets = sys.argv[1:] if len(sys.argv) > 1 else CLOUD_LANGS

    # Estimate total chars
    total_chars = 0
    for code in targets:
        path = os.path.join(LOCALE_DIR, code + '.json')
        if not os.path.exists(path):
            continue
        loc = json.load(open(path, encoding='utf-8'))
        fallbacks = collect_fallbacks(en_data, loc)
        total_chars += sum(len(fb[2]) for fb in fallbacks)

    print(f'Estimated: {total_chars:,d} characters ({len(targets)} languages)')
    print(f'Free limit: 500,000/month')
    if total_chars > 450000:
        print(f'WARNING: close to limit!')
    print()

    total_changed = 0
    for code in targets:
        try:
            changed = process_locale(code, en_data)
            total_changed += changed
        except Exception as e:
            print(f'  ERROR {code}: {e}')

    print(f'\nDONE: {total_changed} strings translated across {len(targets)} languages')


if __name__ == '__main__':
    main()
