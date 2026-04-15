#!/usr/bin/env python3
"""
Convert GX_SECTIONS in data.js to use _t() calls for i18n.

This script:
1. Changes `const GX_SECTIONS = {` → `function _gxSections() { return {`
2. Wraps all translatable text in ${_t('key', 'fallback')} calls
3. Reuses existing gravitixDocs.* keys where possible
4. Generates new keys for content without existing keys
5. Outputs locale entries (en + ru) for new keys
"""
import re
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(BASE, 'static', 'js', 'ide-docs', 'data.js')
EN_JSON = os.path.join(BASE, 'static', 'locales', 'en.json')
RU_JSON = os.path.join(BASE, 'static', 'locales', 'ru.json')

# ── Existing gravitixDocs.* key map: English text → key ──
# Only for EXACT matches of h1/h2/p text
EXISTING_KEYS = {
    # Headings (h1) — from TOC labels or explicit keys
    'Gravitix Language Reference': 'gravitixDocs.title',
    'Quick Start': 'gravitixDocs.quickStart',
    'Syntax at a Glance': 'gravitixDocs.syntaxAtGlance',
    'Variables': 'gravitixDocs.variables',
    'Types': 'gravitixDocs.types',
    'Operators': 'gravitixDocs.operators',
    'Strings': 'gravitixDocs.strings',
    'Loops': 'gravitixDocs.loops',
    'Functions': 'gravitixDocs.functions',
    'Event Handlers': 'gravitixDocs.eventHandlers',
    'Guard Clauses': 'gravitixDocs.guardClauses',
    'Context Object': 'gravitixDocs.contextObject',
    'State Management': 'gravitixDocs.stateManagement',
    'Scheduling': 'gravitixDocs.scheduling',
    'Error Handling': 'gravitixDocs.errorHandling',
    'Complex Numbers': 'gravitixDocs.complexNumbers',
    'Core Mathematics': 'gravitixDocs.coreMath',
    'Complex Analysis': 'gravitixDocs.complexAnalysis',
    'Calculus': 'gravitixDocs.calculus',
    'Linear Algebra': 'gravitixDocs.linearAlgebra',
    'Number Theory': 'gravitixDocs.numberTheory',
    'Statistics': 'gravitixDocs.statistics',
    'Special Functions': 'gravitixDocs.specialFunctions',
    'Built-in Functions': 'gravitixDocs.builtinFunctions',
    'Complete Examples': 'gravitixDocs.completeExamples',
    'Best Practices': 'gravitixDocs.bestPractices',

    # Sub-headings (h2)
    'Declaring variables': 'gravitixDocs.declaringVariables',
    'Explicit type annotations': 'gravitixDocs.explicitTypes',
    'Updating variables': 'gravitixDocs.updatingVariables',
    'Naming rules': 'gravitixDocs.namingRules',
    'Scope': 'gravitixDocs.scope',
    'Primitive types': 'gravitixDocs.primitiveTypes',
    'Arithmetic operators': 'gravitixDocs.arithmeticOps',
    'Assignment operators': 'gravitixDocs.assignmentOps',
    'Comparison operators': 'gravitixDocs.comparisonOps',
    'Logical operators': 'gravitixDocs.logicalOps',
    'String concatenation': 'gravitixDocs.stringConcat',
    'Operator precedence': 'gravitixDocs.operatorPrecedence',
    'String literals': 'gravitixDocs.stringLiterals',
    'String interpolation': 'gravitixDocs.stringInterpolation',
    'Escape sequences': 'gravitixDocs.escapeSequences',
    'Multiline strings': 'gravitixDocs.multilineStrings',
    'Your first bot': 'gravitixDocs.yourFirstBot',
    'Running the bot': 'gravitixDocs.runningTheBot',
    'Anatomy of a handler': 'gravitixDocs.anatomyOfHandler',
    'Parameters': 'gravitixDocs.parameters',
    'Return values': 'gravitixDocs.returnValues',
    'Calling functions': 'gravitixDocs.callingFunctions',
    'Recursion': 'gravitixDocs.recursion',
    'Command handlers': 'gravitixDocs.commandHandlers',
    'Message handler': 'gravitixDocs.messageHandler',
    'All event types': 'gravitixDocs.allEventTypes',
    'User information': 'gravitixDocs.userInfo',
    'Chat information': 'gravitixDocs.chatInfo',
    'Message information': 'gravitixDocs.messageInfo',
    'Declaring state': 'gravitixDocs.declaringState',
    'Reading state': 'gravitixDocs.readingState',
    'Writing state': 'gravitixDocs.writingState',
    'Declaring a flow': 'gravitixDocs.declaringFlow',
    'Triggering a flow': 'gravitixDocs.triggeringFlow',
    'Multi-step form': 'gravitixDocs.multiStepForm',
    'Mathematical constants': 'gravitixDocs.mathConstants',
    'Trigonometric functions': 'gravitixDocs.trigFunctions',
    'Derivatives': 'gravitixDocs.derivatives',
    'Numerical integration': 'gravitixDocs.numericalIntegration',
    'Vectors': 'gravitixDocs.vectors',
    'Matrices': 'gravitixDocs.matrices',
    'Descriptive statistics': 'gravitixDocs.descriptiveStats',
    'Linear regression': 'gravitixDocs.linearRegression',
    'String functions': 'gravitixDocs.stringFunctions',
    'Math functions': 'gravitixDocs.mathFunctions',
    'List functions': 'gravitixDocs.listFunctions',
    'Type conversion': 'gravitixDocs.typeConversion',
    'Extended math': 'gravitixDocs.extendedMath',
    'Type inspection': 'gravitixDocs.typeInspection',
    'Environment variables': 'gravitixDocs.envVars',
    'Debug output': 'gravitixDocs.debugOutput',
    'Time functions': 'gravitixDocs.timeFunctions',
}

