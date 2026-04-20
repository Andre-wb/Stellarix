/* Tiny helper — fills #foot-version from /v1/health */
(() => {
    fetch('/v1/health')
        .then(r => r.json())
        .then(d => {
            const el = document.getElementById('foot-version');
            if (el) el.textContent = 'Vortex Controller v' + d.version;
        })
        .catch(() => {});
})();
