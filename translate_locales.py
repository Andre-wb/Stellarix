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


def _discover_locale_dir():
    """Find the locale directory relative to the script or the CWD.

    Supports three repo layouts:
      - vortex-introduce-page/locales/
      - Vortex/static/locales/
      - vortex.sol-mirror/static/locales/
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, 'locales'),
        os.path.join(here, 'static', 'locales'),
        'locales',
        'static/locales',
    ]
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, 'en.json')):
            return c
    raise SystemExit(
        'Could not find a locales directory with en.json. '
        'Expected one of: locales/, static/locales/'
    )


LOCALE_DIR = _discover_locale_dir()
BATCH_SIZE = 40            # upper bound on strings per API call
MAX_BATCH_CHARS = 4500     # Google Translate hard limit is 5000; leave headroom
SINGLE_MAX_CHARS = 4800    # for a lone string; above this we must chunk or skip
FLUSH_EVERY_BATCHES = 10   # incremental save — protects partial work against net loss
MAX_CONSECUTIVE_NET_FAILS = 20   # give up on this locale if the net is clearly dead
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
            err_msg = str(e).lower()
            # If the error is specifically the length cap, halve the batch
            # immediately rather than retrying the same too-long payload.
            if 'length' in err_msg and len(strings) > 1:
                mid = len(strings) // 2
                left = batch_translate(strings[:mid], target_lang, retries=retries)
                right = batch_translate(strings[mid:], target_lang, retries=retries)
                return list(left) + list(right)
            # Network / rate-limit / proxy failures → long exponential backoff.
            # Typical text: "Max retries exceeded", "ConnectionError",
            # "429 Too Many Requests", "Connection reset".
            is_network = any(x in err_msg for x in (
                'max retries', 'connection', 'timed out', 'timeout',
                '429', 'rate', 'reset by peer', 'temporary failure'
            ))
            if attempt < retries - 1:
                delay = (10 * (2 ** attempt)) if is_network else (2 ** attempt)
                if is_network and attempt >= 1:
                    print(f'    network/rate-limit; sleeping {delay}s before retry...',
                          flush=True)
                time.sleep(delay)
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
    """Probe whether Google supports `google_code`.

    Returns one of:
      True  — confirmed supported (translated "hello" successfully).
      False — confirmed unsupported (Google raised a language-code error).
      None  — indeterminate (network / rate-limit error). Caller should
              NOT treat this as "unsupported" — skip this *attempt*, but
              do not poison the cache for the rest of the session.
    """
    for attempt in range(3):
        try:
            r = GoogleTranslator(source='en', target=google_code).translate('hello')
            return bool(r)
        except Exception as e:
            msg = str(e).lower()
            # Permanent unsupported — language code rejected by the API.
            if ('language' in msg and 'not' in msg) or 'invalid' in msg or \
                    'not supported' in msg:
                return False
            # Transient: connection reset, rate limit, DNS, etc.
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return None

# Cache supported status per session — ONLY for confirmed answers (True/False).
# Transient failures (None) are NOT cached so the next locale attempt re-probes.
_supported_cache = {}

def process_locale(fname, en_data):
    """Process a single locale file."""
    locale_code = fname.replace('.json', '')
    google_code = get_google_code(locale_code)

    # Skip unsupported languages (check once, cache CONFIRMED result).
    # Transient network/rate-limit failures return None → we treat that as
    # "try again this locale", not "blacklist the language forever".
    if google_code not in _supported_cache:
        probe = _check_supported(google_code)
        if probe is None:
            print(f'  RATE-LIMITED probing {google_code} — waiting 60 s then retrying...',
                  flush=True)
            time.sleep(60)
            probe = _check_supported(google_code)
        if probe is not None:
            _supported_cache[google_code] = probe   # cache only confirmed results
        # probe is still None after retry → treat as supported and let the main
        # translation loop either succeed or fail visibly.
    supported = _supported_cache.get(google_code, True)
    if supported is False:
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

    # ── Estimate batch count up-front for progress display ──
    # Walks `strings` the same way the main loop does, but just counts.
    def _estimate_batches(items):
        cnt = 0
        bs = 0
        bc = 0
        for s in items:
            projected = bc + len(s) + (len(SEPARATOR) if bs else 0)
            if bs and (bs >= BATCH_SIZE or projected > MAX_BATCH_CHARS):
                cnt += 1
                bs = 0
                bc = 0
            bs += 1
            bc += len(s) + (len(SEPARATOR) if bs > 1 else 0)
        if bs:
            cnt += 1
        return cnt

    total_batches = _estimate_batches(strings)
    locale_start = time.monotonic()

    def _ts():
        return time.strftime('%H:%M:%S')

    # Translate in batches — size-aware + incremental save.
    # Every FLUSH_EVERY_BATCHES successful batches we write the partial
    # result to disk so a network drop or Ctrl+C doesn't lose progress.
    translated = []
    batch = []
    batch_chars = 0
    batches_since_flush = 0
    batch_index = 0
    consecutive_net_fails = 0
    running_written = 0        # cumulative translated + saved across all flushes
    aborted = False

    def flush_to_disk(n_trans_so_far: int):
        """Apply current `translated` slice back to locale_data and save."""
        written = 0
        for i in range(n_trans_so_far):
            if i >= len(fallbacks) or i >= len(translated): break
            section, key_path, orig = fallbacks[i]
            trans = translated[i]
            if pmap := protection_maps[i]:
                trans = _restore_value(trans, pmap)
                translated[i] = trans   # cache restored form
            if trans and trans != orig:
                if _set_by_path(locale_data, section, key_path, trans):
                    written += 1
        if written > 0:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(locale_data, f, ensure_ascii=False, indent=2)
                f.write('\n')
        return written

    def run_batch(current_batch):
        nonlocal consecutive_net_fails, batch_index
        batch_index += 1
        bn, bs, bc = batch_index, len(current_batch), _joined_len(current_batch)
        t0 = time.monotonic()
        result = batch_translate(current_batch, google_code)
        dt = time.monotonic() - t0
        # Heuristic: if the returned list equals the input (fallback-on-error),
        # count it as a network failure for the early-abort counter.
        is_fail = (result is current_batch or list(result) == list(current_batch))
        if is_fail:
            consecutive_net_fails += 1
            status = f'FAIL (net, consecutive={consecutive_net_fails})'
        else:
            consecutive_net_fails = 0
            ok_count = sum(1 for a, b in zip(current_batch, result) if a != b)
            status = f'ok {ok_count}/{bs}'
        elapsed_min = (time.monotonic() - locale_start) / 60
        print(f'  [{_ts()}] {fname} batch {bn}/{total_batches}  '
              f'{bs:>3}str {bc:>4}chars  {status}  '
              f'{dt:.1f}s  (elapsed {elapsed_min:.1f}m)',
              flush=True)
        return result

    for s in strings:
        projected = batch_chars + len(s) + (len(SEPARATOR) if batch else 0)
        if batch and (len(batch) >= BATCH_SIZE or projected > MAX_BATCH_CHARS):
            translated.extend(run_batch(batch))
            batches_since_flush += 1
            batch = []
            batch_chars = 0
            if consecutive_net_fails >= MAX_CONSECUTIVE_NET_FAILS:
                print(f'  [{_ts()}] {fname}: {MAX_CONSECUTIVE_NET_FAILS} '
                      f'consecutive network failures — aborting early. '
                      f'Already-translated progress will be saved.',
                      flush=True)
                aborted = True
                break
            if batches_since_flush >= FLUSH_EVERY_BATCHES:
                w = flush_to_disk(len(translated))
                running_written = w
                print(f'  [{_ts()}] {fname} → flushed to disk '
                      f'({w}/{len(fallbacks)} cumulative)',
                      flush=True)
                batches_since_flush = 0
            time.sleep(0.3)  # rate limit
        batch.append(s)
        batch_chars += len(s) + (len(SEPARATOR) if len(batch) > 1 else 0)
    if batch and not aborted:
        translated.extend(run_batch(batch))

    # Final flush — writes remaining translations (including the tail batch).
    changed = flush_to_disk(len(translated))

    total_min = (time.monotonic() - locale_start) / 60
    suffix = ' (aborted early)' if aborted else ''
    print(f'  [{_ts()}] {fname}: {changed}/{len(fallbacks)} strings '
          f'translated in {total_min:.1f}m{suffix}',
          flush=True)
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

    # Inter-locale cooldown — gives Google's rate-limiter a chance to settle
    # before we push another 16 000 strings. Tuned for the 100k+ strings
    # this script translates per locale.
    INTER_LOCALE_COOLDOWN_SEC = 15

    for code in priority:
        fname = code + '.json'
        if not os.path.exists(os.path.join(LOCALE_DIR, fname)):
            continue
        try:
            changed = process_locale(fname, en_data)
            total_changed += changed
            total_files += 1
            if changed > 0:
                time.sleep(INTER_LOCALE_COOLDOWN_SEC)
        except Exception as e:
            print(f'  ERROR processing {fname}: {e}')

    print(f'\nDONE: {total_changed} strings translated across {total_files} files')


if __name__ == '__main__':
    main()