# Descriptions (first <p> after <h1>) — from existing *Desc keys
EXISTING_DESC_KEYS = {
    'intro': 'gravitixDocs.introDesc',
    'quickstart': 'gravitixDocs.quickStartDesc',
    'syntax': 'gravitixDocs.syntaxDesc',
    'variables': None,  # no exact desc key
    'types': 'gravitixDocs.typesDesc',
    'operators': 'gravitixDocs.operatorsDesc',
    'strings': 'gravitixDocs.stringsDesc',
    'if': None,
    'loops': None,
    'match': 'gravitixDocs.matchDesc',
    'functions': 'gravitixDocs.functionsDesc',
    'handlers': 'gravitixDocs.eventHandlersDesc',
    'guard': 'gravitixDocs.guardDesc',
    'ctx': 'gravitixDocs.contextDesc',
    'state': 'gravitixDocs.stateDesc',
    'flows': 'gravitixDocs.flowsDesc',
    'emit': 'gravitixDocs.emitDesc',
    'schedule': 'gravitixDocs.schedulingDesc',
    'pipe': 'gravitixDocs.pipeDesc',
    'error': 'gravitixDocs.errorDesc',
    'structs': 'gravitixDocs.structsDesc',
    'math_core': 'gravitixDocs.mathDesc',
    'math_complex': 'gravitixDocs.complexDesc',
    'math_calculus': 'gravitixDocs.calculusDesc',
    'math_linalg': 'gravitixDocs.linearAlgebraDesc',
    'math_numth': 'gravitixDocs.numberTheoryDesc',
    'math_stats': 'gravitixDocs.statisticsDesc',
    'math_special': 'gravitixDocs.specialDesc',
    'math_transforms': 'gravitixDocs.fftDesc',
    'builtins': None,
    'examples': None,
    'bestpractices': None,
    'complex_type': 'gravitixDocs.complexDesc',
    'bitwise': None,
}


def escape_for_template(s):
    """Escape text for use inside JS template literal _t() call."""
    return s.replace('\\', '\\\\').replace("'", "\\'").replace('`', '\\`')


def escape_for_t(s):
    """Escape text for _t('key', 'THIS_PART')."""
    return s.replace("'", "\\'")


