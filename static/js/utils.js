// static/js/utils.js
// ============================================================================
// Набор вспомогательных утилит, используемых во всём приложении:
// работа с DOM, форматирование дат/времени/размеров, работа с куками,
// универсальная функция запросов к API с CSRF-защитой, управление модалками,
// уведомления и прокрутка.
// ============================================================================

// ----------------------------------------------------------------------------
// DOM helper
// ----------------------------------------------------------------------------
/**
 * Короткая функция для получения элемента по id.
 * @param {string} id - идентификатор элемента
 * @returns {HTMLElement|null}
 */
export const $ = id => document.getElementById(id);

// ----------------------------------------------------------------------------
// Экранирование HTML-спецсимволов (защита от XSS)
// ----------------------------------------------------------------------------
/**
 * Заменяет опасные символы на HTML-сущности.
 * @param {string} str - исходная строка
 * @returns {string} экранированная строка
 */
export function esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ----------------------------------------------------------------------------
// Форматирование времени и даты
// ----------------------------------------------------------------------------
/**
 * Форматирует ISO-дату в локальное время (ЧЧ:ММ).
 * @param {string} iso - дата в ISO формате
 * @returns {string}
 */
export function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Форматирует ISO-дату: если сегодня – "Сегодня", иначе день месяц.
 * @param {string} iso - дата в ISO формате
 * @returns {string}
 */
export function fmtDate(iso) {
    const d = new Date(iso);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return 'Сегодня';
    return d.toLocaleDateString('ru', { day: 'numeric', month: 'long' });
}

/**
 * Форматирует размер в байтах в человекочитаемый вид (Б, КБ, МБ).
 * @param {number} bytes - размер в байтах
 * @returns {string}
 */
export function fmtSize(bytes) {
    if (bytes < 1024) return bytes + ' Б';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' КБ';
    return (bytes / 1024 / 1024).toFixed(1) + ' МБ';
}

// ----------------------------------------------------------------------------
// Работа с куками
// ----------------------------------------------------------------------------
/**
 * Возвращает значение cookie по имени.
 * @param {string} name - имя cookie
 * @returns {string|null}
 */
export function getCookie(name) {
    const v = document.cookie.split(';').find(c => c.trim().startsWith(name + '='));
    return v ? v.trim().slice(name.length + 1) : null;
}

// ----------------------------------------------------------------------------
// Универсальная функция для запросов к API с поддержкой CSRF и таймаута
// ----------------------------------------------------------------------------
/**
 * Выполняет HTTP-запрос к API.
 * Автоматически добавляет заголовок X-CSRF-Token для методов, изменяющих данные.
 * Устанавливает таймаут 10 секунд через AbortController.
 * @param {string} method - HTTP метод (GET, POST, ...)
 * @param {string} path - путь (начинается с /api/...)
 * @param {Object} [body] - тело запроса (будет преобразовано в JSON)
 * @returns {Promise<any>} распарсенный JSON ответа
 * @throws {Error} с сообщением об ошибке
 */
export async function api(method, path, body) {
    const opts = { method, credentials: 'include', headers: {} };
    if (body) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
    }
    const state = window.AppState;
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && state?.csrfToken) {
        opts.headers['X-CSRF-Token'] = state.csrfToken;
    }

    // Таймаут 10 секунд
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    try {
        const r = await fetch(path, { ...opts, signal: controller.signal });
        clearTimeout(timeoutId);
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
            const msg = data.detail || data.error || data.message || `Ошибка сервера (HTTP ${r.status})`;
            throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
        return data;
    } catch (err) {
        clearTimeout(timeoutId);
        // Обработка таймаута
        if (err.name === 'AbortError') {
            throw new Error('Сервер не отвечает (таймаут). Попробуйте ещё раз.');
        }
        // Обработка сетевых ошибок
        if (err instanceof TypeError && err.message.toLowerCase().includes('fetch')) {
            throw new Error('Нет соединения с сервером.');
        }
        throw err;
    }
}

// ----------------------------------------------------------------------------
// Загрузка CSRF-токена
// ----------------------------------------------------------------------------
/**
 * Получает CSRF-токен с сервера и сохраняет в AppState.
 */
export async function loadCsrfToken() {
    try {
        const d = await api('GET', '/api/authentication/csrf-token');
        window.AppState.csrfToken = d.csrf_token;
    } catch { }
}

// ----------------------------------------------------------------------------
// Управление модальными окнами
// ----------------------------------------------------------------------------
/**
 * Открывает модальное окно (добавляет класс 'show').
 * @param {string} id - id модального окна
 */
export function openModal(id) {
    $(id).classList.add('show');
}

/**
 * Закрывает модальное окно (убирает класс 'show').
 * @param {string} id - id модального окна
 */
export function closeModal(id) {
    $(id).classList.remove('show');
}

// ----------------------------------------------------------------------------
// Показ всплывающих уведомлений
// ----------------------------------------------------------------------------
/**
 * Показывает алерт в указанном элементе на 5 секунд.
 * @param {string} id - id элемента для сообщения
 * @param {string} msg - текст сообщения
 * @param {string} [type='error'] - тип (error, success, ...)
 */
export function showAlert(id, msg, type = 'error') {
    const el = $(id);
    el.textContent = msg;
    el.className = `alert show alert-${type}`;
    setTimeout(() => el.classList.remove('show'), 5000);
}

// ----------------------------------------------------------------------------
// Прокрутка контейнера сообщений вниз
// ----------------------------------------------------------------------------
/**
 * Прокручивает контейнер с сообщениями в самый низ.
 * @param {boolean} [smooth=false] - использовать плавную прокрутку
 */
export function scrollToBottom(smooth = false) {
    const c = $('messages-container');
    if (c) c.scrollTo({ top: c.scrollHeight, behavior: smooth ? 'smooth' : 'instant' });
}