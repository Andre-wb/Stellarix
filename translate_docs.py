#!/usr/bin/env python3
"""
Translate gravitixDocs.fullReference in all locale files.
Splits the document into lines, skips code blocks and markup,
translates only prose via Google Translate, reassembles.
"""

import json
import os
import sys
import time
import re

from deep_translator import GoogleTranslator

LOCALE_DIR = 'static/locales'
BATCH_SIZE = 30  # prose lines per API call
SEPARATOR = '\n|||SEP|||\n'

# ── Google Translate code mapping (same as translate_locales.py) ──

# Remap our locale codes to Google Translate codes where they differ
CODE_MAP = {
    'he': 'iw', 'jv': 'jw', 'zh': 'zh-CN', 'zh-TW': 'zh-TW',
}

PRIORITY = [
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


def get_google_code(locale_code):
    return CODE_MAP.get(locale_code, locale_code)


# ── Split document into translatable / non-translatable chunks ──

_CODE_RE = re.compile(r'|'.join([
    r'^(let|fn |on |if |elif |else |while |for |match |state\s*\{|return |try\s*\{|catch\s*'
    r'|struct |enum |enum\s*\{|every |at |emit |emit_to|flow |wait )',
    r'^"[^"]*"\s*=>',           # match arm: "x" => ...
    r'^\d[\d_]*\s*(\.\.=?|=>)', # range or match: 0..10, 42 =>
    r'[{};]\s*$',               # ends with { } ;
    r'^\w+\s*\(.*\)\s*;?\s*$',  # function call: foo(bar)
    r'^\w+\.\w+',               # dot access: state.x, ctx.text
    r'^\/\/',                    # comment: // ...
    r'^\*\s*=>',                 # wildcard match: * =>
    r'^(true|false)\s*=>',       # bool match arm: true => ...
    r'^\w+\([^)]*\)\s*;',       # function call with ;: greet("x");
    r'^\w+\s*(\+|-|\*|/)=',     # compound assignment: x += 1
    r'^\w+\s*=\s*\{',           # map init: x = {
    r'^\}',                      # closing brace
    r'^_\s*=>',                  # wildcard match arm: _ => ...
    r'^/[^/]+/[gi]*\s*=>',      # regex match arm: /pattern/ => ...
    r'^\w+:\s*(int|float|str|bool|list|map)\b',  # type annotation: name: str
    r'//\s*→',                   # result comment: // → 42
    r'^\w+\s*[&|^]=',           # bitwise assignment: flags &= ~0b
    r'^\w+\s*[<>]{2}',          # bit shift: x >> 1
    r'^[A-Z]\w+\([^)]*\)\s*[,;/]', # enum variant: Circle(float), ...
    r';\s*//',                     # semicolon + inline comment: x > 1; // ...
]))

_COMMON_WORDS = frozenset(
    'the and for that this with from have will your when they each which their '
    'about into than them been some like then what only just also more here '
    'every where after before other because between can are you all use not '
    'any but how its one two run set new get may put see now way own add '
    'need want give make call take does should would could these those there '
    'first second write read check always never define defines handler runs '
    'sends message user function variable block inside value number result '
    'text command pattern example returns creates allows means same different '
    'above below following built possible declared available suspends until '
    'specified event occurs returned declares persistent survive across covered '
    'depth section'.split()
)

def _looks_like_code(line):
    """Detect Gravitix/code-like lines that are outside ``` blocks."""
    s = line.strip()
    if not s:
        return False
    if not _CODE_RE.search(s):
        return False
    # Post-filter: long lines with many common English words are prose, not code
    words = re.findall(r'[a-zA-Z]{3,}', s)
    if len(words) >= 8 and sum(1 for w in words if w.lower() in _COMMON_WORDS) >= 4:
        return False
    return True


def parse_doc(text):
    """
    Split fullReference into a list of (kind, content) tuples.
    kind = 'code'  → leave as-is (inside ``` blocks or detected as code)
    kind = 'keep'  → leave as-is (blank lines, ---, table separators)
    kind = 'head'  → markdown heading: translate text after #
    kind = 'list'  → list item: translate text after "- "
    kind = 'table' → table row: translate cell text between |
    kind = 'prose' → normal text: translate entirely
    """
    lines = text.split('\n')
    chunks = []
    in_code = False

    for line in lines:
        # Toggle code blocks
        if line.strip().startswith('```'):
            in_code = not in_code
            chunks.append(('code', line))
            continue

        stripped = line.strip()

        # Markdown structural elements break out of broken code blocks
        # (HTML→text conversion can lose < in comparisons, leaving ``` unclosed)
        if in_code:
            if re.match(r'^>\s*\*\*', stripped) or re.match(r'^#{1,3}\s+', stripped):
                in_code = False  # force-close broken code block
            else:
                chunks.append(('code', line))
                continue

        # Empty / separator lines
        if stripped == '' or stripped == '---':
            chunks.append(('keep', line))
            continue

        # Headings: # ## ###
        m = re.match(r'^(#{1,3})\s+(.*)', line)
        if m:
            chunks.append(('head', line))
            continue

        # Table rows: | ... | ... |
        if stripped.startswith('|'):
            # Table separator like | --- | --- |
            if re.match(r'^\|[\s\-|]+\|$', stripped):
                chunks.append(('keep', line))
            else:
                chunks.append(('table', line))
            continue

        # List items: - ...
        if stripped.startswith('- '):
            chunks.append(('list', line))
            continue

        # Detect code-like lines outside ``` blocks
        if _looks_like_code(line):
            chunks.append(('code', line))
            continue

        # Callout markers like > **...**
        if stripped.startswith('> '):
            chunks.append(('prose', line))
            continue

        # Normal prose
        if len(stripped) > 0:
            chunks.append(('prose', line))
        else:
            chunks.append(('keep', line))

    return chunks


def extract_translatable(chunks):
    """Extract strings to translate + their indices in chunks list."""
    items = []  # (chunk_index, original_text, kind)
    for i, (kind, content) in enumerate(chunks):
        if kind == 'head':
            m = re.match(r'^(#{1,3})\s+(.*)', content)
            if m:
                items.append((i, m.group(2), 'head'))
        elif kind == 'list':
            stripped = content.strip()
            if stripped.startswith('- '):
                items.append((i, stripped[2:], 'list'))
        elif kind == 'table':
            # Extract cell text: | cell1 | cell2 |
            cells = [c.strip() for c in content.strip().strip('|').split('|')]
            items.append((i, '|||'.join(cells), 'table'))
        elif kind == 'prose':
            items.append((i, content.strip(), 'prose'))
    return items


def reassemble(chunks, items, translated):
    """Put translated strings back into chunks."""
    for (idx, orig, kind), trans in zip(items, translated):
        old_line = chunks[idx][1]
        if kind == 'head':
            m = re.match(r'^(#{1,3})\s+', old_line)
            prefix = m.group(0) if m else '# '
            chunks[idx] = ('head', prefix + trans)
        elif kind == 'list':
            indent = len(old_line) - len(old_line.lstrip())
            chunks[idx] = ('list', ' ' * indent + '- ' + trans)
        elif kind == 'table':
            cells = trans.split('|||')
            chunks[idx] = ('table', '| ' + ' | '.join(c.strip() for c in cells) + ' |')
        elif kind == 'prose':
            # Preserve leading > for callouts
            if old_line.strip().startswith('> '):
                if not trans.startswith('>'):
                    trans = '> ' + trans
            chunks[idx] = ('prose', trans)

    return '\n'.join(content for _, content in chunks)


# ── Translation with batching ──

def batch_translate(strings, target_lang, retries=3):
    if not strings:
        return strings

    text = SEPARATOR.join(strings)

    # Google Translate limit ~5000 chars; split if needed
    if len(text) > 4500:
        mid = len(strings) // 2
        left = batch_translate(strings[:mid], target_lang, retries)
        right = batch_translate(strings[mid:], target_lang, retries)
        return left + right

    for attempt in range(retries):
        try:
            translator = GoogleTranslator(source='en', target=target_lang)
            result = translator.translate(text)
            if not result:
                return strings

            parts = result.split('|||SEP|||')
            parts = [p.strip() for p in parts]

            if len(parts) != len(strings):
                return _one_by_one(strings, target_lang)

            return parts

        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f'      BATCH ERROR: {e}')
                return strings


