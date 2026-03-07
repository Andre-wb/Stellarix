// static/js/update_viewer.js
// ============================================================================
// Этот скрипт автоматически обновляет ссылку для скачивания изображения
// при изменении src тега <img> в просмотрщике изображений.
// Также добавляет глобальный обработчик клавиши Escape для закрытия
// просмотрщика изображений или оверлея предпросмотра файлов.
// ============================================================================

// Получаем ссылки на элементы просмотрщика
const _ivImg = document.getElementById('image-viewer-img');
const _ivDl  = document.getElementById('image-viewer-download');

// Глобальный обработчик нажатия клавиш
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        // Если открыт просмотрщик изображений, закрываем его
        if (document.getElementById('image-viewer-overlay').classList.contains('show'))
            window.closeImageViewer();
        // Если открыт оверлей предпросмотра файлов, закрываем его
        if (document.getElementById('file-preview-overlay').classList.contains('show'))
            window.cancelFilePreview();
    }
});