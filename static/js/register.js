document.addEventListener('DOMContentLoaded', () => {
    const drop = document.getElementById('avatar-drop');
    const input = document.getElementById('avatar-input');
    const empty = document.getElementById('avatar-empty');
    const hint = document.getElementById('avatar-hint');
    const removeBtn = document.getElementById('avatar-remove');
    if (!drop || !input || typeof Avatar === 'undefined') return;

    const DEFAULT_HINT = 'Перетащите фото сюда или нажмите — по желанию. Иначе будет буква вашего имени.';

    function showPreview(dataUrl) {
        if (dataUrl) {
            drop.style.backgroundImage = 'url("' + dataUrl + '")';
            drop.classList.add('avatar-has-img');
        } else {
            drop.style.backgroundImage = '';
            drop.classList.remove('avatar-has-img');
        }
        if (empty) empty.style.display = dataUrl ? 'none' : '';
        if (removeBtn) removeBtn.hidden = !dataUrl;
        if (hint) hint.textContent = dataUrl ? 'Фото выбрано. Оно уйдёт собеседнику при сопряжении.' : DEFAULT_HINT;
    }

    showPreview(Avatar.getOwn());

    async function accept(file) {
        if (!file) return;
        if (!Avatar.isImageFile(file)) {
            if (hint) hint.textContent = 'Это не изображение — выберите png, jpg или webp.';
            return;
        }
        if (hint) hint.textContent = 'Обрабатываю фото...';
        try {
            const dataUrl = await Avatar.compressFile(file);
            Avatar.setOwn(dataUrl);
            showPreview(dataUrl);
        } catch (err) {
            if (hint) hint.textContent = 'Не удалось обработать фото: ' + err.message;
        }
    }

    drop.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        input.value = '';
        accept(file);
    });

    ['dragenter', 'dragover'].forEach((ev) => {
        drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('dragover'); });
    });
    ['dragleave', 'dragend'].forEach((ev) => {
        drop.addEventListener(ev, () => drop.classList.remove('dragover'));
    });
    drop.addEventListener('drop', (e) => {
        e.preventDefault();
        drop.classList.remove('dragover');
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        accept(file);
    });

    if (removeBtn) {
        removeBtn.addEventListener('click', () => {
            Avatar.clearOwn();
            showPreview('');
        });
    }
});