def _one_by_one(strings, target_lang):
    results = []
    translator = GoogleTranslator(source='en', target=target_lang)
    for s in strings:
        try:
            r = translator.translate(s)
            results.append(r if r else s)
            time.sleep(0.15)
        except:
            results.append(s)
    return results


# ── Main ──

def process_locale(locale_code, en_ref):
    google_code = get_google_code(locale_code)
    path = os.path.join(LOCALE_DIR, locale_code + '.json')
    if not os.path.exists(path):
        return False

    with open(path, 'r', encoding='utf-8') as f:
        loc = json.load(f)

    current = loc.get('gravitixDocs', {}).get('fullReference', '')

    # Skip if already translated (differs from English)
    if current and current != en_ref:
        print(f'  {locale_code}: already translated, skipping', flush=True)
        return False

    print(f'  {locale_code}: parsing document...', flush=True)
    chunks = parse_doc(en_ref)
    items = extract_translatable(chunks)
    strings = [text for _, text, _ in items]

    print(f'  {locale_code}: {len(strings)} translatable segments → {google_code}', flush=True)

    # Translate in batches
    translated = []
    for i in range(0, len(strings), BATCH_SIZE):
        batch = strings[i:i + BATCH_SIZE]
        result = batch_translate(batch, google_code)
        translated.extend(result)
        done = min(i + BATCH_SIZE, len(strings))
        print(f'    [{done}/{len(strings)}]', flush=True)
        if i + BATCH_SIZE < len(strings):
            time.sleep(0.4)

    # Reassemble
    final = reassemble(chunks, items, translated)

    if 'gravitixDocs' not in loc:
        loc['gravitixDocs'] = {}
    loc['gravitixDocs']['fullReference'] = final

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(loc, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'  {locale_code}: DONE ✓', flush=True)
    return True


