// static/js/ui.js
// ============================================================================
// Модуль управления интерфейсом: переключение между экранами,
// открытие комнаты, отображение профиля.
// ============================================================================

import { $ } from './utils.js';
import { renderRoomsList } from './rooms.js';
import { connectWS } from './chat/chat.js';
import { connectSignal } from './webrtc.js';

/**
 * Показывает приветственный экран (выбор комнаты).
 * Скрывает чат, сбрасывает currentRoom, перерисовывает список комнат.
 */
export function showWelcome() {
    $('welcome-screen').classList.add('active');
    $('chat-screen').classList.remove('active');
    $('welcome-screen').style.display = 'flex';
    $('chat-screen').style.display = 'none';
    window.AppState.currentRoom = null;
    renderRoomsList();
    $('nav-welcome').classList.add('active');
}

/**
 * Показывает экран чата.
 * Скрывает приветственный экран, активирует соответствующую кнопку навигации.
 */
export function showChatScreen() {
    $('welcome-screen').style.display = 'none';
    $('chat-screen').style.display = 'flex';
    $('chat-screen').classList.add('active');
    $('welcome-screen').classList.remove('active');
    $('nav-welcome').classList.remove('active');
}

/**
 * Открывает комнату с заданным ID.
 * Устанавливает currentRoom, закрывает предыдущее WebSocket-соединение,
 * очищает сообщения, подключает новые WebSocket (чат и сигнализация).
 * @param {number} id - ID комнаты
 */
export function openRoom(id) {
    const S = window.AppState;
    const room = S.rooms.find(r => r.id === id);
    if (!room) return;
    S.currentRoom = room;
    if (S.ws) {
        S.ws.onclose = null;
        if (S.ws._ping) clearInterval(S.ws._ping);
        S.ws.close();
        S.ws = null;
    }
    showChatScreen();
    $('messages-container').innerHTML = '';
    $('chat-room-name').textContent = room.name;
    $('chat-room-meta').textContent = `${room.member_count} участников · ${room.online_count} онлайн`;
    renderRoomsList();
    connectWS(id);
    // ✅ Федеративные комнаты всегда сигналят через виртуальный ID = -1
    const signalId = room.is_federated ? -1 : id;
    connectSignal(signalId);
}

/**
 * Открывает модальное окно профиля текущего пользователя.
 * Заполняет данные из AppState.user.
 */
export function showProfileModal() {
    const S = window.AppState;
    if (!S.user) return;
    $('prof-phone').textContent = S.user.phone;
    $('prof-username').textContent = '@' + S.user.username;
    $('prof-created').textContent = new Date(S.user.created_at).toLocaleDateString('ru');
    window.openModal('profile-modal');
}

// Функция для управления выдвижным меню на мобильных устройствах
function toggleMobileMenu(open) {
    const sidebar = document.getElementById('sidebar');
    const backButton = document.getElementById('back-button');

    if (!sidebar || !backButton) return;

    if (open === undefined) {
        // Если параметр не передан, переключаем состояние
        sidebar.classList.toggle('open');
    } else if (open) {
        sidebar.classList.add('open');
    } else {
        sidebar.classList.remove('open');
    }

    // Меняем положение кнопки в зависимости от состояния сайдбара
    if (sidebar.classList.contains('open')) {
        backButton.style.left = 'auto';
        backButton.style.right = '5px';
        backButton.style.transform = 'rotate(180deg)'; // Разворачиваем стрелку
    } else {
        backButton.style.left = '0';
        backButton.style.right = 'auto';
        backButton.style.transform = 'rotate(0deg)';
    }
}

// Обработчик клика на кнопку "назад"
document.getElementById('back-button').addEventListener('click', function(e) {
    e.stopPropagation(); // Предотвращаем всплытие события
    toggleMobileMenu();
});

// Закрываем меню при клике на любой пункт в сайдбаре
document.querySelectorAll('#sidebar .nav-item, #sidebar .rooms-list div, #sidebar .sidebar-footer button .room-item').forEach(item => {
    item.addEventListener('click', function() {
        // Проверяем, что мы на мобильном устройстве (ширина экрана <= 639px)
        if (window.innerWidth <= 639) {
            toggleMobileMenu(false); // Закрываем меню
        }
    });
});

// Закрываем меню при клике вне сайдбара (на основной контент)
document.getElementById('main').addEventListener('click', function(e) {
    // Проверяем, что мы на мобильном устройстве и меню открыто
    if (window.innerWidth <= 639) {
        const sidebar = document.getElementById('sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            // Проверяем, что клик был не по кнопке "назад" и не по сайдбару
            if (!e.target.closest('#sidebar') && !e.target.closest('#back-button')) {
                toggleMobileMenu(false);
            }
        }
    }
});

// Обработчик изменения размера окна - закрываем меню при переходе на десктоп
window.addEventListener('resize', function() {
    if (window.innerWidth > 639) {
        // На десктопе всегда показываем сайдбар и сбрасываем положение кнопки
        const sidebar = document.getElementById('sidebar');
        const backButton = document.getElementById('back-button');

        if (sidebar) {
            sidebar.classList.remove('open');
        }

        if (backButton) {
            backButton.style.left = '0';
            backButton.style.right = 'auto';
            backButton.style.transform = 'rotate(0deg)';
        }
    }
});

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Сбрасываем состояние на десктопе
    if (window.innerWidth > 639) {
        const sidebar = document.getElementById('sidebar');
        const backButton = document.getElementById('back-button');

        if (sidebar) {
            sidebar.classList.remove('open');
        }

        if (backButton) {
            backButton.style.left = '0';
            backButton.style.right = 'auto';
            backButton.style.transform = 'rotate(0deg)';
        }
    }
});
/*
toggleMobileMenu(false);
* */