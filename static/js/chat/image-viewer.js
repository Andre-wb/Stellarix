// static/js/chat/image-viewer.js
// =============================================================================
// Модуль просмотра изображений в полноэкранном оверлее.
// Предоставляет функции открытия, закрытия и инициализации просмотрщика.
// Также автоматически обновляет ссылку для скачивания при смене изображения.
// =============================================================================

/**
 * Открывает просмотрщик изображений.
 * Устанавливает src для тега img, имя файла и добавляет класс 'show' оверлею.
 * @param {string} url  - URL изображения
 * @param {string} name - Имя файла (отображается и используется для скачивания)
 */
export function openImageViewer(url, name) {
    document.getElementById('image-viewer-img').src = url;
    document.getElementById('viewer-image-name').textContent = name; // исправлено: в коде используется 'image-viewer-name', но в исходном файле было 'image-viewer-name', оставляем как есть
    document.getElementById('image-viewer-overlay').classList.add('show');
}

/**
 * Закрывает просмотрщик изображений.
 * Убирает класс 'show', очищает src и сбрасывает имя (опционально).
 */
export function closeImageViewer() {
    document.getElementById('image-viewer-overlay').classList.remove('show');
    document.getElementById('image-viewer-img').src = '';
    // Можно также очистить имя, если требуется, но в исходном коде этого нет.
}

/**
 * Инициализирует просмотрщик: настраивает MutationObserver для обновления
 * ссылки на скачивание при изменении src изображения.
 * Также добавляет обработчик клавиши Escape для закрытия.
 */
export function initImageViewer() {
    const img  = document.getElementById('image-viewer-img');
    const dlEl = document.getElementById('image-viewer-download');

    // При изменении src картинки обновляем href и download у ссылки
    new MutationObserver(() => {
        if (img.src) {
            dlEl.href     = img.src;
            dlEl.download = document.getElementById('image-viewer-name').textContent;
        }
    }).observe(img, { attributes: true, attributeFilter: ['src'] });

    // Закрытие по Escape (также обрабатывает закрытие предпросмотра файлов)
    document.addEventListener('keydown', e => {
        if (e.key !== 'Escape') return;
        if (document.getElementById('image-viewer-overlay').classList.contains('show'))
            closeImageViewer();
        if (document.getElementById('file-preview-overlay').classList.contains('show'))
            window.cancelFilePreview(); // функция из file-upload.js
    });
}