class GxDocsConverter:
    def __init__(self):
        self.new_keys_en = {}  # key -> English text
        self.key_counter = {}  # section -> counter
        self.current_section = ''
        self.in_pre = False
        self.first_p_after_h1 = False

    def next_key(self, section, prefix):
        """Generate next key like gxd.intro.p1, gxd.intro.p2, etc."""
        k = f'{section}_{prefix}'
        self.key_counter[k] = self.key_counter.get(k, 0) + 1
        key = f'gxd.{section}.{prefix}{self.key_counter[k]}'
        return key

    def wrap_t(self, key, text):
        """Create ${_t('key', 'text')} wrapper."""
        safe = escape_for_t(text)
        return f"${{_t('{key}', '{safe}')}}"

    def find_or_create_key(self, text, section, prefix):
        """Find existing key or create a new one."""
        plain = re.sub(r'<[^>]+>', '', text).strip()
        if plain in EXISTING_KEYS:
            return EXISTING_KEYS[plain]
        key = self.next_key(section, prefix)
        self.new_keys_en[key] = text
        return key

    def process_line(self, line, section):
        """Process a single line, wrapping translatable text in _t()."""
        stripped = line.strip()

        # Track <pre> blocks
        if '<pre class="gxd-code-raw">' in stripped:
            self.in_pre = True
            # If pre is on one line (contains </pre>), don't mark
            if '</pre>' in stripped:
                return self._process_code_line_full(line, section)
        if '</pre>' in stripped:
            result = self._process_pre_line(line, section)
            self.in_pre = False
            return result
        if self.in_pre:
            return self._process_pre_line(line, section)

        # <h1>text</h1>
        m = re.match(r'^(\s*)<h1>(.*?)</h1>\s*$', line)
        if m:
            indent, text = m.group(1), m.group(2)
            self.first_p_after_h1 = True
            key = self.find_or_create_key(text, section, 'h')
            return f'{indent}<h1>{self.wrap_t(key, text)}</h1>\n'

        # <h2>text</h2>
        m = re.match(r'^(\s*)<h2>(.*?)</h2>\s*$', line)
        if m:
            indent, text = m.group(1), m.group(2)
            key = self.find_or_create_key(text, section, 'h')
            return f'{indent}<h2>{self.wrap_t(key, text)}</h2>\n'

        # <p> or <p class="...">
        m = re.match(r'^(\s*)<p(\s+class="[^"]*")?>(.*?)</p>\s*$', line)
        if m:
            indent, cls, text = m.group(1), m.group(2) or '', m.group(3)
            # Use existing desc key for first <p> after <h1>
            if self.first_p_after_h1:
                self.first_p_after_h1 = False
                desc_key = EXISTING_DESC_KEYS.get(section)
                if desc_key:
                    key = desc_key
                else:
                    key = self.next_key(section, 'p')
                    self.new_keys_en[key] = text
            else:
                key = self.find_or_create_key(text, section, 'p')
            return f'{indent}<p{cls}>{self.wrap_t(key, text)}</p>\n'

        # <li> items
        m = re.match(r'^(\s*)<li>(.*?)</li>\s*$', line)
        if m:
            indent, text = m.group(1), m.group(2)
            key = self.find_or_create_key(text, section, 'li')
            return f'{indent}<li>{self.wrap_t(key, text)}</li>\n'

        # Table <span> with text (not code)
        # Pattern: <span>text</span>
        def replace_span(m):
            text = m.group(1)
            if not text.strip() or text.strip() in ('—', ''):
                return m.group(0)
            # Skip purely numeric/symbolic content
            if re.match(r'^[\d\.\-\s×,+−→≈=()]+$', text.strip()):
                return m.group(0)
            key = self.find_or_create_key(text.strip(), section, 'td')
            return f'<span>{self.wrap_t(key, text)}</span>'

        if '<div class="gxd-type-row">' in stripped and '<span>' in stripped:
            line = re.sub(r'<span>([^<]+?)</span>', replace_span, line)
            return line

        # Callout title
        m = re.match(r'^(\s*)<div class="gxd-callout-title">(.*?)</div>\s*$', line)
        if m:
            indent, text = m.group(1), m.group(2)
            key = self.next_key(section, 'ct')
            self.new_keys_en[key] = text
            return f'{indent}<div class="gxd-callout-title">{self.wrap_t(key, text)}</div>\n'

        return line

    def _process_pre_line(self, line, section):
        """Process a line inside a <pre> block — translate comments."""
        # Match // comment at end of line or standalone
        # But NOT URLs (//example.com) or // inside strings
        m = re.match(r'^(.*?)(\s*//\s+)(.*?)(\s*)$', line)
        if m:
            code, slashes, comment, trail = m.groups()
            # Skip if comment is just a value like "→ 5" or "13"
            if re.match(r'^[\d\.\-\s→≈,()]+$', comment.strip()):
                return line
            # Skip if it looks like a formula/code result
            if comment.strip().startswith('→') or comment.strip().startswith('='):
                return line
            # Skip short value comments
            if len(comment.strip()) < 5:
                return line
            key = self.next_key(section, 'cc')
            self.new_keys_en[key] = comment.strip()
            wrapped = self.wrap_t(key, comment.strip())
            return f'{code}{slashes}{wrapped}{trail}\n'
        return line

    def _process_code_line_full(self, line, section):
        """Process a line that has both <pre> and </pre> (single-line code)."""
        return line

    def convert(self):
        with open(DATA_JS, 'r') as f:
            content = f.read()

        lines = content.split('\n')
        output = []
        self.current_section = ''

        for i, line in enumerate(lines):
            # Detect section start: "sectionName: `"
            m = re.match(r"^(\w+):\s*`\s*$", line.strip())
            if m:
                self.current_section = m.group(1)
                self.in_pre = False
                self.first_p_after_h1 = False
                self.key_counter = {}

            # Convert const to function
            if line.strip() == 'const GX_SECTIONS = {':
                output.append(line.replace('const GX_SECTIONS = {', 'function _gxSections() { return {'))
                continue

            # Process translatable content
            if self.current_section:
                processed = self.process_line(line + '\n', self.current_section)
                output.append(processed.rstrip('\n'))
            else:
                output.append(line)

        # Join and fix the closing
        result = '\n'.join(output)
        # Change the closing }; to }; }
        # Find the LAST }; in the file
        last_close = result.rfind('};')
        if last_close > 0:
            result = result[:last_close] + '}; }' + result[last_close+2:]

        # Write output
        with open(DATA_JS, 'w') as f:
            f.write(result)

        print(f"Converted data.js — {len(self.new_keys_en)} new keys generated")
        return self.new_keys_en