def main():
    # Load English reference
    en_path = os.path.join(LOCALE_DIR, 'en.json')
    with open(en_path, 'r', encoding='utf-8') as f:
        en = json.load(f)

    en_ref = en.get('gravitixDocs', {}).get('fullReference', '')
    if not en_ref:
        print('ERROR: en.json has no gravitixDocs.fullReference')
        sys.exit(1)

    print(f'English reference: {len(en_ref)} chars')
    chunks = parse_doc(en_ref)
    items = extract_translatable(chunks)
    print(f'Translatable segments: {len(items)}')
    print(f'Code/markup segments (kept as-is): {len(chunks) - len(items)}')
    print()

    # Optional: translate only specific locale(s) via CLI args
    # Usage: python3 translate_docs.py ru es de
    targets = sys.argv[1:] if len(sys.argv) > 1 else None

    if targets:
        codes = targets
    else:
        codes = list(PRIORITY)
        all_files = [f.replace('.json', '') for f in os.listdir(LOCALE_DIR)
                     if f.endswith('.json') and f != 'en.json']
        for c in all_files:
            if c not in codes:
                codes.append(c)

    done = 0
    for code in codes:
        try:
            if process_locale(code, en_ref):
                done += 1
        except Exception as e:
            print(f'  ERROR {code}: {e}')

    print(f'\nDONE: {done} locales translated')


if __name__ == '__main__':
    main()
