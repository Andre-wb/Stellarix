// Stellarix — волна реагирует на звук с микрофона сразу после открытия вкладки.
// Ничего не меняет в логике чата и передачи — только кормит SoundWave.level().
(function () {
    if (typeof SoundWave === 'undefined') return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;

    var started = false;

    function start() {
        if (started) return;
        started = true;

        navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
        }).then(function (stream) {
            var AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return;
            var ctx = new AC();
            var src = ctx.createMediaStreamSource(stream);
            var an = ctx.createAnalyser();
            an.fftSize = 1024;
            src.connect(an);

            // если браузер требует жест пользователя — ждём первый клик/клавишу
            if (ctx.state === 'suspended') {
                var resume = function () { ctx.resume(); };
                document.addEventListener('pointerdown', resume, { once: true });
                document.addEventListener('keydown', resume, { once: true });
            }

            var buf = new Float32Array(an.fftSize);
            (function tick() {
                requestAnimationFrame(tick);
                an.getFloatTimeDomainData(buf);
                var sum = 0;
                for (var i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
                SoundWave.level(Math.sqrt(sum / buf.length));
            })();
        }).catch(function () {
            started = false; // разрешение не дано — волна остаётся фоновой
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
