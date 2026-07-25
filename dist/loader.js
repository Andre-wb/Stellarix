// loader.js
(function() {
  const statusEl = document.getElementById('status');
  const detailsEl = document.getElementById('details');
  const progressContainer = document.getElementById('progressContainer');
  const progressBar = document.getElementById('progressBar');
  const appEl = document.getElementById('app');

  // Состояния загрузки с разными сообщениями
  const STAGES = [
    { progress: 10, status: 'Запуск базы данных...', detail: 'Инициализация PostgreSQL' },
    { progress: 25, status: 'Подготовка кластера...', detail: 'Создание файлов базы данных' },
    { progress: 40, status: 'Запуск сервера PostgreSQL...', detail: 'Старт процесса' },
    { progress: 55, status: 'Создание базы данных...', detail: 'Инициализация Stellarix' },
    { progress: 70, status: 'Выполнение миграций...', detail: 'Настройка схемы' },
    { progress: 85, status: 'Запуск веб-сервера...', detail: 'Подготовка приложения' },
    { progress: 95, status: 'Почти готово...', detail: 'Финальные проверки' },
  ];

  let currentStage = 0;
  let stageInterval = null;
  let isComplete = false;
  let hasError = false;
  let recoveryTimer = null;
  let lastBackendStage = null;
  const bridgePresent = !!(window.__TAURI__ && window.__TAURI__.event);

  function log() {
    try { console.log.apply(console, ['[loader]'].concat([].slice.call(arguments))); } catch (e) {}
  }

  // Функция обновления прогресса
  function updateProgress(stageIndex) {
    if (isComplete || hasError) return;

    const stage = STAGES[stageIndex] || STAGES[STAGES.length - 1];
    progressContainer.classList.add('active');
    progressBar.style.width = stage.progress + '%';
    statusEl.innerHTML = stage.status + ' <span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    detailsEl.textContent = stage.detail;
  }

  // Автоматическое продвижение стадий
  function advanceStage() {
    if (isComplete || hasError) return;

    if (currentStage < STAGES.length - 1) {
      currentStage++;
      updateProgress(currentStage);
    }
  }

  // Запуск анимации стадий
  function startProgress() {
    // Показываем первую стадию сразу
    updateProgress(0);

    // Переключаем стадии каждые 3-5 секунд
    let delay = 3000;
    stageInterval = setInterval(() => {
      if (isComplete || hasError) {
        clearInterval(stageInterval);
        return;
      }
      advanceStage();

      // Увеличиваем задержку к концу
      if (currentStage > 4) {
        delay = 5000;
        clearInterval(stageInterval);
        stageInterval = setInterval(advanceStage, delay);
      }
    }, delay);
  }

  // Завершение загрузки (успех)
  function completeLoading() {
    if (isComplete) return;
    isComplete = true;
    clearInterval(stageInterval);
    clearInterval(recoveryTimer);

    progressBar.style.width = '100%';
    statusEl.innerHTML = 'Готово! Приложение запущено';
    detailsEl.textContent = 'Переход в основной интерфейс...';
    appEl.classList.add('success');

    // Небольшая задержка перед редиректом
    setTimeout(() => {
      window.location.href = 'http://127.0.0.1:8000/';
    }, 800);
  }

  // Ошибка
  function showError(message) {
    if (hasError) return;
    hasError = true;
    clearInterval(stageInterval);

    progressContainer.classList.remove('active');
    appEl.classList.add('error');
    statusEl.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" style="vertical-align:-3px" aria-hidden="true"><g stroke="#ffffff" stroke-width="3.6" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/></g><g stroke="#8a8a88" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/></g></svg>' + ' Ошибка запуска';
    detailsEl.textContent = message || 'Проверьте логи для подробностей';
  }

  // Обработка событий от Tauri
  if (bridgePresent) {
    const { listen } = window.__TAURI__.event;
    log('Мост Tauri доступен, регистрирую слушатели событий старта');

    listen('server-progress', (event) => {
      lastBackendStage = event.payload;
      log('этап бэкенда:', event.payload);
      if (!isComplete && !hasError) detailsEl.textContent = event.payload;
    });

    // Слушаем событие готовности сервера
    listen('server-ready', (event) => {
      log('получено server-ready', event && event.payload);
      completeLoading();
    });

    // Слушаем ошибки
    listen('server-error', (event) => {
      log('получено server-error', event.payload);
      showError(event.payload || 'Неизвестная ошибка');
      // Показываем ошибку в консоли для отладки
      console.error('Server error:', event.payload);
    });
  } else {
    console.error('[loader] window.__TAURI__ недоступен — IPC-мост не готов, события старта не придут');
    detailsEl.textContent = 'IPC-мост Tauri недоступен (window.__TAURI__ отсутствует)';
  }

  // Запускаем анимацию прогресса
  startProgress();

  const SERVER_URL = 'http://127.0.0.1:8000/';
  let recoveryAttempts = 0;
  recoveryTimer = setInterval(() => {
    if (isComplete) { clearInterval(recoveryTimer); return; }
    recoveryAttempts++;
    if (recoveryAttempts > 90) { clearInterval(recoveryTimer); return; }
    fetch(SERVER_URL, { mode: 'no-cors', cache: 'no-store' })
      .then(() => {
        if (isComplete) return;
        console.warn('[loader] сервер отвечает, но server-ready не пришло — навигация по резервному опросу (событие потеряно)');
        completeLoading();
      })
      .catch(() => { /* сервер ещё не готов */ });
  }, 2000);

  // Таймаут на случай, если что-то пошло не так и событие не пришло
  const timeoutId = setTimeout(() => {
    if (!isComplete && !hasError) {
      let msg = 'Превышено время ожидания запуска сервера';
      if (!bridgePresent) {
        msg += ' — IPC-мост Tauri (window.__TAURI__) не инициализировался';
      } else if (lastBackendStage) {
        msg += ' — застряли на этапе: ' + lastBackendStage;
      } else {
        msg += ' — бэкенд не прислал ни одного этапа (возможно, события потеряны)';
      }
      showError(msg);
      console.error('Timeout:', msg);
    }
  }, 90000);

  // Очищаем таймаут при завершении
  window.addEventListener('beforeunload', () => {
    clearTimeout(timeoutId);
    clearInterval(stageInterval);
    clearInterval(recoveryTimer);
  });

  // Экспортируем функции для отладки
  window.__loader = {
    complete: completeLoading,
    error: showError,
    stage: currentStage
  };
})();