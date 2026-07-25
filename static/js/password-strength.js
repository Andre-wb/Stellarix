// Stellarix — индикатор сложности пароля на странице регистрации.
// Полоска под полем пароля заполняется и меняет цвет от красного к зелёному.
(function () {
    var input = document.getElementById('password');
    var bar = document.getElementById('pw-strength-bar');
    if (!input || !bar) return;

    function score(v) {
        if (!v) return 0;
        var s = 0;
        s += Math.min(v.length / 14, 1) * 0.45;           // длина
        if (/[a-zа-яё]/.test(v)) s += 0.12;               // строчные
        if (/[A-ZА-ЯЁ]/.test(v)) s += 0.13;               // заглавные
        if (/\d/.test(v)) s += 0.15;                      // цифры
        if (/[^\w\sа-яёА-ЯЁ]/.test(v)) s += 0.15;          // спецсимволы
        if (/(.)\1{2,}/.test(v)) s -= 0.1;                // повторы символов
        if (v.length < 8) s = Math.min(s, 0.3);           // короче минимума — всегда «слабый»
        return Math.max(0, Math.min(s, 1));
    }

    function update() {
        var s = score(input.value);
        bar.style.width = Math.round(s * 100) + '%';
        // 0 → красный (hue 0), 1 → зелёный (hue 120)
        bar.style.background = 'hsl(' + Math.round(s * 120) + ', 70%, 45%)';
    }

    input.addEventListener('input', update);
    update();
})();
