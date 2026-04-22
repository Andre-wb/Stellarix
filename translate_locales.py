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

LOCALE_DIR = 'locales'
BATCH_SIZE = 40            # upper bound on strings per API call
MAX_BATCH_CHARS = 4500     # Google Translate hard limit is 5000; leave headroom
SINGLE_MAX_CHARS = 4800    # for a lone string; above this we must chunk or skip
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

# GLOBAL terms: protected in ALL sections — technical terms that should
# never be translated regardless of context.
_GLOBAL_TERMS = sorted([
    # Product / brand names
    'Gravitix', 'Vortex', 'Cloudflare', "Let's Encrypt", 'Telegram',
    'GitHub', 'Google', 'Apple', 'Microsoft', 'Azure AD',
    'Keycloak', 'Authentik', 'Ollama', 'Matrix', 'Element',
    # Technical product terms (CamelCase / mixed case)
    'WebSocket', 'WebRTC', 'WebAuthn', 'Passkey', 'Passkeys',
    'Mini App', 'Bot Store', 'mkcert', 'cloudflared', 'certbot',
    # Protocols / standards (mixed case)
    'OAuth', 'OIDC', 'FIDO2', 'ECIES', 'X25519', 'BIP39',
    'Wi-Fi', 'Wi-Fi Direct',
    # Programming language names
    'Rust', 'Python', 'JavaScript', 'Go', 'HTML', 'CSS',
], key=len, reverse=True)

# GRAVITIX-ONLY terms: protected only in gravitixDocs/gxd sections.
# These are short keywords that are too common in normal English to
# protect globally (e.g. "match", "state", "flow", "guard", "let").
_GRAVITIX_TERMS = sorted([
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
], key=len, reverse=True)

# Sections where Gravitix-specific term protection is applied
_GRAVITIX_SECTIONS = {'gravitixDocs', 'gxd'}


