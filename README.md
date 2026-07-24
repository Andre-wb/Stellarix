# Установка Stellarix

## 1. Установка зависимостей

### Системные зависимости

#### Для Windows

1. **Установите Rust** (если ещё не установлен):
    - Скачайте и запустите [rustup-init.exe](https://rustup.rs/)
    - Выберите вариант установки по умолчанию (Default installation)
    - После установки перезапустите терминал
    - **Альтернативный способ через командную строку:**
      ```bash
      # Если у вас уже есть winget (Windows Package Manager)
      winget install Rustlang.Rustup
      
      # Или через chocolatey
      choco install rust
      ```

2. **Установите PostgreSQL**:
    - Скачайте [PostgreSQL для Windows](https://www.postgresql.org/download/windows/)
    - Во время установки запомните пароль для пользователя `postgres`
    - Добавьте `C:\Program Files\PostgreSQL\<версия>\bin` в переменную PATH
    - **Альтернативный способ через командную строку:**
      ```bash
      # Через winget
      winget install PostgreSQL.PostgreSQL
      
      # Через chocolatey
      choco install postgresql
      
      # Через Docker (если Docker установлен)
      docker run -d --name stellarix-db -e POSTGRES_PASSWORD=yourpassword -p 5432:5432 postgres:15
      ```

3. **Установите дополнительные зависимости для Tauri**:
    - Установите [Microsoft Visual Studio C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
        - Выберите "Desktop development with C++"
        - Включите "Windows 10/11 SDK"
    - Установите [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (обычно уже установлен в Windows 11)
    - **Альтернативный способ через командную строку:**
      ```bash
      # Установка Visual Studio Build Tools через winget
      winget install Microsoft.VisualStudio.2022.BuildTools
      
      # Или через chocolatey
      choco install visualstudio2022buildtools
      choco install visualstudio2022-workload-vctools
      ```

4. **Установите Node.js** (для Tauri):
    - Скачайте [Node.js](https://nodejs.org/) (LTS версия)
    - Установите с параметрами по умолчанию
    - **Альтернативный способ через командную строку:**
      ```bash
      # Через winget
      winget install OpenJS.NodeJS
      
      # Или через chocolatey
      choco install nodejs
      ```

### Настройка переменных окружения Windows

Если вы столкнулись с проблемами "команда не найдена", добавьте пути вручную:

```powershell
# Добавление в PATH (PowerShell)
# Для Rust
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Users\%USERNAME%\.cargo\bin", [EnvironmentVariableTarget]::User)

# Для PostgreSQL (измените версию на вашу)
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\PostgreSQL\15\bin", [EnvironmentVariableTarget]::User)

# Для Node.js
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\nodejs", [EnvironmentVariableTarget]::User)

# Применение изменений
refreshenv
```

### Установка Rust инструментов

```bash
# Обновление Rust до последней версии
rustup update

# Установка дополнительных компонентов Rust
rustup component add rustfmt clippy

# Установка SQLx CLI для работы с базой данных
cargo install sqlx-cli --no-default-features --features postgres

# Установка Tauri CLI через cargo
cargo install tauri-cli

# Или через npm (альтернативный способ для Tauri)
npm install -g @tauri-apps/cli

# Установка дополнительных утилит
cargo install cargo-watch
cargo install cargo-audit
cargo install cargo-edit
cargo install cargo-expand
cargo install cargo-tree
cargo install cargo-deny
```

### Проверка установки

```bash
# Проверка Rust
rustc --version
cargo --version
rustup --version

# Проверка SQLx CLI
sqlx --version

# Проверка Tauri CLI
cargo tauri --version
# Или
tauri --version

# Проверка Node.js и npm
node --version
npm --version

# Проверка PostgreSQL
psql --version
pg_config --version

# Проверка Visual Studio Build Tools
cl
# Если не работает, откройте "Developer Command Prompt for VS 2022"
```

### Настройка базы данных

```bash
# Создайте базу данных PostgreSQL
# Войдите в psql:
psql -U postgres
# Если psql не найден, используйте полный путь:
# "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres

# Создайте базу данных:
CREATE DATABASE stellarix;
# Или с другой кодировкой:
CREATE DATABASE stellarix ENCODING 'UTF8';

# Создайте пользователя (опционально):
CREATE USER stellarix_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE stellarix TO stellarix_user;

# Выйдите:
\q

# Или через командную строку:
createdb -U postgres stellarix

# Если createdb не найден, используйте полный путь:
# "C:\Program Files\PostgreSQL\15\bin\createdb.exe" -U postgres stellarix
```

### Решение распространённых проблем в Windows

```bash
# Если cargo install не работает из-за openssl
cargo install sqlx-cli --no-default-features --features postgres --locked

# Если ошибка с openssl при сборке
cargo install tauri-cli --locked

# Очистка кэша cargo при проблемах
cargo clean
cargo update

# Переустановка зависимостей проекта
cargo fetch
cargo build

# Если ошибка при запуске SQLx
# Проверьте, что PostgreSQL сервер запущен:
# Services -> PostgreSQL -> Start
# Или через командную строку:
net start postgresql-x64-15

# Сброс миграций базы данных
sqlx db drop
sqlx db create
sqlx migrate run

# Проверка состояния базы данных
sqlx db info
```

### Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
DATABASE_URL=postgres://postgres:ваш_пароль@localhost:5432/stellarix

# Альтернативный вариант с пользователем
DATABASE_URL=postgres://stellarix_user:your_password@localhost:5432/stellarix
```

### Установка фронтенд зависимостей (если требуется)

```bash
# Перейдите в папку с веб-фронтендом (если есть)
cd src-tauri

# Если используете npm
npm install

# Если используете yarn
yarn install

# Если используете pnpm
pnpm install
```

---

Теперь в директории src-tauri/ нужно запустить проект (он будет как десктоп приложение, но в основе лежит веб-приложение). Лучше всего для тестов/разработки.

```
cd src-tauri
cargo run
```

### Еще вот так запустить можно

```bash
# Запуск с предварительной проверкой
cargo tauri dev

# Запуск в релизном режиме ( это сделает реальное приложение)
cargo tauri build 

# Запуск с дебагом
cargo run -- --debug
```

### Если всё ещё возникают проблемы

1. Перезагрузите компьютер после установки всех зависимостей
2. Убедитесь, что у вас есть права администратора при установке
3. Проверьте логи установки PostgreSQL в `C:\Program Files\PostgreSQL\<версия>\data\pg_log\`
4. Проверьте порт 5432 на занятость: `netstat -ano | findstr :5432`
5. Если порт занят, укажите другой в файле `.env`: `DATABASE_URL=postgres://postgres:password@localhost:5433/stellarix`
6. Временно отключите антивирус или добавьте пути в исключения
7. Убедитесь, что все пути в PATH корректные и нет лишних пробелов