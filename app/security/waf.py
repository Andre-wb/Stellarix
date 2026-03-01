import re
import ipaddress
import secrets
import logging
import json
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple, Optional, Any
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# WAF Rule Definitions (Signatures)
# ----------------------------------------------------------------------

class WAFRule:
    """
    Represents a single WAF rule with a compiled regex pattern and metadata.
    """
    def __init__(self, rule_id: str, pattern: str, severity: str = "medium",
                 description: str = "", action: str = "block"):
        self.rule_id = rule_id
        try:
            self.pattern = re.compile(pattern, re.IGNORECASE)
        except re.error:
            self.pattern = re.compile(r"(?!)", re.IGNORECASE)  # never matches
            logger.error(f"Failed to compile rule {rule_id}: {pattern}")
        self.severity = severity
        self.description = description
        self.action = action
        self.trigger_count = 0
        self.last_triggered: Optional[datetime] = None


class WAFSignature:
    """
    Collection of predefined attack signatures.
    """
    # SQL Injection patterns (regex, short description)
    SQL_INJECTION_PATTERNS = [
        (r"(\b(SELECT|UNION|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|EXECUTE)\b.*\b(FROM|INTO|SET|WHERE|VALUES)\b)", "SQL Injection"),
        (r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)", "SQL Boolean Injection"),
        (r"(\b(SLEEP|WAITFOR|BENCHMARK)\(.*\))", "SQL Time-based Injection"),
        (r"(\b(UNION\s+ALL\s+SELECT)\b)", "Union SQL Injection"),
        (r"(\b(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)\b)", "SQL File Operations"),
        (r"(--|#|/\*|\*/|;)", "SQL Comment Injection"),
        (r"(\b(XPATH|CONCAT|GROUP_CONCAT)\b.*\()", "SQL Function Injection"),
        (r"(\b(CASE|WHEN|THEN|END)\b.*\b(WHEN|THEN)\b)", "SQL Conditional Injection"),
        (r"(\b(CHAR|ASCII|BIN|HEX)\b.*\()", "SQL Encoding Functions"),
        (r"(\b(IF|ELSE|ENDIF)\b.*\()", "SQL Conditional Functions"),
    ]

    # XSS patterns
    XSS_PATTERNS = [
        (r"(<script.*?>.*?</script>)", "Script Tag XSS"),
        (r"(javascript:)", "JavaScript Protocol XSS"),
        (r"(on\w+\s*=)", "Event Handler XSS"),
        (r"(alert\(.*\))", "Alert XSS"),
        (r"(document\.(cookie|location|domain|referrer))", "Document Object XSS"),
        (r"(window\.(location|open))", "Window Object XSS"),
        (r"(eval\(.*\))", "Eval XSS"),
        (r"(setTimeout|setInterval).*\(.*\)", "Timer XSS"),
        (r"(<iframe.*?>.*?</iframe>)", "IFrame XSS"),
        (r"(<img.*?src.*?=.*?javascript:)", "IMG Tag XSS"),
        (r"(<svg.*?onload.*?=)", "SVG XSS"),
        (r"(<body.*?onload.*?=)", "Body Tag XSS"),
        (r"(<input.*?onfocus.*?=)", "Input Tag XSS"),
        (r"(<marquee.*?onstart.*?=)", "Marquee Tag XSS"),
        (r"(<details.*?ontoggle.*?=)", "Details Tag XSS"),
        (r"(<select.*?onchange.*?=)", "Select Tag XSS"),
    ]

    # Path Traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        (r"(\.\./|\.\.\\)", "Directory Traversal"),
        (r"(/etc/passwd|/etc/shadow|/etc/hosts)", "System File Access"),
        (r"(c:\\windows\\system32\\config\\sam)", "Windows SAM File"),
        (r"(\.\.%2f|\.\.%5c)", "Encoded Directory Traversal"),
        (r"(%00|%0a|%0d)", "Null Byte Injection"),
        (r"(/proc/self/environ|/proc/self/cmdline)", "Proc Filesystem Access"),
        (r"(\.git/|\.svn/|\.hg/)", "Version Control Files"),
        (r"(\.env|\.htaccess|\.htpasswd)", "Configuration Files"),
        (r"(php://filter|zip://|phar://)", "PHP Wrappers"),
        (r"(file://|ftp://|gopher://)", "Dangerous Protocols"),
    ]

    # Command Injection patterns
    COMMAND_INJECTION_PATTERNS = [
        (r"(;\s*(ls|dir|cat|more|less|head|tail|ps|netstat|ifconfig|ipconfig))", "Command Injection"),
        (r"(\|\s*(ls|dir|cat|more|less|head|tail))", "Pipe Command Injection"),
        (r"(&&\s*(ls|dir|cat|more|less|head|tail))", "AND Command Injection"),
        (r"(\|\|\s*(ls|dir|cat|more|less|head|tail))", "OR Command Injection"),
        (r"(\$(\(.*\)|\{.*\}))", "Bash Command Substitution"),
        (r"(`.*`)", "Backtick Command Execution"),
        (r"(wget\s+|curl\s+|nc\s+|ncat\s+|telnet\s+)", "Network Tools"),
        (r"(python\s+|perl\s+|ruby\s+|php\s+)", "Script Execution"),
        (r"(base64\s+-d|base64\s+-decode)", "Base64 Decode Command"),
        (r"(sh\s+-i|bash\s+-i|zsh\s+-i)", "Reverse Shell"),
    ]

    # File Inclusion (LFI/RFI) patterns
    FILE_INCLUSION_PATTERNS = [
        (r"(include\(.*\)|require\(.*\)|include_once\(.*\)|require_once\(.*\))", "File Inclusion"),
        (r"(\.\./\.\./\.\./)", "Multiple Directory Traversal"),
        (r"(http://|https://|ftp://).*(\.php|\.asp|\.aspx|\.jsp)", "Remote File Inclusion"),
        (r"(php://input|data://)", "PHP Stream Wrappers"),
        (r"(expect://|ssh2://)", "Dangerous PHP Wrappers"),
        (r"(\./\./\./)", "Relative Path Traversal"),
    ]

    # SSRF patterns
    SSRF_PATTERNS = [
        (r"(localhost|127\.0\.0\.1|::1|0\.0\.0\.0)", "Localhost Access"),
        (r"(169\.254\.169\.254|metadata\.google\.internal)", "Cloud Metadata"),
        (r"(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+)", "Private IP Range"),
        (r"(file://|gopher://|dict://)", "Dangerous URL Schemes"),
        (r"(admin|internal|backend|management)", "Internal Service Names"),
    ]

    # XXE patterns
    XXE_PATTERNS = [
        (r"(<!DOCTYPE.*\[.*\])", "XML DOCTYPE Declaration"),
        (r"(<!ENTITY.*SYSTEM.*>)", "XML External Entity"),
        (r"(file:///|http://|ftp://).*ENTITY", "External Entity Reference"),
        (r"(XXE|XML External Entity)", "XXE Keyword"),
        (r"(<!ELEMENT|<!ATTLIST)", "XML Schema Elements"),
    ]

    # API Abuse patterns
    API_ABUSE_PATTERNS = [
        (r"(/api/.*(admin|delete|drop|truncate))", "Admin API Abuse"),
        (r"(/v[0-9]+/.*)", "API Version Enumeration"),
        (r"(swagger|openapi|api-docs)", "API Documentation"),
        (r"(\.json|\.xml|\.yaml|\.yml)", "API Data Formats"),
        (r"(limit=1000|limit=9999)", "Large Result Set"),
        (r"(offset=10000|page=1000)", "Deep Pagination"),
    ]

    # Scanner / bot patterns
    SCANNER_PATTERNS = [
        (r"(nmap|nikto|sqlmap|metasploit|nessus|acunetix|w3af|skipfish|burpsuite|zap)", "Security Scanner"),
        (r"(dirb|gobuster|ffuf|wfuzz|dirbuster)", "Directory Brute Force"),
        (r"(wp-admin|wp-login|wp-content)", "WordPress Scanner"),
        (r"(phpmyadmin|adminer|mysql-admin)", "Database Admin Scanner"),
        (r"(\.git/HEAD|\.svn/entries|\.hg/store)", "Version Control Scanner"),
        (r"(robots\.txt|sitemap\.xml|crossdomain\.xml)", "Crawler Directives"),
        (r"(\.DS_Store|Thumbs\.db|desktop\.ini)", "OS Metadata Files"),
    ]

    @classmethod
    def get_all_rules(cls) -> List[WAFRule]:
        """
        Compile all signature patterns into a list of WAFRule objects.
        """
        rules = []
        counter = 1
        for patterns, prefix, severity, action in [
            (cls.SQL_INJECTION_PATTERNS, "SQLI", "critical", "block"),
            (cls.XSS_PATTERNS, "XSS", "high", "block"),
            (cls.PATH_TRAVERSAL_PATTERNS, "PT", "high", "block"),
            (cls.COMMAND_INJECTION_PATTERNS, "CI", "critical", "block"),
            (cls.FILE_INCLUSION_PATTERNS, "FI", "high", "block"),
            (cls.SSRF_PATTERNS, "SSRF", "medium", "alert"),
            (cls.XXE_PATTERNS, "XXE", "high", "block"),
            (cls.API_ABUSE_PATTERNS, "API", "medium", "alert"),
            (cls.SCANNER_PATTERNS, "SCAN", "low", "log"),
        ]:
            for pattern, desc in patterns:
                rules.append(WAFRule(
                    rule_id=f"{prefix}-{counter:03d}",
                    pattern=pattern,
                    severity=severity,
                    description=desc,
                    action=action
                ))
                counter += 1
        return rules


