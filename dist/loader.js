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

    progressBar.style.width = '100%';
    statusEl.innerHTML = 'Готово! Приложение запущено ✅';
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
    statusEl.innerHTML = '❌ Ошибка запуска';
    detailsEl.textContent = message || 'Проверьте логи для подробностей';
  }

  // Обработка событий от Tauri
  if (window.__TAURI__) {
    const { listen } = window.__TAURI__.event;

    // Слушаем событие готовности сервера
    listen('server-ready', () => {
      completeLoading();
    });

    // Слушаем ошибки
    listen('server-error', (event) => {
      showError(event.payload || 'Неизвестная ошибка');
      // Показываем ошибку в консоли для отладки
      console.error('Server error:', event.payload);
    });
  }

  // Запускаем анимацию прогресса
  startProgress();

  // Таймаут на случай, если что-то пошло не так и событие не пришло
  const timeoutId = setTimeout(() => {
    if (!isComplete && !hasError) {
      // Если прошло 30 секунд, а сервер не запустился
      showError('Превышено время ожидания запуска сервера');
      console.error('Timeout: Server did not start within 30 seconds');
    }
  }, 60000);

  // Очищаем таймаут при завершении
  window.addEventListener('beforeunload', () => {
    clearTimeout(timeoutId);
    clearInterval(stageInterval);
  });

  // Экспортируем функции для отладки
  window.__loader = {
    complete: completeLoading,
    error: showError,
    stage: currentStage
  };
})();