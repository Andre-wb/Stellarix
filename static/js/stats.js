// Stellarix — локальная статистика сеансов для дашборда.
// Записи хранятся в localStorage браузера и появляются на дашборде
// сразу после завершения передачи (через событие storage или опрос).
// Формат записи: { at, kind: 'tx'|'rx'|'key', ok: bool, bytes?, ms? }
const StxStats = (() => {
    const KEY = 'stx_stats_v1';
    const LIMIT = 200;

    function load() {
        try {
            const raw = JSON.parse(localStorage.getItem(KEY));
            if (raw && Array.isArray(raw.sessions)) return raw;
        } catch (e) { /* повреждённые данные — начинаем заново */ }
        return { sessions: [] };
    }

    function save(data) {
        try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (e) { /* нет места — молча пропускаем */ }
    }

    function report(session) {
        if (typeof fetch !== 'function') return;
        try {
            fetch('/api/stats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                keepalive: true,
                body: JSON.stringify({
                    kind: session.kind,
                    ok: !!session.ok,
                    bytes: typeof session.bytes === 'number' ? session.bytes : null,
                    ms: typeof session.ms === 'number' ? session.ms : null,
                }),
            }).catch(() => {});
        } catch (e) {}
    }

    return {
        record(session) {
            const data = load();
            data.sessions.push(Object.assign({ at: Date.now() }, session));
            if (data.sessions.length > LIMIT) data.sessions = data.sessions.slice(-LIMIT);
            save(data);
            report(session);
        },
        all() {
            return load().sessions;
        },
        reset() {
            save({ sessions: [] });
        },
    };
})();
