const FilePolicy = (() => {
    const ALLOWED = [
        { ext: 'jpg', mime: 'image/jpeg' },
        { ext: 'jpeg', mime: 'image/jpeg' },
        { ext: 'jfif', mime: 'image/jpeg' },
        { ext: 'png', mime: 'image/png' },
        { ext: 'webp', mime: 'image/webp' },
        { ext: 'gif', mime: 'image/gif' },
        { ext: 'bmp', mime: 'image/bmp' },
        { ext: 'pdf', mime: 'application/pdf' },
        { ext: 'txt', mime: 'text/plain' },
        { ext: 'md', mime: 'text/plain' },
        { ext: 'csv', mime: 'text/plain' },
        { ext: 'log', mime: 'text/plain' },
        { ext: 'json', mime: 'application/json' },
    ];

    const DANGEROUS = [
        'php', 'php3', 'php4', 'php5', 'phtml', 'asp', 'aspx', 'jsp', 'cgi', 'pl', 'py', 'rb',
        'sh', 'bash', 'exe', 'dll', 'bat', 'cmd', 'ps1', 'vbs', 'com', 'scr', 'jar', 'msi',
        'app', 'dylib', 'so', 'bin', 'run',
    ];

    function extOf(name) {
        const base = (name || '').split(/[\\/]/).pop();
        const dot = base.lastIndexOf('.');
        return dot >= 0 && dot + 1 < base.length ? base.slice(dot + 1).toLowerCase() : '';
    }

    function isAllowed(name) {
        const e = extOf(name);
        return !!e && ALLOWED.some((a) => a.ext === e);
    }

    function hasDangerousDoubleExtension(name) {
        const base = (name || '').split(/[\\/]/).pop();
        const parts = base.split('.');
        if (parts.length <= 2) return false;
        return parts.slice(1).some((p) => DANGEROUS.indexOf(p.toLowerCase()) !== -1);
    }

    function list() {
        return ALLOWED.map((a) => a.ext).filter((e, i, a) => a.indexOf(e) === i).join(', ');
    }

    function accept() {
        const mimes = ALLOWED.map((a) => a.mime).filter((m, i, a) => a.indexOf(m) === i);
        const exts = ALLOWED.map((a) => '.' + a.ext);
        return mimes.concat(exts).join(',');
    }

    return { isAllowed, hasDangerousDoubleExtension, extOf, list, accept };
})();