# ----------------------------------------------------------------------
# Core WAF Engine
# ----------------------------------------------------------------------

class WAFEngine:
    """
    Main WAF engine. Performs request analysis, IP black/whitelisting,
    rate limiting, and signature rule matching.
    """
    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.rules = WAFSignature.get_all_rules()
        self.safe_params = set(cfg.get('safe_params', ['csrf_token', '_csrf', 'csrfmiddlewaretoken']))
        self.ip_whitelist: Set[str] = {'127.0.0.1', '::1', 'localhost'}
        self.ip_blacklist: Set[str] = set()
        self.blocked_ips: Dict[str, Dict] = {}
        self.request_history: Dict[str, List[datetime]] = defaultdict(list)

        self.rate_limit_requests = int(cfg.get('rate_limit_requests', 100))
        self.rate_limit_window = int(cfg.get('rate_limit_window', 60))
        self.block_duration = int(cfg.get('block_duration', 3600))
        self.max_content_length = int(cfg.get('max_content_length', 10 * 1024 * 1024))

        self.stats = {
            'total_requests': 0,
            'blocked_requests': 0,
            'rules_triggered': defaultdict(int),
            'ip_blocks': 0,
        }

        for ip in cfg.get('whitelist_ips', []):
            self.ip_whitelist.add(ip)

    # ----- IP check / block methods -----
    def is_ip_blocked(self, ip: str) -> bool:
        """Check if IP is permanently or temporarily blocked."""
        if ip in self.ip_whitelist:
            return False
        if ip in self.ip_blacklist:
            return True
        if ip in self.blocked_ips:
            if self.blocked_ips[ip].get('until', datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
                return True
            del self.blocked_ips[ip]  # expired block
        return False

    def block_ip(self, ip: str, reason: str, duration: Optional[int] = None) -> bool:
        """
        Temporarily block an IP address.
        Returns True if blocked, False if IP is whitelisted.
        """
        if ip in self.ip_whitelist:
            logger.warning(f"Attempt to block whitelisted IP: {ip}")
            return False
        dur = duration or self.block_duration
        self.blocked_ips[ip] = {
            'blocked_at': datetime.now(timezone.utc),
            'until': datetime.now(timezone.utc) + timedelta(seconds=dur),
            'reason': reason,
            'duration': dur
        }
        self.stats['ip_blocks'] += 1
        logger.warning(f"IP blocked: {ip}, reason: {reason}")
        return True

    # ----- Rate limiting -----
    def check_rate_limit(self, ip: str) -> Tuple[bool, Optional[str]]:
        """
        Apply rate limiting for the given IP.
        Returns (True, None) if allowed, otherwise (False, message).
        Automatically blocks IP if limit is exceeded twofold.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=self.rate_limit_window)
        self.request_history[ip] = [ts for ts in self.request_history[ip] if ts > window_start]

        if len(self.request_history[ip]) >= self.rate_limit_requests:
            oldest = min(self.request_history[ip])
            wait = self.rate_limit_window - (now - oldest).total_seconds()
            if len(self.request_history[ip]) >= self.rate_limit_requests * 2:
                self.block_ip(ip, "Rate limit exceeded (double limit)", 1800)
            return False, f"Rate limit exceeded. Try again in {wait:.0f} seconds."

        self.request_history[ip].append(now)
        if len(self.request_history[ip]) > self.rate_limit_requests * 10:
            self.request_history[ip] = self.request_history[ip][-self.rate_limit_requests:]
        return True, None

    # ----- Main request analysis -----
    def analyze_request(self, request_data: Dict) -> Dict[str, Any]:
        """
        Analyze a request dictionary. Returns analysis result containing
        'block' flag, list of findings, matched rule IDs, and client IP.
        """
        findings = []
        should_block = False
        matched_rules = []

        ip = request_data.get('client_ip', 'unknown')

        if self.is_ip_blocked(ip):
            return {'block': True, 'reason': 'IP blocked', 'findings': [{'rule_id': 'IP-BLOCKED', 'severity': 'critical'}]}

        rate_ok, rate_reason = self.check_rate_limit(ip)
        if not rate_ok:
            return {'block': True, 'reason': rate_reason, 'findings': [{'rule_id': 'RATE-LIMIT', 'severity': 'medium'}]}

        # HTTP method validation
        method = request_data.get('method', '').upper()
        if method not in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'}:
            findings.append({'rule_id': 'INVALID-METHOD', 'severity': 'medium', 'description': f'Invalid HTTP method: {method}'})

        # URL length check
        url = request_data.get('url', '')
        if len(url) > 2048:
            findings.append({'rule_id': 'LONG-URL', 'severity': 'low', 'description': f'URL too long: {len(url)} characters'})

        # Header inspection
        headers = request_data.get('headers', {})
        for name, value in headers.items():
            if name.lower() == 'user-agent' and (not value or len(value) < 5):
                findings.append({'rule_id': 'SUSPICIOUS-UA', 'severity': 'low', 'description': 'Suspicious User-Agent'})
            if name.lower() == 'referer' and 'javascript:' in value.lower():
                findings.append({'rule_id': 'XSS-REFERER', 'severity': 'high', 'description': 'XSS in Referer header'})

        # Query parameters
        params = request_data.get('params', {})
        for name, val in params.items():
            values = val if isinstance(val, list) else [val]
            for v in values:
                findings.extend(self._check_parameter(name, str(v)))

        # Request body
        body = request_data.get('body', '')
        if body:
            if len(body) > self.max_content_length:
                findings.append({'rule_id': 'LARGE-BODY', 'severity': 'medium', 'description': f'Request body too large: {len(body)} bytes'})
            else:
                findings.extend(self._check_request_body(body, request_data.get('content_type', '')))

        # URL path
        path = request_data.get('path', '')
        findings.extend(self._check_path(path))

        # Determine blocking based on severity
        for f in findings:
            if f.get('severity') in ('high', 'critical'):
                should_block = True
                matched_rules.append(f['rule_id'])

        self.stats['total_requests'] += 1
        if should_block:
            self.stats['blocked_requests'] += 1
            for rid in matched_rules:
                self.stats['rules_triggered'][rid] += 1

        return {'block': should_block, 'findings': findings, 'matched_rules': matched_rules, 'client_ip': ip}

    # ----- Helper inspection methods -----
    def _check_parameter(self, name: str, value: str) -> List[Dict]:
        """Check a single parameter against all rules."""
        if name.lower() in self.safe_params:
            return []
        res = []
        for rule in self.rules:
            if rule.pattern.search(name) or rule.pattern.search(value):
                res.append({
                    'rule_id': rule.rule_id,
                    'description': f'{rule.description} in parameter {name}',
                    'severity': rule.severity,
                    'value': value[:100]
                })
                rule.trigger_count += 1
                rule.last_triggered = datetime.now(timezone.utc)
        return res

    def _check_request_body(self, body: str, content_type: str) -> List[Dict]:
        """Parse and inspect request body according to Content-Type."""
        findings = []
        parsed = False
        if 'multipart/form-data' in content_type:
            return []

        if 'application/json' in content_type:
            try:
                data = json.loads(body)
                findings.extend(self._check_json_structure(data))
                parsed = True
            except json.JSONDecodeError:
                findings.append({'rule_id': 'INVALID-JSON', 'severity': 'medium', 'description': 'Invalid JSON in request body'})

        elif 'application/x-www-form-urlencoded' in content_type:
            import urllib.parse
            try:
                parsed_data = urllib.parse.parse_qs(body)
                for key, values in parsed_data.items():
                    if key.lower() in self.safe_params:
                        continue
                    for val in values:
                        findings.extend(self._check_parameter(key, val))
                parsed = True
            except Exception:
                pass

        if not parsed:
            # Fallback: treat body as plain text
            for rule in self.rules:
                if rule.pattern.search(body):
                    findings.append({
                        'rule_id': rule.rule_id,
                        'description': f'{rule.description} in request body',
                        'severity': rule.severity,
                        'value': body[:100]
                    })
                    rule.trigger_count += 1
        return findings

    def _check_json_structure(self, data: Any, path: str = "") -> List[Dict]:
        """Recursively traverse JSON structure and inspect keys/values."""
        findings = []
        if isinstance(data, dict):
            for key, value in data.items():
                cur = f"{path}.{key}" if path else key
                findings.extend(self._check_parameter(cur, key))
                if isinstance(value, (dict, list)):
                    findings.extend(self._check_json_structure(value, cur))
                else:
                    findings.extend(self._check_parameter(cur, str(value)))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                cur = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    findings.extend(self._check_json_structure(item, cur))
                else:
                    findings.extend(self._check_parameter(cur, str(item)))
        return findings

    def _check_path(self, path: str) -> List[Dict]:
        """Check URL path for directory traversal, dangerous extensions, etc."""
        findings = []
        if '..' in path or '../' in path or '..\\' in path:
            findings.append({'rule_id': 'PATH-TRAVERSAL', 'severity': 'high', 'description': 'Directory traversal attempt in path'})
        for ext in ('.php', '.asp', '.aspx', '.jsp', '.py', '.pl', '.sh'):
            if path.lower().endswith(ext):
                findings.append({'rule_id': 'DANGEROUS-EXTENSION', 'severity': 'medium', 'description': f'Dangerous file extension: {ext}'})
        if len(path) > 500:
            findings.append({'rule_id': 'LONG-PATH', 'severity': 'low', 'description': f'Path too long: {len(path)} characters'})
        for rule in self.rules:
            if rule.pattern.search(path):
                findings.append({
                    'rule_id': rule.rule_id,
                    'description': f'{rule.description} in URL path',
                    'severity': rule.severity
                })
                rule.trigger_count += 1
        return findings

    # ----- Statistics and cleanup -----
    def get_stats(self) -> Dict:
        """Return current WAF statistics."""
        total = self.stats['total_requests']
        return {
            'total_requests': total,
            'blocked_requests': self.stats['blocked_requests'],
            'block_rate': round(self.stats['blocked_requests'] / total * 100, 2) if total else 0,
            'rules_triggered': dict(self.stats['rules_triggered']),
            'ip_blocks': self.stats['ip_blocks'],
            'blocked_ips_count': len(self.blocked_ips),
            'active_rules': len([r for r in self.rules if r.trigger_count > 0])
        }

    def clear_old_blocks(self):
        """Remove expired temporary IP blocks."""
        now = datetime.now(timezone.utc)
        expired = [ip for ip, info in self.blocked_ips.items() if info.get('until', now) < now]
        for ip in expired:
            del self.blocked_ips[ip]
        if expired:
            logger.info(f"Cleared {len(expired)} expired IP blocks")


# ----------------------------------------------------------------------
# CAPTCHA (with timing‑attack protection)
# ----------------------------------------------------------------------

class WAFCaptcha:
    """
    Simple arithmetic CAPTCHA stored in memory with TTL.
    Uses secrets.compare_digest for answer verification.
    """
    def __init__(self):
        self._challenges: Dict[str, Dict] = {}
        self.ttl = 300  # seconds

    def generate_challenge(self, client_ip: str) -> Dict:
        """Generate a new CAPTCHA challenge for the client."""
        op = secrets.choice(['+', '-', '*'])
        a = secrets.randbelow(10) + 1
        b = secrets.randbelow(10) + 1
        if op == '+':
            answer = str(a + b)
        elif op == '-':
            answer = str(a - b)
        else:
            answer = str(a * b)

        cid = secrets.token_hex(16)
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.ttl)
        self._challenges[cid] = {
            'answer': answer,
            'expires_at': expires,
            'client_ip': client_ip
        }
        return {
            'challenge_id': cid,
            'question': f"What is {a} {op} {b}?",
            'expires_in': self.ttl
        }

    def verify_challenge(self, challenge_id: str, answer: str) -> bool:
        """Verify the answer; challenge is consumed (single-use)."""
        ch = self._challenges.get(challenge_id)
        if not ch or ch['expires_at'] < datetime.now(timezone.utc):
            self._challenges.pop(challenge_id, None)
            return False
        ok = secrets.compare_digest(str(answer).strip(), ch['answer'])
        del self._challenges[challenge_id]
        return ok

    def cleanup_expired(self):
        """Remove expired challenges."""
        now = datetime.now(timezone.utc)
        expired = [cid for cid, ch in self._challenges.items() if ch['expires_at'] < now]
        for cid in expired:
            del self._challenges[cid]


# ----------------------------------------------------------------------
# Unified ASGI Middleware
# ----------------------------------------------------------------------

class WAFMiddleware:
    """
    ASGI middleware that intercepts HTTP requests, analyzes them via WAFEngine,
    and optionally blocks or requests CAPTCHA.
    """
    EXCLUDED_PATHS = {
        '/static/', '/health', '/favicon.ico', '/robots.txt',
        '/waf/stats', '/waf/captcha', '/waf/test'
    }

    def __init__(self, app, waf_engine: WAFEngine):
        self.app = app
        self.waf = waf_engine
        self.captcha = WAFCaptcha()
        self._cleanup_started = False

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            # WebSocket и другие не-HTTP соединения пропускаем без проверки
            await self.app(scope, receive, send)
            return

        # Запускаем фоновую задачу очистки один раз при первом запросе
        if not self._cleanup_started:
            asyncio.create_task(self._cleanup_loop())
            self._cleanup_started = True

        # ── Читаем тело запроса ЗДЕСЬ, до передачи в _build_request ─────────
        # ВАЖНО: ASGI receive() — это одноразовый генератор.
        # Если мы его вызовем в _build_request, а потом передадим оригинальный
        # receive дальше по стеку — BaseHTTPMiddleware (LoggingMiddleware, CSRFMiddleware
        # и т.д.) получит пустое тело и зависнет на 10 секунд ожидая disconnect.
        # Решение: читаем тело сами, потом создаём replay_receive — заглушку,
        # которая всегда возвращает то же тело при вызове из downstream-обработчиков.
        body_bytes = b''
        method = scope.get('method', 'GET')

        if method in ('POST', 'PUT', 'PATCH'):
            more_body = True
            while more_body:
                message = await receive()
                msg_type = message.get('type', '')
                if msg_type == 'http.request':
                    # Накапливаем тело по кускам (chunked transfer)
                    body_bytes += message.get('body', b'')
                    more_body = message.get('more_body', False)  # False = последний кусок
                elif msg_type == 'http.disconnect':
                    # Клиент отключился до конца отправки тела — прерываем
                    break
                else:
                    # Неизвестный тип сообщения — прерываем чтобы не зависнуть
                    break

        # Создаём replay_receive — closure, возвращающий сохранённое тело.
        # BaseHTTPMiddleware вызовет его один раз чтобы получить тело запроса.
        # Все последующие вызовы (например ожидание http.disconnect) форвардируем
        # в оригинальный receive, но только после того как тело было отдано.
        _body_sent = False

        async def replay_receive():
            nonlocal _body_sent
            if not _body_sent:
                # Первый вызов: отдаём сохранённое тело
                _body_sent = True
                return {
                    'type':      'http.request',
                    'body':      body_bytes,
                    'more_body': False,  # тело полностью, одним куском
                }
            # Последующие вызовы: форвардируем в оригинальный receive
            # (например BaseHTTPMiddleware ждёт http.disconnect после отправки ответа)
            return await receive()

        # Строим словарь для анализа WAF (путь, заголовки, тело и т.д.)
        request = self._build_request_from_scope(scope, body_bytes)

        # Пути из EXCLUDED_PATHS пропускаем без проверки
        if self._is_excluded(request['path']):
            await self.app(scope, replay_receive, send)  # ← replay_receive, не receive!
            return

        # Анализируем запрос через движок WAF
        analysis = self.waf.analyze_request(request)
        if analysis['block']:
            await self._send_blocked(scope, send, analysis, request)
            return

        # Проверяем CAPTCHA если клиент передал заголовки
        if 'x-captcha-id' in request['headers'] and 'x-captcha-answer' in request['headers']:
            cid = request['headers']['x-captcha-id']
            ans = request['headers']['x-captcha-answer']
            if not self.captcha.verify_challenge(cid, ans):
                await self._send_captcha_required(send)
                return

        # Всё чисто — передаём запрос дальше по стеку С replay_receive
        await self.app(scope, replay_receive, send)

    def _build_request_from_scope(self, scope, body_bytes: bytes) -> Dict:
        """
        Строит словарь запроса из ASGI scope и уже прочитанных байт тела.

        Тело читается в __call__ ДО вызова этого метода, чтобы после анализа
        его можно было передать дальше через replay_receive.

        Раньше: async def _build_request(self, scope, receive) — читал тело сам
        и тело терялось для downstream-обработчиков (главный баг ~10s зависания).

        Теперь: синхронный метод, принимает уже прочитанные bytes.
        """
        from urllib.parse import parse_qs

        client_ip = self._get_client_ip(scope)              # IP клиента
        method    = scope.get('method', 'GET')              # HTTP-метод
        path      = scope.get('path', '/')                  # URL path
        headers   = {                                       # заголовки → dict
            k.decode('latin-1').lower(): v.decode('latin-1')
            for k, v in scope.get('headers', [])
        }
        qs  = scope.get('query_string', b'').decode()       # query string
        url = path + ('?' + qs if qs else '')               # полный URL

        return {
            'client_ip':    client_ip,
            'method':       method,
            'path':         path,
            'url':          url,
            'headers':      headers,
            'params':       parse_qs(qs),                   # dict[str, list[str]]
            'content_type': headers.get('content-type', ''),
            # Тело уже прочитано в __call__ и передано сюда как bytes
            'body': body_bytes.decode('utf-8', errors='ignore') if body_bytes else '',
        }

    def _get_client_ip(self, scope) -> str:
        """Extract real client IP from headers or connection info."""
        client = scope.get('client')
        if client:
            return client[0]
        headers = {k.decode().lower(): v.decode() for k, v in scope.get('headers', [])}
        for h in ('x-forwarded-for', 'x-real-ip', 'cf-connecting-ip'):
            if h in headers:
                ip = headers[h].split(',')[0].strip()
                try:
                    ipaddress.ip_address(ip)
                    return ip
                except ValueError:
                    pass
        return 'unknown'

    def _is_excluded(self, path: str) -> bool:
        """Check if path is excluded from WAF inspection."""
        return any(path.startswith(ex) for ex in self.EXCLUDED_PATHS)

    async def _send_blocked(self, scope, send, analysis: Dict, req: Dict):
        """Send HTTP 403 response with violation details."""
        findings = analysis.get('findings', [])
        critical = [f for f in findings if f.get('severity') in ('high', 'critical')][:3]
        body = json.dumps({
            'error': 'Request blocked by WAF',
            'request_id': secrets.token_hex(8),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'client_ip': req.get('client_ip'),
            'violations': [{'rule_id': f['rule_id'], 'description': f.get('description'), 'severity': f['severity']} for f in critical]
        }, ensure_ascii=False).encode()
        await send({
            'type': 'http.response.start',
            'status': 403,
            'headers': [
                (b'content-type', b'application/json'),
                (b'x-waf-blocked', b'true')
            ]
        })
        await send({'type': 'http.response.body', 'body': body})
        logger.warning(f"WAF blocked {req['method']} {req['path']} from {req['client_ip']} — {[f['rule_id'] for f in critical]}")

    async def _send_captcha_required(self, send):
        """Send HTTP 429 response indicating CAPTCHA is required."""
        body = json.dumps({
            'error': 'CAPTCHA verification required',
            'message': 'Please solve the CAPTCHA to continue',
            'retry_after': 30
        }).encode()
        await send({
            'type': 'http.response.start',
            'status': 429,
            'headers': [(b'content-type', b'application/json'), (b'x-waf-captcha-required', b'true')]
        })
        await send({'type': 'http.response.body', 'body': body})

    async def _cleanup_loop(self):
        """Background task to remove expired blocks and CAPTCHAs."""
        while True:
            try:
                self.waf.clear_old_blocks()
                self.captcha.cleanup_expired()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(300)


# ----------------------------------------------------------------------
# FastAPI Dependencies
# ----------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_waf_engine() -> WAFEngine:
    """Create and cache a singleton WAFEngine instance."""
    return WAFEngine()

@lru_cache(maxsize=1)
def get_waf_manager() -> 'WAFManager':
    """Create and cache a singleton WAFManager instance."""
    from .waf import WAFManager  # avoid circular import
    return WAFManager(get_waf_engine())


# ----------------------------------------------------------------------
# WAF Management API Routes
# ----------------------------------------------------------------------

waf_router = APIRouter(prefix="/waf", tags=["WAF"])

@waf_router.get("/stats")
async def waf_stats(waf: WAFEngine = Depends(get_waf_engine)):
    return JSONResponse(waf.get_stats())

@waf_router.get("/rules")
async def waf_rules(waf: WAFEngine = Depends(get_waf_engine)):
    rules = [
        {
            'id': r.rule_id,
            'description': r.description,
            'severity': r.severity,
            'action': r.action,
            'trigger_count': r.trigger_count,
            'last_triggered': r.last_triggered.isoformat() if r.last_triggered else None
        }
        for r in waf.rules
    ]
    return JSONResponse({'rules': rules, 'total': len(rules)})

@waf_router.get("/blocked-ips")
async def blocked_ips(manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse({'blocked_ips': manager.get_blocked_ips()})

@waf_router.post("/block-ip")
async def block_ip(ip: str, reason: str = "Manual block", duration: int = 3600,
                   manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse(manager.block_ip(ip, reason, duration))

@waf_router.post("/unblock-ip")
async def unblock_ip(ip: str, manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse(manager.unblock_ip(ip))

@waf_router.get("/whitelist")
async def whitelist(manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse({'whitelist': manager.get_whitelist()})

@waf_router.post("/whitelist/add")
async def whitelist_add(ip: str, manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse(manager.add_whitelist_ip(ip))

@waf_router.delete("/whitelist/remove")
async def whitelist_remove(ip: str, manager: 'WAFManager' = Depends(get_waf_manager)):
    return JSONResponse(manager.remove_whitelist_ip(ip))

@waf_router.post("/captcha/generate")
async def generate_captcha(request: Request):
    client_ip = request.client.host if request.client else 'unknown'
    captcha = WAFCaptcha()
    challenge = captcha.generate_challenge(client_ip)
    return JSONResponse({'success': True, 'challenge': challenge})

@waf_router.get("/test")
async def test_waf(request: Request):
    return JSONResponse({'status': 'ok', 'client_ip': request.client.host if request.client else 'unknown'})


# ----------------------------------------------------------------------
# WAF Setup Function for FastAPI Application
# ----------------------------------------------------------------------

def setup_waf(app, config: Optional[Dict] = None) -> WAFEngine:
    """
    Initialize WAF, attach middleware and management routes to a FastAPI app.
    Returns the WAFEngine instance.
    """
    waf_engine = WAFEngine(config)
    app.add_middleware(WAFMiddleware, waf_engine=waf_engine)
    app.include_router(waf_router)

    @app.exception_handler(HTTPException)
    async def waf_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 403:
            return JSONResponse(
                status_code=403,
                content={'error': 'Access denied', 'message': exc.detail},
                headers={'X-WAF-Protected': 'true'}
            )
        return JSONResponse(status_code=exc.status_code, content={'error': exc.detail})

    logger.info("WAF successfully initialized")
    return waf_engine


# ----------------------------------------------------------------------
# WAF Manager (used by API routes)
# ----------------------------------------------------------------------

class WAFManager:
    """
    Provides administrative operations for the WAF (block/unblock IP,
    manage whitelist, retrieve statistics).
    """
    def __init__(self, waf_engine: WAFEngine):
        self.waf = waf_engine

    def block_ip(self, ip: str, reason: str, duration: int = 3600) -> Dict:
        success = self.waf.block_ip(ip, reason, duration)
        return {'success': success, 'ip': ip, 'reason': reason, 'duration': duration}

    def unblock_ip(self, ip: str) -> Dict:
        if ip in self.waf.blocked_ips:
            del self.waf.blocked_ips[ip]
            return {'success': True, 'ip': ip, 'message': 'IP unblocked'}
        return {'success': False, 'ip': ip, 'message': 'IP not found'}

    def get_blocked_ips(self) -> List[Dict]:
        return [
            {
                'ip': ip,
                'blocked_at': info.get('blocked_at').isoformat() if info.get('blocked_at') else None,
                'blocked_until': info.get('until').isoformat() if info.get('until') else None,
                'reason': info.get('reason', 'unknown'),
                'duration': info.get('duration', 0)
            }
            for ip, info in self.waf.blocked_ips.items()
        ]

    def add_whitelist_ip(self, ip: str) -> Dict:
        try:
            ipaddress.ip_address(ip)
            self.waf.ip_whitelist.add(ip)
            return {'success': True, 'ip': ip, 'message': 'IP added to whitelist'}
        except ValueError:
            return {'success': False, 'ip': ip, 'message': 'Invalid IP format'}

    def remove_whitelist_ip(self, ip: str) -> Dict:
        if ip in self.waf.ip_whitelist:
            self.waf.ip_whitelist.remove(ip)
            return {'success': True, 'ip': ip, 'message': 'IP removed from whitelist'}
        return {'success': False, 'ip': ip, 'message': 'IP not found in whitelist'}

    def get_whitelist(self) -> List[str]:
        return list(self.waf.ip_whitelist)

# ----------------------------------------------------------------------
# Global WAF engine instance for dependency injection
# ----------------------------------------------------------------------

_waf_engine: Optional[WAFEngine] = None

def init_waf_engine(config: Optional[Dict] = None) -> WAFEngine:
    """
    Initialize the global WAF engine (should be called once at startup).
    """
    global _waf_engine
    _waf_engine = WAFEngine(config)
    return _waf_engine

def get_waf_engine() -> WAFEngine:
    """
    FastAPI dependency that returns the global WAF engine.
    """
    if _waf_engine is None:
        raise RuntimeError("WAFEngine not initialized. Call init_waf_engine() first.")
    return _waf_engine