def update_locales(new_keys):
    """Add new keys to en.json and ru.json."""
    # Read existing locales
    with open(EN_JSON, 'r') as f:
        en = json.load(f)
    with open(RU_JSON, 'r') as f:
        ru = json.load(f)

    # Add new keys under gxd namespace
    if 'gxd' not in en:
        en['gxd'] = {}
    if 'gxd' not in ru:
        ru['gxd'] = {}

    # Group keys by section
    for key, text in sorted(new_keys.items()):
        # key format: gxd.section.typeN
        parts = key.split('.')
        if len(parts) != 3:
            continue
        _, section, field = parts
        if section not in en['gxd']:
            en['gxd'][section] = {}
        if section not in ru['gxd']:
            ru['gxd'][section] = {}

        # Strip HTML for the JSON value
        clean = text
        en['gxd'][section][field] = clean
        ru['gxd'][section][field] = clean  # English as fallback, translate later

    # Write back
    with open(EN_JSON, 'w') as f:
        json.dump(en, f, indent=2, ensure_ascii=False)
        f.write('\n')
    with open(RU_JSON, 'w') as f:
        json.dump(ru, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"Updated en.json and ru.json with {len(new_keys)} new keys")


if __name__ == '__main__':
    converter = GxDocsConverter()
    new_keys = converter.convert()

    # Print summary of new keys
    print("\n── New keys ──")
    for key, text in sorted(new_keys.items()):
        preview = text[:80] + ('...' if len(text) > 80 else '')
        print(f"  {key}: {preview}")

    update_locales(new_keys)
    print("\nDone!")