def _protect_value(text, section):
    """
    Protect a value before sending to Google Translate.
    Returns (protected_text, replacements_list).

    Five layers (applied in order):
    1. <code>content</code> → single placeholder (code = never translate)
    2. Standalone HTML tags → placeholder each
    3. ALL-CAPS words (2+ chars) → placeholder (HTTP, SSL, API, QR, P2P, etc.)
    4. Global technical terms (WebSocket, Cloudflare, mkcert, etc.) → placeholder
    5. Gravitix-specific keywords (only for gravitixDocs/gxd sections)
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

    # Layer 3: ALL-CAPS words (2+ letters, optionally with digits/hyphens).
    # Catches: HTTP, HTTPS, SSL, API, URL, JSON, P2P, E2E, QR, PDF, GIF,
    #          UDP, TCP, DNS, SFU, BLE, SSO, JWT, CSRF, TOTP, HMAC, etc.
    # Skips single-letter caps and normal short words in sentences.
    text = re.sub(
        r'\b[A-Z][A-Z0-9]{1,}(?:[-/][A-Z0-9]+)*\b',
        lambda m: _add(m.group(0)),
        text
    )

    # Layer 4: global technical terms (applied to ALL sections)
    for term in _GLOBAL_TERMS:
        if term not in text:
            continue
        while term in text:
            text = text.replace(term, _add(term), 1)

    # Layer 5: Gravitix-specific keywords (only for docs sections)
    if section in _GRAVITIX_SECTIONS:
        for term in _GRAVITIX_TERMS:
            if term not in text:
                continue
            if len(term) <= 3 and term.isalpha():
                pattern = r'(?<![a-zA-Z])' + re.escape(term) + r'(?![a-zA-Z])'
                if re.search(pattern, text):
                    text = re.sub(pattern, lambda m: _add(term), text)
            else:
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
    """Find all keys where locale value == en value (untranslated fallback).

    Walks arbitrary-depth nested dicts + lists. Returns a flat list of
    `(section, path, en_value)` tuples where `section` is the top-level
    JSON key (used for per-section term-protection rules) and `path`
    is a dotted/indexed path inside that section, e.g.
    `"federation.intro.h1_a"` or `"__arr_3"` or `"a.__arr_2.title"`.
    """
    fallbacks = []

    def walk(en_node, loc_node, section, path):
        # String leaf — compare and record if it's a true fallback.
        if isinstance(en_node, str):
            if not en_node or en_node in SKIP_VALUES:
                return
            if loc_node == en_node:
                # key check using the LAST path segment
                last_seg = path.rsplit('.', 1)[-1] if path else ''
                if last_seg in SKIP_KEYS:
                    return
                fallbacks.append((section, path, en_node))
            return

        # Dict — recurse per key. If locale side is missing/mismatched,
        # we treat the leaf as an untranslated fallback (== en).
        if isinstance(en_node, dict):
            if not isinstance(loc_node, dict):
                loc_node = {}
            for k, v in en_node.items():
                if k in SKIP_KEYS:
                    continue
                sub_loc = loc_node.get(k)
                sub_path = f'{path}.{k}' if path else k
                walk(v, sub_loc, section, sub_path)
            return

        # List — recurse per index. Record string leaves as __arr_N.
        if isinstance(en_node, list):
            if not isinstance(loc_node, list):
                loc_node = []
            for i, v in enumerate(en_node):
                sub_loc = loc_node[i] if i < len(loc_node) else None
                sub_path = f'{path}.__arr_{i}' if path else f'__arr_{i}'
                walk(v, sub_loc, section, sub_path)
            return

        # Numbers, bools, None — nothing to translate.

    for section, en_sub in en_data.items():
        if section in SKIP_KEYS:
            continue
        loc_sub = locale_data.get(section)
        # Top-level scalar string handled too (rare but possible).
        walk(en_sub, loc_sub, section, '')
    return fallbacks


def _set_by_path(root, section, path, value):
    """Write `value` into root[section][path] where `path` is a dotted/
    __arr_N mixed path. Creates missing intermediate containers lazily.
    Returns True if the final write succeeded."""
    if section not in root:
        return False
    node = root[section]
    parts = path.split('.') if path else []
    for p in parts[:-1]:
        if p.startswith('__arr_'):
            idx = int(p[len('__arr_'):])
            if not isinstance(node, list) or idx >= len(node):
                return False
            node = node[idx]
        else:
            if not isinstance(node, dict) or p not in node:
                return False
            node = node[p]
    if not parts:
        # Whole section is a string — rare; write back to the section.
        root[section] = value
        return True
    last = parts[-1]
    if last.startswith('__arr_'):
        idx = int(last[len('__arr_'):])
        if not isinstance(node, list) or idx >= len(node):
            return False
        node[idx] = value
        return True
    if not isinstance(node, dict):
        return False
    node[last] = value
    return True


def _joined_len(strings):
    """Total character length when joined with SEPARATOR."""
    if not strings:
        return 0
    return sum(len(s) for s in strings) + len(SEPARATOR) * (len(strings) - 1)


def batch_translate(strings, target_lang, retries=3):
    """Translate a batch of strings by joining with separator.

    Size-aware: if the joined payload is over MAX_BATCH_CHARS, recursively
    split the batch in half so the HTTP call never breaches Google's
    5000-char per-request limit.
    """
    if not strings:
        return strings

    # Split over-long batches before we even try the network.
    if _joined_len(strings) > MAX_BATCH_CHARS and len(strings) > 1:
        mid = len(strings) // 2
        left = batch_translate(strings[:mid], target_lang, retries=retries)
        right = batch_translate(strings[mid:], target_lang, retries=retries)
        return list(left) + list(right)

    # A single string that alone exceeds the limit — can't join anything, so
    # hand it to the one-by-one path which at worst returns the original.
    if len(strings) == 1 and len(strings[0]) > SINGLE_MAX_CHARS:
        print(f'    skipping {len(strings[0])}-char oversize string (>{SINGLE_MAX_CHARS})')
        return list(strings)

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
            # If the error is specifically the length cap, halve the batch
            # immediately rather than retrying the same too-long payload.
            if 'length' in str(e).lower() and len(strings) > 1:
                mid = len(strings) // 2
                left = batch_translate(strings[:mid], target_lang, retries=retries)
                right = batch_translate(strings[mid:], target_lang, retries=retries)
                return list(left) + list(right)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                err_preview = str(e)[:160].replace('\n', ' ')
                print(f'    ERROR translating batch ({len(strings)} strings, '
                      f'{_joined_len(strings)} chars): {err_preview}')
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

    # Translate in batches — size-aware: start a new batch when either
    # the string count reaches BATCH_SIZE or the joined length would
    # exceed MAX_BATCH_CHARS.
    translated = []
    batch = []
    batch_chars = 0
    for s in strings:
        projected = batch_chars + len(s) + (len(SEPARATOR) if batch else 0)
        if batch and (len(batch) >= BATCH_SIZE or projected > MAX_BATCH_CHARS):
            translated.extend(batch_translate(batch, google_code))
            time.sleep(0.3)  # rate limit
            batch = []
            batch_chars = 0
        batch.append(s)
        batch_chars += len(s) + (len(SEPARATOR) if len(batch) > 1 else 0)
    if batch:
        translated.extend(batch_translate(batch, google_code))

    # Restore protected terms and HTML after translation
    for i, pmap in enumerate(protection_maps):
        if pmap and i < len(translated):
            translated[i] = _restore_value(translated[i], pmap)

    # Apply translations back to locale data (arbitrary-depth paths).
    changed = 0
    for (section, path, orig), trans in zip(fallbacks, translated):
        if trans and trans != orig:
            if _set_by_path(locale_data, section, path, trans):
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
