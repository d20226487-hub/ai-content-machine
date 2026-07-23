/**
 * Russian translation dictionary. Keep synchronised with en.ts (same keys).
 *
 * Style: formal "Вы" (capitalized in product strings is the convention here).
 * Brand names (WordPress, Polylang, WPML, Bearer, JSON, CSV, JWT, API) stay
 * in Latin script. Per the user's request, navigation labels: Single → Один,
 * Bulk → Массово.
 */
import type { en } from "./en";

export const ru: Record<keyof typeof en, string> = {
  // ---------- common ----------
  "common.loading": "Загрузка…",
  "common.refresh": "Обновить",
  "tableCost.title": "Стоимость генерации",
  "tableCost.summary":
    "{usd} за {gens} генераций по {cells} ячейкам.",
  "tableCost.includesRegenerations":
    "Включая повторы и перегенерации — это общие расходы, а не стоимость текущего текста.",
  "tableCost.unpricedWarning":
    "{n} генераций выполнено на provider:model без заданной цены — они учтены как $0. Реальная сумма выше: задайте цену в Настройки → Цены (применится только к будущим генерациям).",
  "tableCost.colColumn": "Колонка",
  "tableCost.colCost": "Стоимость",
  "tableCost.colCells": "Ячейки",
  "tableCost.colGenerations": "Генерации",
  "tableCost.colTokens": "Токены",
  "tableCost.noSpend":
    "Пока ничего не сгенерировано или таблица создана до учёта расходов.",
  "tableCost.toolsHeading": "ИИ-инструменты",
  "tableCost.toolsHint":
    "Проходы очистки с ИИ по этой таблице (перевод, исправление ссылок). Показаны отдельно — не входят в сумму генерации выше.",
  "tableCost.colTool": "Инструмент",
  "tableCost.colCalls": "Вызовы",
  "tableCost.tool.brain_translate": "Перевод",
  "tableCost.tool.brain_fix_links": "Исправление ссылок ИИ",
  "tableCost.toolUnpricedHint":
    "{n} вызов(ов) добавили $0 — не задана ставка для этого провайдера:модели, либо они выполнены до появления поштучного учёта расходов.",
  "common.retry": "Повторить",
  "common.save": "Сохранить",
  "common.saving": "Сохранение…",
  "common.saved": "Сохранено",
  "common.savedDot": "Сохранено.",
  "common.cancel": "Отмена",
  "common.close": "Закрыть",
  "modal.unsavedConfirm": "Есть несохранённые изменения — отменить их?",
  "modal.discard": "Отменить",
  "modal.keepEditing": "Продолжить редактирование",
  "common.delete": "Удалить",
  "common.deleteFailed": "Не удалось удалить",
  "common.edit": "Редактировать",
  "common.add": "Добавить",
  "common.adding": "Добавление…",
  "common.create": "Создать",
  "common.creating": "Создание…",
  "common.createFailed": "Не удалось создать",
  "common.rename": "Переименовать",
  "common.renameFailed": "Не удалось переименовать",
  "common.move": "Переместить",
  "common.moveFailed": "Не удалось переместить",
  "common.duplicate": "Дублировать",
  "common.import": "Импорт",
  "common.importing": "Импорт…",
  "common.importFailed": "Не удалось импортировать",
  "common.done": "Готово",
  "common.export": "Экспорт",
  "common.exportFailed": "Не удалось экспортировать",
  "common.copy": "Копировать",
  "common.copied": "Скопировано",
  "common.details": "Подробнее",
  "common.hide": "Скрыть",
  "common.show": "Показать",
  "common.previous": "Назад",
  "common.next": "Далее",
  "common.prev": "← Назад",
  "common.nextArrow": "Далее →",
  "common.page": "Страница",
  "common.pageXofY": "Страница {page} из {total}",
  "common.pageXslashY": "Страница {page} / {total}",
  "common.perPage": "На странице",
  "common.rows": "Строк",
  "common.showingRange": "Показано {from}–{to} из {total}",
  "common.failedToLoad": "Не удалось загрузить",
  "common.somethingWentWrong": "Что-то пошло не так",
  "common.searchPlaceholder": "Поиск…",
  "common.search": "Поиск",
  "common.optional": "(необязательно)",
  "common.actions": "Действия",
  "common.yes": "Да",
  "common.no": "Нет",
  "common.openArrow": "Открыть ↗",
  "common.open": "Открыть",
  "common.unknown": "(неизвестно)",
  "common.empty": "(пусто)",
  "common.merge": "Объединить",
  "common.mergeFailed": "Не удалось объединить",
  "common.actionFailed": "Действие не выполнено",
  "common.dash": "—",

  // ---------- app shell ----------
  "app.brand": "Content Beast",
  "app.tagline": "Внутренний инструмент для генерации контента с помощью ИИ",
  "app.signOut": "Выйти",
  "nav.dashboard": "Главная",
  "nav.prompts": "Промпты",
  "nav.content": "Контент",
  "nav.single": "Один",
  "nav.bulk": "Массово",
  "nav.publish": "Публикация",
  "nav.users": "Пользователи",
  "nav.errors": "Ошибки",
  "nav.settings": "Настройки",
  "nav.docs": "Документация",

  // ---------- theme + language toggles ----------
  "theme.label": "Тема",
  "theme.light": "Светлая",
  "theme.system": "Системная",
  "theme.dark": "Тёмная",
  "theme.toLight": "Переключить на светлую тему",
  "theme.toDark": "Переключить на тёмную тему",
  "lang.label": "Язык",
  "lang.en": "EN",
  "lang.ru": "RU",

  // ---------- login ----------
  "login.subtitle": "Войдите, чтобы продолжить",
  "login.email": "Электронная почта",
  "login.password": "Пароль",
  "login.submit": "Войти",
  "login.submitting": "Выполняется вход…",
  "login.failed": "Не удалось войти",

  // ---------- dashboard ----------
  "dashboard.welcome": "Добро пожаловать, {name}",
  "dashboard.role": "Роль",
  "dashboard.apiStatus": "Статус API",
  "dashboard.checking": "Проверка…",
  "dashboard.reachable": "Доступен",
  "dashboard.unreachable": "Недоступен",
  "dashboard.note": "Настройки, Пользователи и Промпты готовы к работе.",
  "dashboard.docsTitle": "Документация",
  "dashboard.docsSubtitle": "Подробные руководства по каждому разделу системы — как создавать промпты, запускать массовую генерацию, публиковать в WordPress и так далее.",
  "dashboard.docsCta": "Открыть документацию →",
  "dashboard.docsQuickLinks": "Быстрые ссылки",

  // ---------- users ----------
  "users.title": "Пользователи",
  "users.subtitle":
    "Управляйте тем, кто может входить в систему и какие действия ему разрешены.",
  "users.newButton": "Новый пользователь",
  "users.loading": "Загрузка пользователей…",
  "users.colEmail": "Эл. почта",
  "users.colName": "Имя",
  "users.colRole": "Роль",
  "users.colActive": "Активен",
  "users.colCreated": "Создан",
  "users.colSpend": "Расходы (этот месяц)",
  "users.colSpendHint":
    "Расходы на вызовы LLM API в этом месяце (USD). Наведите на мелкие цифры — увидите за день / 7 дней / всё время. Цены задаются в Настройках → Цены.",
  "users.spendToday": "сегодня",
  "users.spendWeek": "7д",
  "users.spendMonth": "месяц",
  "users.spendAll": "всё время",
  "users.spendEvents": "вызовов",
  "users.orphanSpend":
    "Расходы удалённых пользователей: {month} в этом месяце, {all} всего.",
  "pricing.title": "Цены LLM",
  "pricing.subtitle":
    "USD за 1 000 000 токенов для каждой пары provider:model. Стоимость рассчитывается в момент записи события — изменения здесь влияют только на новые генерации, исторические суммы не пересчитываются.",
  "pricing.addRow": "+ Добавить строку",
  "pricing.empty":
    "Цены ещё не настроены. Добавьте строку для пары provider:model, чтобы начать отслеживать расходы.",
  "pricing.colProvider": "Код провайдера",
  "pricing.colModel": "Модель",
  "pricing.colInput": "Вход $/1M",
  "pricing.colOutput": "Выход $/1M",
  "pricing.unitHint":
    "USD за 1M токенов. Десятичные дроби допустимы: 0.075, 1.25 и т. п.",
  "users.you": "вы",
  "users.confirmDelete":
    "Переместить {email} в Корзину? Сессия сразу обрывается, войти заново нельзя. Восстановить можно со страницы Корзины в течение срока хранения.",
  "users.modalNew": "Новый пользователь",
  "users.modalEdit": "Редактирование {email}",
  "users.fieldFullName": "Полное имя",
  "users.fieldFullNamePlaceholder": "Необязательно",
  "users.fieldRole": "Роль",
  "users.cantChangeOwnRole": "Нельзя изменить собственную роль.",
  "users.cantDeactivateSelf": "(нельзя деактивировать себя)",
  "users.fieldActive": "Активен",
  "users.fieldPassword": "Пароль",
  "users.fieldPasswordReset": "Сбросить пароль (необязательно)",
  "users.passwordPlaceholderNew": "Минимум 8 символов",
  "users.passwordPlaceholderEdit":
    "Оставьте пустым, чтобы сохранить текущий пароль",
  "users.managersCantEditAdmins":
    "Менеджеры не могут редактировать администраторов.",
  "users.saveChanges": "Сохранить изменения",
  "users.createUser": "Создать пользователя",
  "users.saveFailed": "Не удалось сохранить",

  // ---------- settings ----------
  "settings.title": "Настройки",
  "backup.title": "Резервные копии базы",
  "backup.subtitle":
    "Ежедневный pg_dump запускается в 03:00 UTC. Дампы хранятся локально и при желании загружаются в любое S3-совместимое хранилище.",
  "backup.scheduleHeading": "Расписание",
  "backup.scheduleHint":
    "Резервные копии создаются раз в сутки в выбранное время. Изменения вступают в силу при следующем запуске — перезапуск не нужен.",
  "backup.scheduleEnabled": "Создавать копии автоматически",
  "backup.scheduleEnabledHint":
    "Когда выключено — ежедневное расписание не запускается. Запустить вручную можно кнопкой выше в любой момент.",
  "backup.scheduleHour": "Время запуска (UTC)",
  "backup.destinationHeading": "Куда сохранять",
  "backup.destinationHint":
    "Резервная копия всегда сохраняется на сервере, где работает приложение. По желанию её можно также загружать в S3-совместимое хранилище (AWS S3, MinIO, Garage, Backblaze B2 и т. п.) для внешнего копирования.",
  "backup.s3Enabled": "Загружать копии в S3-совместимое хранилище",
  "backup.s3EnabledHint":
    "Когда выключено — копии остаются только на этом сервере. Когда включено — воркер загружает каждый дамп и удаляет более старые по сроку хранения в S3.",
  "backup.endpoint": "URL эндпойнта",
  "backup.region": "Регион",
  "backup.bucket": "Бакет",
  "backup.prefix": "Префикс ключа",
  "backup.accessKey": "Access key ID",
  "backup.secretKey": "Secret access key",
  "backup.secretConfigured": "(задан — введите новое значение для замены)",
  "backup.secretEmpty": "Не задан",
  "backup.clearSecret": "Удалить сохранённый ключ",
  "backup.secretCleared": "Ключ удалён.",
  "backup.localRetention": "Локальное хранение (дней)",
  "backup.s3Retention": "Хранение в S3 (дней)",
  "backup.testConnection": "Проверить подключение",
  "backup.testing": "Проверка…",
  "backup.runNow": "Запустить сейчас",
  "backup.runningNow": "Запуск…",
  "backup.recentRuns": "Последние запуски",
  "backup.noRuns": "Пока нет резервных копий.",
  "backup.col.started": "Начало",
  "backup.col.status": "Статус",
  "backup.col.size": "Размер",
  "backup.col.trigger": "Триггер",
  "backup.col.s3": "Ключ S3",
  "backup.col.error": "Ошибка",
  "backup.loadHint":
    "Если это появилось после обновления, бэкенду, возможно, нужна пересборка + `alembic upgrade head`, чтобы подхватить новые роуты и таблицу backup_runs.",
  "settings.subtitle":
    "Провайдеры ИИ, модели по умолчанию и лимиты запросов для каждого провайдера. Только API-ключи шифруются на диске; вы можете очистить или заменить их в любой момент.",
  "settings.loadingProviders": "Загрузка провайдеров…",
  "settings.tabsAria": "Разделы настроек",
  "settings.tab.providers": "Провайдеры",
  "settings.tab.generation": "Генерация",
  "settings.tab.publishing": "Публикация",
  "settings.tab.pricing": "Цены",
  "settings.tab.backups": "Бэкапы",
  "settings.tab.trash": "Корзина",
  "settings.tab.brain": "Мозг",
  "brain.translateTitle": "Промпт для перевода",
  "brain.translateSubtitle":
    "Управляет кнопкой «Перевести» в редакторе ячеек bulk-таблиц. Для output-ячеек открывается параллельный перевод, чтобы коллеги, не знающие исходный язык, могли прочитать контент.",
  "brain.promptLabel": "Системный промпт",
  "brain.promptHint":
    "Используйте {{target_language}} как плейсхолдер для запрошенного языка. Значение ячейки передаётся как сообщение пользователя.",
  "brain.defaultLangLabel": "Язык перевода по умолчанию",
  "brain.defaultLangHint":
    "Двухбуквенный код (например, ru, en, pl). Редактор ячеек подставит его по умолчанию; пользователь сможет выбрать другой язык для каждого перевода.",
  "brain.providerLabel": "Провайдер ИИ для перевода",
  "brain.providerHint":
    "Оставьте пустым, чтобы использовать первого включённого провайдера и его модель по умолчанию.",
  "brain.fixLinksTitle": "Промпт исправления ссылок",
  "brain.fixLinksSubtitle":
    "Используется кнопкой «Исправить ИИ» в проверке ссылок. Имея список ожидаемых ссылок и найденные проблемы, модель вставляет недостающие ссылки, исправляет опечатки и удаляет выдуманные — меняя только ссылки и ничего больше.",
  "brain.gdocsMetaTitle": "Промпт извлечения мета из Google Docs",
  "brain.gdocsMetaSubtitle":
    "Используется импортом из Google Docs для извлечения SEO-заголовка и мета-описания из начала каждого документа, когда метки распознать однозначно не удаётся. Провайдер и модель выбираются при каждом импорте в окне загрузки.",
  "brain.gdocsPairingTitle": "Промпт сопоставления страниц Google Docs",
  "brain.gdocsPairingSubtitle":
    "Используется импортом из Google Docs, чтобы сопоставить каждый документ со страницей из колонки «Структура» (слаг берётся из структуры). Опирается на заголовок и содержимое документа, так как ссылки-якоря бывают неверными. Провайдер и модель выбираются при каждом импорте в окне загрузки.",
  "translate.button": "Перевести",
  "translate.original": "Оригинал",
  "translate.translation": "Перевод",
  "translate.translate": "Перевести",
  "translate.retranslate": "Перевести заново",
  "translate.translating": "Переводим…",
  "translate.emptyHint":
    "Выберите язык и нажмите «Перевести». Результат кэшируется в ячейке, повторное открытие ничего не стоит.",
  "translate.noLang": "Сначала выберите язык перевода.",
  "translate.langSelect": "Популярные языки",
  "translate.langCustomOption": "Свой…",
  "translate.langInput": "Код языка",
  "translate.closePanel": "Закрыть панель перевода",
  "settings.enabled": "Включён",
  "settings.apiKey": "API-ключ",
  "settings.apiKeyPlaceholderSet":
    "•••••••••••• (задан — введите, чтобы заменить)",
  "settings.apiKeyPlaceholderUnset": "Не задан",
  "settings.apiKeyStored":
    "Хранится в зашифрованном виде. Оставьте пустым, чтобы сохранить текущий ключ.",
  "settings.apiKeyEmpty": "Ключ ещё не задан.",
  "settings.testConnection": "Проверить подключение",
  "settings.testing": "Проверка…",
  "settings.testHintTyped":
    "Проверить только что введённый ключ (без сохранения)",
  "settings.testHintSaved": "Проверить сохранённый ключ",
  "settings.testHintNeedKey": "Сначала введите или сохраните ключ",
  "settings.clearKey": "Очистить ключ",
  "settings.vertexAuthHeader": "Авторизация через сервисный аккаунт (рекомендуется)",
  "settings.vertexAuthHint":
    "Для продакшен-нагрузок вставьте JSON сервисного аккаунта Google Cloud и укажите project + регион. Оставьте поля пустыми, чтобы использовать Vertex Express через API-ключ выше (только пробные квоты).",
  "settings.vertexProjectId": "ID проекта GCP",
  "settings.vertexLocation": "Регион",
  "settings.vertexSaJson": "JSON сервисного аккаунта",
  "settings.vertexSaJsonPlaceholder": "Вставьте сюда полный JSON сервисного аккаунта…",
  "settings.vertexSaJsonStored": "Сохранён — вставьте новый JSON, чтобы заменить.",
  "settings.vertexSaJsonHelperEmpty":
    "Перед сохранением шифруется. Сервисному аккаунту нужна роль Vertex AI User в проекте.",
  "settings.vertexSaJsonHelperStored":
    "JSON сервисного аккаунта уже сохранён. Замените его, вставив новый, или используйте Очистить.",
  "settings.vertexClear": "Очистить",
  "settings.vertexConfirmClear":
    "Очистить сохранённые project, регион и JSON сервисного аккаунта Vertex?",
  "settings.confirmClearKey": "Очистить API-ключ для {provider}?",
  "settings.clearKeyFailed": "Не удалось очистить ключ",
  "settings.testRequestFailed": "Не удалось выполнить проверочный запрос",
  "settings.connectionOk": "✓ Подключение успешно",
  "settings.connectionFailed": "✗ Проверка не пройдена",
  "settings.reply": "Ответ: {text}",
  "settings.defaultModel": "Модель по умолчанию",
  "settings.modelForAi": "Модель для создания промптов с помощью ИИ",
  "settings.availableModels": "Доступные модели (по одной в строке)",
  "settings.showRateLimits": "Показать настройки лимитов запросов",
  "settings.hideRateLimits": "Скрыть настройки лимитов запросов",
  "settings.rpm": "Запросов в минуту",
  "settings.maxConcurrency": "Макс. параллельных запросов",
  "settings.batchSize": "Размер пакета",
  "settings.delayMs": "Задержка между запросами (мс)",
  "settings.retryMax": "Максимум повторов",
  "settings.backoffBase": "Базовая задержка отката (мс)",
  "settings.backoffJitter": "Случайный разброс отката (мс)",
  "settings.respectRetryAfter": "Учитывать заголовок Retry-After",
  "settings.saveFailed": "Не удалось сохранить",
  "settings.generationDefaults": "Параметры генерации по умолчанию",
  "settings.generationDefaultsHint":
    "Применяются ко всем генерациям, где не задано иное. Отдельная колонка может задать свой лимит в редакторе колонки.",
  "settings.maxOutputTokens": "Максимум токенов ответа",
  "settings.maxOutputTokensHint":
    "Жёсткий предел длины ответа модели. Слишком маленькое значение обрезает длинные статьи на середине фразы — примерно 1000 токенов на 700 слов HTML.",
  "settings.thinkingBudgetEnable": "Управлять бюджетом рассуждений",
  "settings.thinkingBudgetHint":
    "Некоторые модели (Gemini 2.5, Claude Sonnet 5) тратят часть лимита на внутренние рассуждения перед ответом, из-за чего ответ каждый раз укорачивается по-разному. Оставьте выключенным, чтобы использовать поведение модели по умолчанию.",
  "settings.thinkingBudget": "Токены на рассуждения",
  "settings.thinkingBudgetZeroHint":
    "0 отключает рассуждения — весь лимит уходит на ответ.",
  "settings.publishDefaults": "Параметры публикации по умолчанию",
  "settings.publishDefaultsHint":
    "Глобальные лимиты запросов, применяемые ко всем доменам, если у домена нет собственного значения (задаётся в Редактирование домена → Лимиты запросов).",
  "settings.publishDefaultsRpm": "Запросов в минуту",
  "settings.respectRetryAfterHint":
    "Учитывать заголовок Retry-After при ответах 429",
  "settings.saveDefaults": "Сохранить значения",

  // ---------- errors page ----------
  "errors.title": "Журнал ошибок",
  "errors.totalSuffix": "всего",
  "errors.exportSelected": "Экспорт выбранных ({count})",
  "errors.exportAllMatching": "Экспорт всех подходящих",
  "errors.exportAllHint":
    "Экспортирует до 10 000 записей, соответствующих текущим фильтрам",
  "errors.retention": "Срок хранения:",
  "errors.daysSuffix": "дн.",
  "errors.purgeOld": "Очистить старые",
  "errors.purging": "Очистка…",
  "errors.confirmPurge": "Удалить все записи об ошибках старше {days} дн.?",
  "errors.purgeFailed": "Не удалось очистить",
  "errors.purgeDeleted": "Удалено старых записей: {count}.",
  "errors.retentionUpdated": "Срок хранения обновлён: {days} дн.",
  "errors.retentionUpdateFailed": "Не удалось обновить срок хранения",
  "errors.confirmDeleteOne": "Удалить эту запись об ошибке?",
  "errors.searchPlaceholder": "Поиск по сообщению…",
  "errors.allSources": "Все источники",
  "errors.allCategories": "Все категории",
  "errors.allProviders": "Все провайдеры",
  "errors.colTime": "Время",
  "errors.colSource": "Источник",
  "errors.colCategory": "Категория",
  "errors.colProvider": "Провайдер",
  "errors.colStatus": "Статус",
  "errors.colUser": "Пользователь",
  "errors.colMessage": "Сообщение",
  "errors.selectAllOnPage": "Выбрать всё на странице",
  "errors.selectRowAria": "Выбрать ошибку №{id}",
  "errors.noneMatch": "Нет ошибок, соответствующих текущим фильтрам.",
  "errors.failedToLoad": "Не удалось загрузить ошибки",

  // error detail drawer
  "errors.detailTitle": "Ошибка №{id}",
  "errors.copyJson": "Копировать JSON",
  "errors.sectionMessage": "Сообщение",
  "errors.sectionContext": "Контекст",
  "errors.sectionStack": "Трассировка стека",
  "errors.fieldSource": "Источник",
  "errors.fieldCategory": "Категория",
  "errors.fieldProvider": "Провайдер",
  "errors.fieldStatusCode": "Код состояния",
  "errors.fieldUser": "Пользователь",
  "errors.fieldResource": "Ресурс",

  // ---------- prompts (list page) ----------
  "prompts.title": "Промпты",
  "prompts.folderFallback": "Папка",
  "prompts.includeSubfolders": "Включая вложенные папки",
  "prompts.includeSubfoldersHint":
    "Когда включено, поиск и фильтр по тегам охватывают и вложенные папки. По умолчанию: только содержимое текущей папки.",
  "prompts.newFolder": "+ Новая папка",
  "prompts.manageTags": "Управление тегами",
  "prompts.newPrompt": "+ Новый промпт",
  "prompts.searchPlaceholder": "Поиск промптов…",
  "prompts.tagsLabel": "Теги",
  "prompts.tagAddFilter": "Добавить «{name}» в фильтр (логическое И)",
  "prompts.tagRemoveFilter": "Убрать «{name}» из фильтра",
  "prompts.tagsClear": "Очистить",
  "prompts.tagsAndNote": "· у промпта должны быть все выбранные теги",
  "prompts.foldersHeading": "Папки ({count})",
  "prompts.promptsHeading": "Промпты",
  "prompts.selectedCount": "Выбрано: {count}",
  "prompts.selectedCountPlural": "Выбрано: {count}",
  "prompts.selectAllOnPage": "Выбрать все на странице",
  "prompts.selectRow": "Выбрать {name}",
  "prompts.moveToFolder": "Переместить в папку…",
  "prompts.moveModalTitle": "Переместить промпты ({count}) в папку",
  "prompts.moveModalTitlePlural": "Переместить промпты ({count}) в папку",
  "prompts.moveModalSubtitle": "Выберите назначение. «Корень» — убрать из всех папок.",
  "prompts.empty.noMatches": "Под эти фильтры не подходит ни один промпт.",
  "prompts.empty.none": "Здесь пока нет промптов.",
  "prompts.empty.createFirst": "Создать первый",
  "prompts.folderPromptsCount": "Промптов: {count}",
  "prompts.folderPromptsCountPlural": "Промптов: {count}",
  "prompts.folderSubfoldersCount": " · вложенных папок: {count}",
  "prompts.folderSubfoldersCountPlural": " · вложенных папок: {count}",
  "prompts.inFolderLabel": "в",
  "prompts.versionPrefix": "v",
  "prompts.unfilledVariablesPrompt": "(пусто)",
  "prompts.breadcrumbHome": "Главная",
  "prompts.folderNamePrompt": "Название папки:",
  "prompts.renameFolderPrompt": "Переименовать папку:",
  "prompts.confirmDeleteFolder":
    "Удалить папку «{name}»? Папка должна быть пустой (без промптов и подпапок).",
  "prompts.movePickerNoFolder": "— без папки —",
  "prompts.failedLoadFolders": "Не удалось загрузить папки",
  "prompts.failedLoadTags": "Не удалось загрузить теги",
  "prompts.failedLoadPrompts": "Не удалось загрузить промпты",

  // prompt detail
  "promptDetail.back": "← Назад к промптам",
  "promptDetail.folderLabel": "Папка: {name}",
  "promptDetail.noFolder": "Без папки",
  "promptDetail.updated": "обновлено {time}",
  "promptDetail.createdBy": "Создан",
  "promptDetail.createdOn": "{date}",
  "promptDetail.currentContent": "Текущая версия",
  "promptDetail.test": "Тест",
  "promptDetail.testHint":
    "Попробовать этот промпт с тестовыми значениями переменных — без сохранения и публикации, просто для быстрой проверки.",
  "test.title": "Тест промпта — {name}",
  "test.subtitle":
    "Заполните переменные и сгенерируйте результат. Ничего не сохраняется.",
  "test.noVariables": "У этого промпта нет переменных; нажмите «Сгенерировать», чтобы увидеть вывод.",
  "test.provider": "Провайдер",
  "test.model": "Модель",
  "test.noKey": " (нет API-ключа)",
  "test.pickProviderModel": "Сначала выберите провайдера и модель.",
  "test.missingHint": "Не заполнены переменные: {vars}",
  "test.generate": "Сгенерировать",
  "test.pageTitle": "Тест промпта",
  "test.pageSubtitle":
    "Быстрая песочница для этого промпта. Заполните переменные, сгенерируйте и посмотрите результат. Ничего не сохраняется.",
  "test.outputSubtitle":
    "Результат теста. Возврат к форме сохраняет заполненные переменные.",
  "test.backToPrompt": "Назад к промпту",
  "test.generating": "Генерация…",
  "test.generateFailed": "Не удалось сгенерировать",
  "test.failedLoadProviders": "Не удалось загрузить провайдеров",
  "test.resultMeta": "{provider} · {model}",
  "promptDetail.variables": "Переменные",
  "promptDetail.versionHistory": "История версий ({count})",
  "promptDetail.versionCurrent": "текущая",
  "promptDetail.versionBy": "автор: {name}",
  "promptDetail.noteFor": "Примечание к этой версии",
  "promptDetail.noteEmpty": "нет примечания",
  "promptDetail.noteEdit": "изменить",
  "promptDetail.noteAdd": "добавить",
  "promptDetail.revert": "Откатить",
  "promptDetail.confirmRevert":
    "Откатить к v{n}? Будет создана новая версия.",
  "promptDetail.confirmDelete":
    "Переместить «{name}» в Корзину? История версий сохранится; восстановить можно со страницы Корзины в течение срока хранения.",
  "promptDetail.noteSaveFailed":
    "Не удалось сохранить примечание. Подробности в консоли.",
  "promptDetail.revertFailed": "Откат не выполнен",

  // tags page
  "tags.title": "Управление тегами",
  "tags.subtitle":
    "Переименовывайте, объединяйте или удаляйте теги. Объединение перенесёт все промпты на целевой тег и удалит исходный.",
  "tags.newPlaceholder": "Название нового тега",
  "tags.search": "Поиск тегов…",
  "tags.colName": "Название",
  "tags.colPrompts": "Промпты",
  "tags.colLastUsed": "Последнее использование",
  "tags.colCreated": "Создан",
  "tags.empty": "Пока нет тегов.",
  "tags.emptySearch": "Ничего не найдено.",
  "tags.confirmDelete": "Удалить тег «{name}»?",
  "tags.confirmDeleteWithCount":
    "Удалить тег «{name}»? У {count} промпт(ов) этот тег будет снят.",
  "tags.confirmMerge":
    "Объединить «{src}» с «{tgt}»?\n\n{count} промпт(ов) с тегом «{src}» будут перетегированы на «{tgt}». Тег «{src}» затем будет удалён.",
  "tags.mergeIntoLabel": "в",
  "tags.mergePickTarget": "— выберите целевой —",
  "tags.mergeNeedOther":
    "Для объединения нужен хотя бы один другой тег",
  "tags.failedLoad": "Не удалось загрузить теги",

  // new prompt modal
  "newPrompt.title": "Новый промпт",
  "newPrompt.modeManual": "Вручную",
  "newPrompt.modeAi": "С помощью ИИ",
  "newPrompt.aiDescribe": "Опишите, что должен делать промпт",
  "newPrompt.aiDescribePlaceholder":
    "напр., промпт, пишущий вступление к SEO-статье на 200 слов для B2B SaaS, с настраиваемой темой, тоном и аудиторией.",
  "newPrompt.noProviderEnabled":
    "Нет включённых провайдеров. Настройте провайдера в разделе Настройки, чтобы использовать ИИ-черновик.",
  "newPrompt.providerLabel": "Провайдер",
  "newPrompt.modelLabel": "Модель",
  "newPrompt.providerNoApiKey": "(нет API-ключа)",
  "newPrompt.providerNoKeyHint":
    "Нет API-ключа — генерация недоступна, пока он не задан в Настройках.",
  "newPrompt.aiDraftFailed": "Не удалось создать ИИ-черновик",
  "newPrompt.draftButton": "Сгенерировать черновик",
  "newPrompt.drafting": "Генерация…",
  "newPrompt.draftedWith": "Сгенерировано через {provider} / {model}",
  "newPrompt.fieldName": "Название",
  "newPrompt.fieldFolder": "Папка",
  "newPrompt.folderNone": "— Без папки —",
  "newPrompt.fieldContent": "Содержимое",
  "newPrompt.contentPlaceholder":
    "Используйте {{имя_переменной}} для частей, которые будут заполняться при генерации.",
  "newPrompt.fieldTags": "Теги",
  "newPrompt.addTagPlaceholder": "Добавить новый тег…",
  "newPrompt.fieldChangeNote": "Примечание к версии (необязательно)",
  "newPrompt.changeNotePlaceholder": "Сохранится как примечание к v1",
  "newPrompt.createPrompt": "Создать промпт",
  "newPrompt.failedAddTag": "Не удалось добавить тег",
  "newPrompt.failedCreate": "Не удалось создать",

  // edit prompt modal
  "editPrompt.title": "Редактирование промпта",
  "editPrompt.subtitle":
    "Изменение содержимого создаёт новую версию. Переименование или перемещение — нет.",
  "editPrompt.fieldChangeNote": "Примечание к версии",
  "editPrompt.changeNotePlaceholder":
    "напр., уточнена системная инструкция",
  "editPrompt.changeNoteFootnote":
    "Сохраняется при создании новой версии, чтобы потом было ясно, что изменилось.",
  "editPrompt.noTags": "Тегов пока нет",
  "editPrompt.saveAsNewVersion": "Сохранить как новую версию",

  // ---------- library (list) ----------
  "library.title": "Библиотека",
  "library.subtitleRoot":
    "Ваши таблицы массовой генерации. Сохраняются автоматически по мере правок.",
  "library.subtitleFolder":
    "Таблицы в этой папке. Сохраняются автоматически по мере правок.",
  "library.newFolder": "+ Новая папка",
  "library.importCsv": "Импорт CSV",
  "library.importGdocs": "Импорт из Google Docs",
  "library.newTable": "+ Новая таблица",
  "library.searchPlaceholder": "Поиск таблиц…",
  "library.searchInFolderPlaceholder": "Поиск в «{folder}»…",
  "library.foldersHeading": "Папки ({count})",
  "library.subfoldersHeading": "Вложенные папки ({count})",
  "library.tablesHeading": "Таблицы",
  "library.selectedCount": "Выбрано: {count}",
  "library.selectedCountPlural": "Выбрано: {count}",
  "library.selectAllOnPage": "Выбрать все на странице",
  "library.selectTable": "Выбрать {name}",
  "library.moveToFolder": "Переместить в папку…",
  "library.moveModalTitle": "Переместить таблицы ({count}) в папку",
  "library.moveModalTitlePlural": "Переместить таблицы ({count}) в папку",
  "library.moveModalSubtitle": "Выберите назначение. «Корень» — убрать из всех папок.",
  "library.empty.search": "По вашему запросу ничего не найдено.",
  "library.empty.folder": "Папка пуста.",
  "library.empty.none": "У вас ещё нет таблиц.",
  "library.empty.createOne": "Создать таблицу",
  "library.empty.or": " или ",
  "library.empty.importCsv": "импортировать CSV",
  "library.tableMeta":
    "колонок: {cols} · строк: {rows} · обновлено {time}",
  "library.folderTablesCount": "Таблиц: {count}",
  "library.folderTablesCountPlural": "Таблиц: {count}",
  "library.folderSubfoldersCount": "Вложенных папок: {count}",
  "library.folderSubfoldersCountPlural": "Вложенных папок: {count}",
  "library.folderNamePrompt": "Название папки:",
  "library.renameFolderPrompt": "Переименовать папку:",
  "library.confirmDeleteFolder":
    "Удалить папку «{name}»? Папка должна быть пустой (сначала переместите все таблицы).",
  "library.newTablePrompt": "Название новой таблицы:",
  "library.confirmDeleteTable":
    "Переместить «{name}» в Корзину? Восстановить можно со страницы Корзины в течение срока хранения.",
  "library.deleteBlockedInflight":
    "Нельзя переместить таблицу в Корзину: по ней идёт массовая публикация. Сначала отмените прогон на /publish/runs.",
  "library.trashLink": "Корзина",
  "library.trashLinkWithCount": "Корзина ({count})",
  "library.trash.title": "Корзина",
  "library.trash.subtitle":
    "Удалённые таблицы хранятся здесь {days} дней, потом удаляются безвозвратно.",
  "library.trash.subtitleManual":
    "Автоочистка выключена. Таблицы остаются здесь, пока их не удалят вручную.",
  "library.trash.empty": "Корзина пуста.",
  "library.trash.deletedAt": "Удалена {time}",
  "library.trash.preview": "Просмотр",
  "library.trash.restore": "Восстановить",
  "library.trash.deletePermanent": "Удалить навсегда",
  "library.trash.restoreSelected": "Восстановить выбранные",
  "library.trash.deleteSelected": "Удалить выбранные",
  "library.trash.emptyAll": "Очистить корзину",
  "library.trash.selectAll": "Выбрать все на странице",
  "library.trash.confirmDeletePermanent":
    "Удалить «{name}» безвозвратно? Это нельзя отменить.",
  "library.trash.confirmEmpty":
    "Безвозвратно удалить все {count} таблиц(ы) в корзине? Это нельзя отменить.",
  "library.trash.confirmDeleteSelected":
    "Безвозвратно удалить выбранные таблицы ({count})? Это нельзя отменить.",
  "library.trash.restored": "Восстановлено таблиц: {count}.",
  "library.trash.deleted": "Удалено безвозвратно: {count}.",
  "library.trash.previewBanner":
    "Эта таблица в Корзине (удалена {time}). Доступна только для чтения — восстановите для редактирования.",
  "library.trash.previewBack": "← Корзина",
  "library.trash.retentionLabel":
    "Автоочистка корзины через",
  "library.trash.retentionDays": "дней",
  "library.trash.retentionHint":
    "0 — отключить автоочистку (таблицы остаются в корзине до ручного удаления).",
  "library.trash.retentionSaved": "Сохранено.",
  "library.trash.retentionTitle": "Срок хранения корзины таблиц",
  "settings.trashRetention.title": "Срок хранения корзин",
  "settings.trashRetention.hint":
    "Сколько дней сущности хранятся в Корзине, пока ежедневная задача очистки не удалит их безвозвратно. 0 — отключить автоочистку (только ручная).",
  "settings.trashRetention.days": "дней",
  "settings.trashRetention.saved": "Сохранено.",
  "settings.trashRetention.bulkTables": "Bulk-таблицы",
  "settings.trashRetention.domains": "Домены",
  "settings.trashRetention.prompts": "Промпты",
  "settings.trashRetention.users": "Пользователи",
  "users.trashLinkWithCount": "Корзина ({count})",
  "users.trash.title": "Корзина",
  "users.trash.subtitle":
    "Удалённые пользователи хранятся здесь {days} дней, потом удаляются безвозвратно. Не-админы вычищаются ежедневной фоновой задачей; админы пропускаются — их нужно «Удалить навсегда» вручную.",
  "users.trash.subtitleManual":
    "Автоочистка выключена. Пользователи остаются здесь, пока их не удалят вручную.",
  "users.trash.adminHint":
    "Замечание: трешированные пользователи не могут войти, их сессия сбрасывается мгновенно. Восстановление возвращает их в активный список — войти нужно заново (старый токен не воссоздаётся).",
  "users.trash.empty": "Корзина пуста.",
  "users.trash.deletedAt": "Удалён {time}",
  "users.trash.restore": "Восстановить",
  "users.trash.deletePermanent": "Удалить навсегда",
  "users.trash.restoreSelected": "Восстановить выбранные",
  "users.trash.deleteSelected": "Удалить выбранные",
  "users.trash.emptyAll": "Очистить корзину",
  "users.trash.selectAll": "Выбрать все",
  "users.trash.confirmDeletePermanent":
    "Удалить {email} безвозвратно? Атрибуция в промптах/доменах/таблицах станет «(удалённый пользователь)». История расходов сохранится в общей корзине. Это нельзя отменить.",
  "users.trash.confirmEmpty":
    "Безвозвратно удалить все {count} пользователей в корзине? Админы пропускаются (см. подсказку выше). Это нельзя отменить.",
  "users.trash.confirmDeleteSelected":
    "Безвозвратно удалить выбранных пользователей ({count})? Админы в выборке пропускаются.",
  "users.trash.restored": "Восстановлено: {count}.",
  "users.trash.deleted": "Удалено безвозвратно: {count}.",
  "users.trash.skippedConflicts":
    "Пропущено {count} пользователей из-за конфликтов email с активными аккаунтами: {emails}",
  "prompts.trashLinkWithCount": "Корзина ({count})",
  "prompts.trash.title": "Корзина",
  "prompts.trash.subtitle":
    "Удалённые промпты хранятся здесь {days} дней, потом удаляются безвозвратно. История версий сохраняется до окончательного удаления.",
  "prompts.trash.subtitleManual":
    "Автоочистка выключена. Промпты остаются здесь, пока их не удалят вручную.",
  "prompts.trash.empty": "Корзина пуста.",
  "prompts.trash.deletedAt": "Удалён {time}",
  "prompts.trash.restore": "Восстановить",
  "prompts.trash.deletePermanent": "Удалить навсегда",
  "prompts.trash.restoreSelected": "Восстановить выбранные",
  "prompts.trash.deleteSelected": "Удалить выбранные",
  "prompts.trash.emptyAll": "Очистить корзину",
  "prompts.trash.selectAll": "Выбрать все на странице",
  "prompts.trash.confirmDeletePermanent":
    "Удалить «{name}» безвозвратно? Вся история версий пропадёт навсегда.",
  "prompts.trash.confirmEmpty":
    "Безвозвратно удалить все {count} промпт(ов) в корзине? Истории версий пропадут. Это нельзя отменить.",
  "prompts.trash.confirmDeleteSelected":
    "Безвозвратно удалить выбранные промпты ({count})? Истории версий пропадут.",
  "prompts.trash.restored": "Восстановлено промптов: {count}.",
  "prompts.trash.deleted": "Удалено безвозвратно: {count}.",
  "domains.trashLinkWithCount": "Корзина ({count})",
  "domains.deleteBlockedInflight":
    "Нельзя переместить домен в Корзину: по нему идёт массовая публикация. Сначала отмените прогон на /publish/runs.",
  "domains.confirmDelete":
    "Переместить «{name}» в Корзину? Учётные данные и профили публикации сохранятся — восстановить можно со страницы Корзины.",
  "domains.trash.title": "Корзина",
  "domains.trash.subtitle":
    "Удалённые домены хранятся здесь {days} дней, потом удаляются безвозвратно. До этого момента учётные данные, профили публикации, лимиты и media-кэш сохраняются.",
  "domains.trash.subtitleManual":
    "Автоочистка выключена. Домены остаются здесь, пока их не удалят вручную.",
  "domains.trash.empty": "Корзина пуста.",
  "domains.trash.deletedAt": "Удалён {time}",
  "domains.trash.restore": "Восстановить",
  "domains.trash.deletePermanent": "Удалить навсегда",
  "domains.trash.restoreSelected": "Восстановить выбранные",
  "domains.trash.deleteSelected": "Удалить выбранные",
  "domains.trash.emptyAll": "Очистить корзину",
  "domains.trash.selectAll": "Выбрать все",
  "domains.trash.confirmDeletePermanent":
    "Удалить «{name}» безвозвратно? Учётные данные и профили публикации будут потеряны.",
  "domains.trash.confirmEmpty":
    "Безвозвратно удалить все {count} домен(ов) в корзине? Это нельзя отменить.",
  "domains.trash.confirmDeleteSelected":
    "Безвозвратно удалить выбранные домены ({count})? Это нельзя отменить.",
  "domains.trash.restored": "Восстановлено доменов: {count}.",
  "domains.trash.deleted": "Удалено безвозвратно: {count}.",
  "library.movePickerNoFolder": "— без папки —",
  "library.breadcrumbRoot": "Библиотека",
  "library.inFolder": "в",

  // table detail
  "libraryTable.back": "← Библиотека",
  "libraryTable.exportCsv": "Экспорт CSV",
  "libraryTable.exportPreparing": "Подготовка…",
  "libraryTable.exportPreparingPct": "Подготовка… {pct}%",
  "libraryTable.exportDownloading": "Загрузка…",
  "libraryTable.exportFailed": "Не удалось экспортировать. {error}",
  "libraryTable.updateTable": "Обновить таблицу",

  // ---- Обновление таблицы из CSV / вставки ----
  "updateTable.title": "Обновить таблицу из CSV или вставленных данных",
  "updateTable.subtitle":
    "Обновляет существующие строки — сопоставьте один или несколько столбцов; остальное не трогается. Строки не добавляются и не удаляются.",
  "updateTable.sourceFile": "Загрузить файл",
  "updateTable.sourcePaste": "Вставить данные",
  "updateTable.fileLabel": "Файл CSV / TSV",
  "updateTable.pasteLabel": "Вставьте строки (из Excel/Таблиц или CSV)",
  "updateTable.pastePlaceholder": "Вставьте строки с разделителем-табуляцией или запятой…",
  "updateTable.firstRowHeader": "Первая строка — заголовок",
  "updateTable.detected": "Обнаружено столбцов: {cols}, строк данных: {rows}.",
  "updateTable.detectedFile": "Обнаружено столбцов в файле: {cols}.",
  "updateTable.mapHeading": "Сопоставление столбцов",
  "updateTable.mapFrom": "Из (ваши данные)",
  "updateTable.mapSample": "Первое значение",
  "updateTable.mapTo": "В столбец таблицы",
  "updateTable.dontImport": "— Не импортировать —",
  "updateTable.matchHeading": "Сопоставлять строки по",
  "updateTable.matchKey": "Ключевому столбцу",
  "updateTable.matchKeyUsing": "использовать",
  "updateTable.matchKeyMatches": "для сопоставления со столбцом",
  "updateTable.matchOrder": "Порядку строк",
  "updateTable.matchOrderHint":
    "1-я строка данных обновляет 1-ю строку таблицы, 2-я→2-ю и т. д.",
  "updateTable.skipEmpty": "Не изменять ячейки, пустые в данных",
  "updateTable.updateBtn": "Обновить столбцов: {n}",
  "updateTable.updating": "Обновление…",
  "updateTable.failed": "Не удалось обновить",
  "updateTable.tooLarge": "Файл слишком большой (макс. 100 МБ).",
  "updateTable.tooManyRows": "Слишком много вставленных строк (макс. {max}) — загрузите их файлом.",
  "updateTable.pasteTooLong": "Вставленных данных слишком много — загрузите их файлом.",
  "updateTable.doneTitle": "Таблица обновлена",
  "updateTable.doneCells": "Обновлено ячеек: {cells} в строках: {rows}.",
  "updateTable.doneMatched": "Сопоставлено входных строк: {n}.",
  "updateTable.doneUnmatched": "Не сопоставлено входных строк: {n} (пропущены).",
  "libraryTable.tableMeta": "колонок: {cols} · строк: {rows}",
  "libraryTable.createdBy": " · создал ",
  "libraryTable.clickToRename": "Щёлкните, чтобы переименовать",
  "libraryTable.confirmDelete":
    "Удалить «{name}» и все её строки? Это действие нельзя отменить.",
  "libraryTable.failedLoad": "Не удалось загрузить таблицу",
  "libraryTable.savedAt": "Сохранено в {time}",

  // bulk grid
  "bulkGrid.toolbarSelected": "Выбрано строк: {count}",
  "bulkGrid.toolbarClickGenerate":
    "Нажмите «Сгенерировать», чтобы настроить запуск.",
  "bulkGrid.clearValues": "Очистить значения",
  "bulkGrid.clearValuesHint":
    "Удалить значения всех ячеек в выбранных строках (сами строки остаются)",
  "bulkGrid.confirmClearValues":
    "Очистить значения всех ячеек в строках ({count})? Сами строки останутся; будут удалены только значения.",
  "bulkGrid.clearValuesFailed":
    "Не удалось очистить значения. Подробности в консоли.",
  "bulkGrid.clearSelection": "Снять выделение",
  "bulkGrid.publishHint":
    "Опубликовать строки этой таблицы на подключённый сайт",
  "bulkGrid.publishLabelSelected": "Опубликовать (выбрано: {count})…",
  "bulkGrid.publishLabel": "Массовая публикация…",
  "bulkGrid.generateLabelSelected": "Сгенерировать (выбрано: {count})…",
  "bulkGrid.generateLabel": "Сгенерировать…",
  "bulkGrid.generateDisabledHint":
    "Сначала настройте промпт хотя бы для одной выходной колонки",
  "bulkGrid.generateOpenHint": "Открыть очередь генерации",
  "autotool.button": "Autotool",
  "autotool.remove": "Удалить из Autotool",
  "autotool.disabledHint":
    "Сделать таблицу публичным CSV, который сможет забирать Autotool",
  "autotool.enabledHint": "Таблица доступна как публичный CSV для Autotool",
  "autotool.copyLink": "Копировать ссылку на CSV",
  "autotool.copied": "Скопировано",
  "autotool.linkLabel": "Публичная ссылка на CSV",
  "autotool.enableTitle": "Добавить в Autotool?",
  "autotool.enableBody":
    "Будет опубликован публичный CSV этой таблицы по неугадываемой ссылке без авторизации. Любой, у кого есть ссылка, сможет прочитать содержимое — сгенерированный текст, домены назначения, ID постов. Autotool по этой ссылке публикует строки таблицы на ваши сайты.",
  "autotool.enableConfirm": "Добавить в Autotool",
  "autotool.removeTitle": "Удалить из Autotool?",
  "autotool.removeBody":
    "Таблица будет удалена из Autotool, а её публичная ссылка сразу станет недействительной — Autotool больше не сможет её забрать. Добавить обратно можно будет позже, но ссылка будет новой.",
  "autotool.removeConfirm": "Удалить из Autotool",
  "autotool.cancel": "Отмена",
  "autotool.failed": "Что-то пошло не так. Попробуйте ещё раз.",
  "bulkGrid.selectAllOnPage": "Выбрать все строки на этой странице",
  "bulkGrid.colKindOutput": "выход",
  "bulkGrid.colKindInput": "вход",
  "bulkGrid.colNoPrompt": " · нет промпта",
  "bulkGrid.cfgPromptHint":
    "Настроить промпт и привязку переменных",
  "bulkGrid.toggleKindHint": "Переключить на «{kind}»",
  "bulkGrid.deleteColumnHint": "Удалить колонку",
  "bulkGrid.addColumnHint": "Добавить колонку",
  "bulkGrid.addColumnPrompt": "Название новой колонки:",
  "bulkGrid.addColumnFailed": "Не удалось добавить колонку",
  "bulkGrid.confirmDeleteColumn":
    "Удалить колонку «{name}»? Все её значения будут потеряны.",
  "bulkGrid.deleteRowHint": "Удалить строку",
  "bulkGrid.confirmDeleteRow": "Удалить эту строку?",
  "bulkGrid.openViewerHint":
    "Двойной щелчок откроет средство просмотра",
  "bulkGrid.openViewer": "Открыть средство просмотра",
  "bulkGrid.truncated": "обрезано",
  "bulkGrid.truncatedHint":
    "Модель достигла лимита токенов ответа, поэтому текст неполный. Увеличьте «Максимум токенов ответа» для этой колонки (или в Настройки → Генерация) и сгенерируйте заново.",
  "bulkGrid.outputPlaceholder": "(вывод ИИ)",
  "bulkGrid.generating": "Генерация…",
  "bulkGrid.failedClickToSee":
    "✗ Ошибка — щёлкните, чтобы посмотреть",
  "bulkGrid.failedHint": "Щёлкните, чтобы посмотреть ошибку",
  "bulkGrid.dragResizeHint":
    "Тяните, чтобы изменить ширину · двойной щелчок — сброс",
  "bulkGrid.doubleClickRename":
    "Двойной щелчок, чтобы переименовать",
  "bulkGrid.addRow": "+ Добавить строку",
  "bulkGrid.noRows": "Строк нет",
  "bulkGrid.rowsRange": "Строки {from}–{to} из {total}",
  "bulkGrid.selectedSuffix": "выбрано: {count}",
  "bulkGrid.selectAllN": "Выбрать все {total}",
  "bulkGrid.rowHeight": "Высота строки",
  "bulkGrid.rowsPerPage": "Строк на странице",
  "bulkGrid.firstPage": "Первая страница",
  "bulkGrid.previousPage": "Предыдущая страница",
  "bulkGrid.nextPage": "Следующая страница",
  "bulkGrid.lastPage": "Последняя страница",
  "bulkGrid.heightCompact": "Компактная",
  "bulkGrid.heightDefault": "Обычная",
  "bulkGrid.heightComfortable": "Просторная",
  "bulkGrid.heightTall": "Высокая",
  "bulkGrid.errorTitle": "Ошибка генерации: {col}",
  "bulkGrid.errorEmpty": "(нет описания ошибки)",
  "bulkGrid.retryCell": "Повторить для этой ячейки",
  "bulkGrid.retryFailed":
    "Не удалось повторить. Подробности в консоли.",

  // generation error banner (table-wide failed / truncated notice)
  "genErrors.failedTitle": "Ячеек с ошибкой генерации: {count}",
  "genErrors.truncatedTitle": "Ячеек обрезано (не поместились): {count}",
  "genErrors.affectedColumns": "Затронутые столбцы:",
  "genErrors.truncatedHelp":
    "Эти ответы упёрлись в лимит выходных токенов, поэтому текст неполный. Прежде чем повторять, увеличьте «Макс. выходных токенов» для этих столбцов (или в «Настройки → Генерация») — иначе их снова обрежет.",
  "genErrors.retryFailed": "Повторить с ошибкой ({count})",
  "genErrors.retryFailedHint":
    "Открыть очередь генерации и перезапустить только ячейки, где запрос завершился ошибкой.",
  "genErrors.retryTruncated": "Повторить обрезанные ({count})",
  "genErrors.retryTruncatedHint":
    "Открыть очередь генерации и перезапустить только обрезанные ячейки. Сначала увеличьте «Макс. выходных токенов», иначе их снова обрежет.",

  // cell editor
  "cellEditor.edit": "Редактирование",
  "cellEditor.preview": "Предпросмотр",
  "cellEditor.changes": "Изменения",
  "cellEditor.changesHint":
    "Зелёным — ссылки, добавленные или изменённые ИИ; зачёркнутым красным — удалённые.",
  "cellEditor.empty": "Ячейка пуста",
  "cellEditor.unsavedChanges": "Несохранённые изменения",
  "cellEditor.noChanges": "Изменений нет",
  "cellEditor.toSave": "для сохранения",
  "cellEditor.groundingSources": "Источники ({n})",
  "cellEditor.groundingQueries": "Запросы: {q}",

  // column config
  "colCfg.title": "Настройка колонки:",
  "colCfg.subtitle":
    "Выберите промпт и укажите, какая колонка должна заполнять каждую переменную.",
  "colCfg.prompt": "Промпт",
  "colCfg.searchPrompts": "Поиск промптов…",
  "colCfg.noFolder": "(без папки)",
  "colCfg.noPromptsMatch": "Нет подходящих промптов.",
  "colCfg.variables": "Переменные ({count})",
  "colCfg.noVariables":
    "У этого промпта нет переменных — он будет отправляться как есть для каждой строки.",
  "colCfg.pickSourceColumn": "— выберите исходную колонку —",
  "colCfg.outputSuffix": "(выход)",
  "colCfg.auto": "авто",
  "colCfg.providerModel": "Провайдер и модель",
  "colCfg.optionalOverride": "(необязательное переопределение)",
  "colCfg.useWorkspaceDefault":
    "— Использовать значение по умолчанию —",
  "colCfg.providerNoKeyHint":
    "API-ключ не настроен — генерация завершится ошибкой.",
  "colCfg.usesProviderDefault": "(использовать модель провайдера)",
  "colCfg.useProviderDefault": "(использовать модель провайдера)",
  "colCfg.inheritHint":
    "Оставьте оба поля пустыми, чтобы использовать первый включённый провайдер из Настроек.",
  "colCfg.maxOutputTokens": "Максимум токенов ответа",
  "colCfg.maxOutputTokensPlaceholder": "Наследовать общее значение",
  "colCfg.maxOutputTokensHint":
    "Предел длины ответа для этой колонки. Увеличьте для полных статей, уменьшите для заголовков и мета-описаний. Пусто — берётся из Настройки → Генерация.",
  "colCfg.grounding": "Граундинг (research)",
  "colCfg.groundingOff": "Выключено",
  "colCfg.groundingGoogleSearch": "Google Search — исследовать тему",
  "colCfg.groundingHint":
    "Исследует тему через живой поиск Google и прикрепляет использованные источники. Лучше всего — на отдельной колонке, которую остальные читают как переменную. Добавляет наценку за каждую ячейку сверх токенов.",
  "colCfg.groundingRequiresVertex":
    "Чтобы включить граундинг, выберите провайдера Google Vertex AI и модель Gemini.",
  "colCfg.preview": "Предпросмотр",
  "colCfg.previewLoading": "(загрузка или нечего показать)",
  "colCfg.unfilledVarsForRow":
    "Незаполненные переменные для этой строки: {vars}",
  "colCfg.rowHash": "Строка №{n}",
  "colCfg.clearAssignment": "Сбросить привязку промпта",
  "colCfg.saveFailed": "Не удалось сохранить",

  // generation queue
  "queue.title": "Очередь генерации",
  "queue.subtitle":
    "Выберите, что запустить, и нажмите «Старт». Подходят только выходные колонки с настроенным промптом.",
  "queue.columnsToRun": "Запустить для колонок",
  "queue.noOutputColumns":
    "Выходных колонок ещё нет. Сначала переключите колонку в «выход» в таблице, затем настройте промпт через значок шестерёнки.",
  "queue.noPrompt": "нет промпта",
  "queue.noPromptColumnsHint":
    "Выходных колонок без промпта: {count} — настройте через значок шестерёнки.",
  "queue.unmappedTitle": "У некоторых колонок не сопоставлены переменные промпта",
  "queue.unmappedItem": "{col}: {vars}",
  "queue.unmappedHint":
    "Сопоставьте каждую переменную промпта с колонкой (в настройках колонки) перед генерацией.",
  "queue.rows": "Строки",
  "queue.rowsAll": "Все строки ({count})",
  "queue.rowsSelected": "Выбранные строки ({count})",
  "queue.rowsSelectedNone":
    "Выбранные строки (в таблице ничего не отмечено)",
  "queue.rowsRange": "Диапазон:",
  "queue.fromRow": "со строки",
  "queue.toRow": "по",
  "queue.whichCells": "Какие ячейки",
  "queue.onlyEmpty": "Только пустые",
  "queue.onlyEmptyHint":
    "Пропускает ячейки, в которых уже есть сгенерированное значение.",
  "queue.onlyFailed": "Только с ошибкой",
  "queue.onlyFailedHint":
    "Повторяет ячейки, в которых последний запуск завершился ошибкой.",
  "queue.onlyTruncated": "Только обрезанные ячейки",
  "queue.onlyTruncatedHint":
    "Повторяет ячейки, которые достигли лимита токенов и вернулись неполными. Сначала увеличьте «Максимум токенов ответа», иначе они обрежутся снова.",
  "queue.allCells": "Все ячейки (перезаписать)",
  "queue.allCellsHint":
    "Запускает заново для каждой выбранной ячейки, заменяя существующие значения.",
  "queue.willGenerate":
    "Будет сгенерировано ячеек: {count} в колонках: {cols} × строках: {rows}.",
  "queue.using": "Используется: {variants}",
  "queue.usingOverride": "Переопределение: для каждой ячейки этого запуска — {provider} / {model}.",
  "queue.overrideLabel": "Переопределить провайдера и модель для этого запуска",
  "queue.overrideHint":
    "Принудительно использовать один и тот же провайдер/модель для всех ячеек, игнорируя настройки колонок — полезно для разовых A/B тестов или перезапусков.",
  "queue.overrideProvider": "Провайдер",
  "queue.overrideModel": "Модель",
  "queue.overrideNoKey": " (нет API-ключа)",
  "queue.workspaceDefault": "(значение по умолчанию)",
  "queue.defaultModel": "(модель по умолчанию)",
  "queue.failedToEnqueue": "Не удалось поставить в очередь",
  "queue.start": "Запустить генерацию",
  "queue.starting": "Запуск…",
  "queue.startWithCount": "Запустить генерацию ({count})",

  // CSV import (library)
  "csvImport.title": "Импорт CSV",
  "csvImport.subtitle":
    "Каждая колонка CSV становится входной колонкой. Выходные колонки и привязку промптов можно добавить после импорта.",
  "csvImport.tableName": "Название таблицы",
  "csvImport.tableNamePlaceholder": "напр., план статей на 2 квартал",
  "csvImport.csvFile": "CSV-файл",
  "csvImport.csvFiles": "CSV-файл(ы)",
  "csvImport.multiHint": "Выберите несколько файлов, чтобы создать по таблице на файл (каждая названа по имени файла).",
  "csvImport.willCreate": "Будет создано таблиц: {count}:",
  "csvImport.importN": "Импортировать таблиц: {count}",
  "csvImport.importingProgress": "Импорт {done}/{total}…",
  "csvImport.someFailed": "Не удалось импортировать некоторые файлы: {names}",
  "csvImport.delimiter": "Разделитель",
  "csvImport.delimiterComma": ", (запятая)",
  "csvImport.delimiterSemicolon": "; (точка с запятой)",
  "csvImport.delimiterTab": "табуляция",
  "csvImport.delimiterPipe": "| (вертикальная черта)",
  "csvImport.firstRowHeader": "Первая строка — заголовок",
  "csvImport.previewLabel": "Предпросмотр",
  "csvImport.downloadSample": "Скачать пример",
  "csvImport.sampleHint":
    "Не знаете, какие столбцы использовать? Скачайте пример CSV под ваш сценарий публикации. Для Custom CMS столбцы должны соответствовать плейсхолдерам body_template вашего домена.",
  "csvImport.sampleWpSingle": "WordPress — один сайт",
  "csvImport.sampleWpMulti": "WordPress — несколько сайтов",
  "csvImport.sampleCustomSingle": "Custom CMS — один сайт",
  "csvImport.sampleCustomMulti": "Custom CMS — несколько сайтов",

  // ---------- create / single ----------
  "create.title": "Создать",
  "create.subtitle": "Сгенерируйте контент по своим промптам.",
  "single.pickPrompt": "Выберите промпт",
  "single.savedGenerations": "Сохранённые генерации",
  "single.backToForm": "Назад к форме",
  "single.outputSubtitle":
    "Сохраните, опубликуйте или переведите результат. Возврат к форме сохраняет всё, что вы заполнили.",
  "single.selectToBegin":
    "Выберите промпт, чтобы начать, или откройте «Сохранённые генерации» сверху.",
  "single.variablesCount": "Переменных: {count}",
  "single.noVariables":
    "У этого промпта нет переменных — заполнять нечего.",
  "single.providerLabel": "Провайдер",
  "single.modelLabel": "Модель",
  "single.noProviderEnabled":
    "Нет включённых провайдеров. Настройте провайдера в разделе Настройки.",
  "single.providerNoKeyHint":
    "У этого провайдера нет API-ключа — задайте его в Настройках, чтобы включить.",
  "single.showPreview": "Показать предпросмотр промпта",
  "single.hidePreview": "Скрыть предпросмотр промпта",
  "single.willBeSent": "Что будет отправлено модели",
  "single.promptTemplateLabel": "Шаблон промпта",
  "single.unfilledVars": "Незаполненные переменные: {vars}",
  "single.generationFailed": "Ошибка генерации",
  "single.generate": "Сгенерировать",
  "single.generating": "Генерация…",
  "single.viewingSaved": "Просмотр сохранённой генерации:",
  "single.clear": "Сбросить",
  "single.generatedWith":
    "Сгенерировано через {provider} · {model}",
  "single.publishTo": "Опубликовать на…",
  "single.alreadySaved": "✓ Сохранено",
  "single.saveFailed": "Не удалось сохранить",
  "single.generatedContent": "Сгенерированный контент",

  // saved generations modal
  "saved.title": "Сохранённые генерации",
  "saved.onlyYours": "Здесь видны только ваши.",
  "saved.empty":
    "Вы ещё не сохраняли генерации. Нажмите «Сохранить» на результате, чтобы оставить его.",
  "saved.confirmDelete":
    "Удалить «{name}»? Это действие нельзя отменить.",
  "saved.searchPlaceholder": "Поиск по названию или промпту…",
  "saved.noMatches": "Нет сохранённых генераций по вашему запросу.",
  "saved.backToCreate": "← Назад к генератору",
  "saved.open": "Открыть",

  // publish to domain modal
  "pubMod.title": "Публикация на подключённый сайт",
  "pubMod.failedLoadDomains": "Не удалось загрузить домены",
  "pubMod.noneConnected":
    "Подключённых доменов пока нет. Добавьте домен в Публикация → Домены.",
  "pubMod.fieldDomain": "Домен",
  "pubMod.fieldLanguage": "Язык",
  "pubMod.fieldPostType": "Тип записи",
  "pubMod.noCreds": " — нет учётных данных",
  "pubMod.noFormConfigured":
    "Для этого домена ещё не настроена форма публикации — используются стандартные поля WordPress. Их можно настроить позднее в окне «Редактирование домена».",
  "pubMod.publish": "Опубликовать",
  "pubMod.publishing": "Публикация…",
  "pubMod.publishFailed": "Публикация не удалась",
  "pubMod.published": "Опубликовано.",
  "pubMod.viewPost": "Открыть запись →",
  "pubMod.warnings": "Предупреждения",
  "pubMod.required": "*",
  "pubMod.taxonomyHint":
    "Идентификаторы через запятую из таксономии «{tax}».",
  "pubMod.mediaHint":
    "Числовой ID вложения или ссылка (пока сохраняется как meta).",

  // published-to history
  "pubHist.loading": "Загрузка истории публикаций…",
  "pubHist.empty": "Пока нигде не опубликовано.",
  "pubHist.heading": "Опубликовано на",
  "pubHist.deletedDomain": "(удалённый домен)",
  "pubHist.viewArrow": "Открыть →",
  "pubHist.failedLoad": "Не удалось загрузить историю",

  // ---------- publish ----------
  "publish.tabDomains": "Домены",
  "publish.tabSingleRuns": "Одиночные публикации",
  "publish.tabBulkRuns": "Массовые публикации",
  "publish.tabLanguages": "Языки",
  "publish.tabAutotool": "Autotool",
  "publish.tabCacheRuns": "Кэш",

  // кэш доменов — массовая очистка/прогрев для сайтов Custom CMS
  "domains.bulkCache": "Очистить кэш…",
  "domains.bulkCacheHint": "Очистить кэш выбранных доменов Custom CMS",
  "cacheModal.title": "Очистка кэша",
  "cacheModal.subtitle": "Выбрано доменов: {count}",
  "cacheModal.customOnlyNote": "Действие применяется только к доменам Custom CMS. Домены WordPress и недоступные домены из выбора пропускаются автоматически.",
  "cacheModal.action_clear": "Очистить кэш",
  "cacheModal.action_warm": "Прогреть кэш",
  "cacheModal.action_clear_and_warm": "Очистить, затем прогреть",
  "cacheModal.actionHint_clear": "Сбросить кэш каждого сайта (/index.php?__clear_cache).",
  "cacheModal.run": "Запустить",
  "cacheRuns.heading": "Запуски кэша",
  "cacheRuns.toDomains": "← Домены",
  "cacheRuns.empty": "Запусков кэша пока нет. Выберите домены Custom CMS на вкладке «Домены» и нажмите «Кэш…».",
  "cacheRuns.colRun": "Запуск",
  "cacheRuns.colAction": "Действие",
  "cacheRuns.colStatus": "Статус",
  "cacheRuns.colProgress": "Прогресс",
  "cacheRuns.colCreated": "Создан",
  "cacheRun.runHash": "Запуск кэша #{id}",
  "cacheRun.failedShort": "ошибок: {count}",
  "cacheRun.back": "← Запуски кэша",
  "cacheRun.unsupportedSkipped": "пропущено: {count} (не Custom CMS)",
  "cacheRun.retryFailedHint": "Повторить {count} доменов с ошибкой в этом запуске",
  "cacheRun.retryFailed": "Повторить ошибки ({count})",
  "cacheRun.processed": "{done} / {total} обработано",
  "cacheRun.donePrefix": "✓ готово: {count}",
  "cacheRun.failedPrefix": "✗ ошибок: {count}",
  "cacheRun.skippedPrefix": "пропущено: {count}",
  "cacheRun.colDomain": "Домен",
  "cacheRun.colBaseUrl": "Базовый URL",
  "cacheRun.colStatus": "Статус",
  "cacheRun.colDetail": "Детали",
  "cacheRun.colTime": "Время",
  "cacheRun.empty": "В этом запуске нет доменов.",
  "cacheRun.clearCode": "очистка {code}",
  "cacheRun.warmCode": "прогрев {code}",

  // настройка подключения Autotool
  "autotoolCfg.title": "Autotool",
  "autotoolCfg.subtitle":
    "Подключение к внешнему прокси Autotool. Он забирает публичный CSV таблицы (включается кнопкой Autotool в bulk-таблице) и публикует его на ваши сайты.",
  "autotoolCfg.targetUrl": "Целевой URL",
  "autotoolCfg.targetUrlHint":
    "Эндпойнт Autotool ImportPosts, куда отправляются запросы.",
  "autotoolCfg.apiKey": "API-ключ (X-Api-Key)",
  "autotoolCfg.apiKeyConfigured": "Задан — введите новое значение для замены",
  "autotoolCfg.apiKeyPlaceholder": "Вставьте API-ключ Autotool",
  "autotoolCfg.apiKeyHint": "Хранится в зашифрованном виде; после сохранения не показывается.",
  "autotoolCfg.clearKey": "Удалить ключ",
  "autotoolCfg.undoClear": "Отменить",
  "autotoolCfg.clearKeyPending": "Сохранённый ключ будет удалён при сохранении.",
  "autotoolCfg.test": "Проверить",
  "autotoolCfg.testing": "Проверка…",
  "autotoolCfg.testHint": "Отправляет пробный запрос на сохранённый URL с сохранённым ключом.",
  "autotoolCfg.testNote":
    "Проверка использует сохранённые настройки — сначала сохраните, если только что их меняли. Она отправляет на эндпойнт ImportPosts пустой запрос: 401/403 означает, что ключ отклонён; любой другой ответ — прокси доступен и принял ключ.",
  "autotoolCfg.sharedHeading": "Таблицы в Autotool",
  "autotoolCfg.sharedSubtitle":
    "Таблицы, сейчас доступные Autotool. Можно посмотреть точный POST-запрос, который будет отправлен для каждой.",
  "autotoolCfg.sharedEmpty":
    "Пока ни одна таблица не отдана в Autotool. Включите кнопкой Autotool в bulk-таблице.",
  "autotoolCfg.rowsCols": "{rows} строк · {cols} колонок",
  "autotoolCfg.viewRequest": "Показать POST-запрос",
  "autotoolCfg.previewTitle": "POST-запрос — {name}",
  "autotoolCfg.noTarget": "Целевой URL не задан — настройте выше.",
  "autotoolCfg.noKey": "API-ключ не задан — настройте выше.",
  "autotoolCfg.siteColumn": "Колонка с сайтами",
  "autotoolCfg.siteColumnNone": "— нет —",
  "autotoolCfg.detected": "определена автоматически",
  "autotoolCfg.siteCount": "сайтов: {n}",
  "autotoolCfg.request": "Запрос",
  "autotoolCfg.copy": "Копировать",
  "autotoolCfg.keyMaskedNote":
    "X-Api-Key здесь скрыт; реальный ключ отправляется с запросом.",
  "autotoolCfg.close": "Закрыть",
  "autotoolCfg.splitSummary":
    "доменов: {domains} · файлов: {pages} · строк: {rows}",
  "autotoolCfg.unmatchedWarn":
    "У {n} строк нет значения в этой колонке — они не попадут ни в один файл.",
  "autotoolCfg.requestsHeading": "запросов: {n} · до {size} строк каждый",
  "autotoolCfg.copyAll": "Копировать все",
  "autotoolCfg.noDomains":
    "В выбранной колонке нет доменов — выберите колонку с целевыми сайтами.",
  "autotoolCfg.rowsForDomain": "строк: {n}",
  "autotoolCfg.pageRange": "строки {from}–{to} из {total}",
  "autotoolCfg.pageStart": "со строки {start}",
  "autotoolCfg.pageSizeLabel": "Строк в одном запросе",
  "autotoolCfg.pageSizeHint":
    "В каждом файле не больше этого числа строк, чтобы импортёр успел в своё окно (1–1000).",
  "autotoolCfg.copyCsvLink": "Копировать ссылку",
  "autotoolCfg.sendAll": "Отправить все ({n})",
  "autotoolCfg.sendConfirmWarn":
    "Будет отправлено {n} POST-запросов, и эти домены будут опубликованы на реальные сайты через Autotool. Продолжить?",
  "autotoolCfg.sendConfirm": "Отправить",
  "autotoolCfg.sending": "Запуск…",
  "autotoolCfg.sendNeedsConfig":
    "Сначала задайте целевой URL и API-ключ выше.",
  "autotoolCfg.viewRuns": "Запуски →",
  "autotoolCfg.startRun": "Запустить ({n})",

  // autotool runs — список
  "autotoolRuns.heading": "Запуски Autotool",
  "autotoolRuns.toConfig": "← Настройки Autotool",
  "autotoolRuns.empty": "Запусков пока нет. Начните из предпросмотра POST-запроса общей таблицы.",
  "autotoolRuns.colRun": "Запуск",
  "autotoolRuns.colTable": "Таблица",
  "autotoolRuns.colStatus": "Статус",
  "autotoolRuns.colProgress": "Прогресс",
  "autotoolRuns.colCreated": "Создан",

  // autotool runs — детали
  "autotoolRun.back": "← Все запуски",
  "autotoolRun.runHash": "Запуск №{id}",
  "autotoolRun.tableFallback": "Таблица №{id}",
  "autotoolRun.pageSizeLabel": "{size} строк/запрос",
  "autotoolRun.colId": "id Autotool",
  "autotoolRun.processed": "{done} / {total} запросов",
  "autotoolRun.sentPrefix": "отправлено: {count}",
  "autotoolRun.failedPrefix": "ошибок: {count}",
  "autotoolRun.failedShort": "ошибок: {count}",
  "autotoolRun.skippedPrefix": "пропущено: {count}",
  "autotoolRun.retryFailed": "Повторить ошибки ({count})",
  "autotoolRun.retryFailedHint": "Повторно отправить {count} стр. с ошибками в этом запуске.",
  "autotoolRun.colSite": "Сайт",
  "autotoolRun.colPage": "Страница",
  "autotoolRun.colStatus": "Статус",
  "autotoolRun.colDetail": "Детали",
  "autotoolRun.colTime": "Время",
  "autotoolRun.empty": "Нет элементов.",

  // domains page
  "domains.title": "Домены",
  "domains.subtitle":
    "Подключённые сайты, на которые можно публиковать.",
  "domains.selectedCount": "Выбрано: {count}",
  "domains.selectRow": "Выбрать {name}",
  "domains.moveToFolder": "В папку…",
  "domains.bulkDelete": "В корзину",
  "domains.confirmBulkDelete":
    "Переместить домены ({count}) в корзину? Восстановить можно из /publish/domains/trash.",
  "domains.bulkDeletePartial":
    "В корзину: {trashed}. Не удалось удалить: {blocked}:",
  "domains.selectAllMatchingPrompt":
    "Выбраны все {shown} на этой странице.",
  "domains.selectAllMatchingAction":
    "Выбрать все {total} по текущему фильтру",
  "domains.searchPlaceholder": "Поиск по названию или URL…",
  "domains.totalCount": "Всего: {count}",
  "domains.inFolder": "в {folder}",
  "domains.emptySearch": "Нет доменов по запросу {q}.",
  "domains.pageSizeLabel": "На странице:",
  "domains.pageOfTotal": "Стр. {page} из {total}",

  // folder tree on /publish/domains (migration 0027 redesign)
  "domainFolders.heading": "Папки",
  "domainFolders.newTopLevel": "Новая папка верхнего уровня",
  "domainFolders.allDomains": "Все домены",
  "domainFolders.root": "Корень (без папки)",
  "domainFolders.emptyHint": "Папок пока нет — нажмите + для создания.",
  "domainFolders.namePrompt": "Название папки:",
  "domainFolders.renamePrompt": "Новое название папки:",
  "domainFolders.confirmDelete":
    "Удалить папку {name}? Удалить можно только пустую папку.",
  "domainFolders.cardDomainCount": "Доменов: {count}",
  "domainFolders.cardDomainCountPlural": "Доменов: {count}",
  "domainFolders.cardSubfolderCount": "Подпапок: {count}",
  "domainFolders.cardSubfolderCountPlural": "Подпапок: {count}",
  "domainFolders.newFolderButton": "Новая папка",
  "domainFolders.foldersHeading": "Папки",
  "domainFolders.subfoldersHeading": "Подпапки",

  // move-to-folder modal
  "moveToFolder.title": "Переместить домены ({count}) в папку",
  "moveToFolder.subtitle":
    "Выберите назначение. «Корень» — убрать из всех папок.",
  "moveToFolder.root": "Корень (без папки)",
  "moveToFolder.noFolders":
    "Папок пока нет. Сначала создайте папку в боковой панели.",
  "moveToFolder.confirm": "Переместить",

  "common.clearSelection": "Сбросить выбор",
  "common.selectAll": "Выбрать все",
  "common.saveFailed": "Не удалось сохранить",

  "domains.import": "Импорт CSV",
  "domains.importJson": "Импорт JSON",
  "domains.importJsonHint":
    "Массовое создание доменов с полным вложенным publish_config (post-типы + поля). Используйте, когда плоских колонок CSV недостаточно.",
  "domainJson.title": "Импорт доменов из JSON",
  "domainJson.subtitle":
    "Вставьте или загрузите JSON-массив объектов. Каждый элемент — та же структура, что в POST /domains: вложенный publish_config (профили + поля) и custom_config поддерживаются. Лимит 500 элементов за вызов.",
  "domainJson.sample": "Пример (Site A, Site B, Custom Site)",
  "domainJson.sampleStart": "Разверните и используйте как отправную точку.",
  "domainJson.loadSample": "Загрузить пример в редактор",
  "domainJson.downloadSample": "Скачать пример",
  "domainJson.uploadLabel": "Загрузить .json-файл",
  "domainJson.pasteLabel": "Или вставьте JSON напрямую",
  "domainJson.parseOk": "Похоже на корректный JSON — {count} доменов готовы к импорту.",
  "domainJson.parseErr": "Не удалось распарсить: {detail}",
  "domainJson.errNotArray": "На верхнем уровне должен быть JSON-массив.",
  "domainJson.errEmpty": "Массив пуст.",
  "domainJson.errParse": "Не удалось распарсить JSON.",
  "domainJson.summary": "Импортировано: {inserted}, пропущено: {skipped}.",
  "domainJson.rowError": "Строка {row}: {detail}",
  "domains.add": "Добавить домен",
  "domains.colName": "Название",
  "domains.colBaseUrl": "Базовый URL",
  "domains.colCms": "CMS",
  "domains.colAuth": "Авторизация",
  "domains.colLanguages": "Языки",
  "domains.colPlugin": "Плагин",
  "domains.colTest": "Проверка",
  "domains.empty":
    "Доменов пока нет. Нажмите «Добавить домен», чтобы подключить.",
  "domains.noCreds": "(нет учётных данных)",
  "domains.testButton": "Проверить",
  "domains.testing": "Проверка…",
  "domains.testFailed": "Проверка не пройдена",

  // domain modal
  "domainMod.editTitle": "Редактирование домена: {name}",
  "domainMod.addTitle": "Добавить домен",
  "domainMod.fieldName": "Название",
  "domainMod.fieldBaseUrl": "Базовый URL",
  "domainMod.fieldCmsType": "Тип CMS",
  "domainMod.cmsWordpress": "WordPress",
  "domainMod.cmsCustom": "Custom (своя API)",
  "domainMod.fieldLanguages":
    "Языки (через запятую, первый — по умолчанию)",
  "domainMod.fieldMultilingual": "Плагин мультиязычности",
  "domainMod.pluginNone": "Нет (одноязычный)",
  "domainMod.pluginPolylang": "Polylang",
  "domainMod.pluginWpml": "WPML",
  "domainMod.fieldAppPassword":
    "Application Password («user:abcd efgh ijkl mnop»)",
  "domainMod.appPasswordHintEdit":
    "Оставьте пустым, чтобы сохранить текущий пароль. Введите значение, чтобы заменить.",
  "domainMod.publishForm": "Форма публикации",
  "domainMod.publishFormHint":
    "Один или несколько профилей публикации для сайта. Каждый профиль соответствует типу записи и имеет собственный набор полей — например, «Стандартная запись» и «Событие». При одиночной публикации профиль выбирается на этапе публикации.",
  "domainMod.unnamed": "(без имени)",
  "domainMod.addProfile": "+ Добавить профиль",
  "domainMod.fieldProfileName": "Название профиля",
  "domainMod.fieldPostType": "Тип записи",
  "domainMod.discoveredTypes":
    "Обнаружено типов на этом сайте: {count}.",
  "domainMod.discoveryFailed":
    "(Не удалось получить типы из /wp-json/wp/v2/types — введите slug вручную.)",
  "domainMod.deleteProfile": "Удалить этот профиль",
  "domainMod.fieldKey": "ключ (напр., title)",
  "domainMod.fieldLabel": "подпись",
  "domainMod.fieldType": "Тип",
  "domainMod.typeText": "Текст",
  "domainMod.typeTextarea": "Длинный текст",
  "domainMod.typeSelect": "Выпадающий список",
  "domainMod.typeTaxonomy": "ID таксономии",
  "domainMod.typeMedia": "Медиа (URL/ID)",
  "domainMod.required": "Обязательно",
  "domainMod.meta": "Meta",
  "domainMod.removeField": "Удалить поле",
  "domainMod.metaKeyPlaceholder":
    "meta_key (по умолчанию равен ключу)",
  "domainMod.optionsPlaceholder": "варианты (через запятую)",
  "domainMod.taxonomyPlaceholder":
    "slug таксономии (напр., categories, tags, news_category)",
  "domainMod.addField": "+ Добавить поле",
  "domainMod.fieldAuthType": "Тип авторизации",
  "domainMod.authBearer": "Bearer-токен",
  "domainMod.authApiKey": "API-ключ в заголовке",
  "domainMod.authBasic": "Логин + пароль (Basic auth)",
  "domainMod.fieldBearerToken": "Bearer-токен",
  "domainMod.bearerHintEdit":
    "Оставьте пустым, чтобы сохранить текущий токен.",
  "domainMod.bearerPlaceholder": "вставьте токен",
  "domainMod.fieldBasicCreds": "Логин : пароль",
  "domainMod.basicHint":
    "Формат: login:password (одна строка, одно двоеточие). Отправляется как HTTP Basic auth.",
  "domainMod.basicHintEdit":
    "Оставьте пустым, чтобы сохранить текущие учётные данные.",
  "domainMod.fieldHeaderName": "Имя заголовка",
  "domainMod.fieldHeaderValue": "Значение заголовка",
  "domainMod.headerValueHintEdit":
    "Оставьте пустым, чтобы сохранить текущее значение.",
  "domainMod.headerValuePlaceholder": "вставьте ключ",
  "domainMod.fieldEndpointPath": "Путь эндпоинта",
  "domainMod.fieldBodyTemplate":
    "Шаблон тела (JSON, с {{плейсхолдерами}})",
  "domainMod.fieldResponseIdPath":
    "Путь к ID в ответе (напр., id, data.id)",
  "domainMod.fieldResponseUrlPath": "Путь к URL в ответе",
  "domainMod.rateLimits": "Лимиты запросов",
  "domainMod.rateLimitsHint":
    "Переопределения для домена. Оставьте поле пустым, чтобы использовать глобальное значение из Настройки → Параметры публикации по умолчанию.",
  "domainMod.rateRpm": "Запросов в минуту",
  "domainMod.rateMaxConc": "Макс. параллельных запросов",
  "domainMod.rateDelay": "Задержка между запросами (мс)",
  "domainMod.rateRetry": "Максимум повторов",
  "domainMod.rateBackoff": "Базовая задержка отката (мс)",
  "domainMod.rateJitter": "Случайный разброс отката (мс)",
  "domainMod.respectRetryAfter": "Учитывать заголовок Retry-After",
  "domainMod.inheritPlaceholder": "наследовать",
  "domainMod.inheritOption": "наследовать (глобальное значение)",
  "domainMod.optYes": "да",
  "domainMod.optNo": "нет",
  "domainMod.mediaCache": "Кэш загрузок медиа",
  "domainMod.mediaCacheHint":
    "Когда массовый запуск ссылается на один и тот же URL изображения для многих строк, мы загружаем его в медиатеку этого сайта один раз и переиспользуем ID. Очистите кэш, если на стороне WP вы удалили медиа и хотите, чтобы дальнейшие публикации загружали их заново.",
  "domainMod.cachedEntries": "Записей в кэше:",
  "domainMod.clearCache": "Очистить кэш",
  "domainMod.clearing": "Очистка…",
  "domainMod.clearedCount":
    "Очищено записей в кэше: {count}.",
  "domainMod.clearCacheConfirm":
    "Очистить кэш загрузок медиа для этого домена? В дальнейшем изображения будут загружаться заново, даже если URL источника тот же.",
  "domainMod.clearCacheFailed": "Не удалось очистить",
  "domainMod.dupeProfile":
    "Имя профиля «{name}» повторяется. Имена профилей должны быть уникальны.",
  "domainMod.dupeFieldKeys":
    "В профиле «{name}» повторяются ключи полей: {keys}",
  "domainMod.bothApiKeyRequired":
    "Для авторизации по API-ключу нужны и имя заголовка, и значение",
  "domainMod.invalidJson":
    "Неверный JSON в шаблоне тела: {message}",
  "domainMod.invalidJsonGeneric":
    "Неверный JSON в шаблоне тела",
  "domainMod.bodyMustBeObject":
    "body_template должен быть JSON-объектом",

  // domain CSV import
  "domainCsv.title": "Импорт доменов из CSV",
  "domainCsv.requiredColumns": "Обязательные колонки:",
  "domainCsv.customColumns": "Для Custom CMS также (в каждой строке):",
  "domainCsv.sampleHint":
    "Скачайте готовый шаблон для вашей CMS и типа сайта, впишите свои домены и загрузите файл.",
  "domainCsv.downloadSample": "Скачать шаблон",
  "domainCsv.sampleWp": "Сайты WordPress",
  "domainCsv.sampleCustom": "Сайты Custom CMS",
  "domainCsv.pickFirst": "Сначала выберите CSV-файл",
  "domainCsv.summary":
    "Добавлено: {inserted}; пропущено: {skipped}.",
  "domainCsv.rowError": "Строка {row}: {detail}",

  // publish history (single runs)
  "pubHistory.title": "История публикаций",
  "pubHistory.subtitle":
    "Попыток: {count}, по одиночному и массовому режимам.",
  "pubHistory.colTime": "Время",
  "pubHistory.colDomain": "Домен",
  "pubHistory.colSlug": "Слаг",
  "pubHistory.colProfile": "Профиль",
  "pubHistory.colStatus": "Статус",
  "pubHistory.httpCodeTip": "HTTP-код ответа CMS",
  "pubHistory.colLang": "Язык",
  "pubHistory.colPost": "Запись",
  "pubHistory.colError": "Ошибка / предупреждения",
  "pubHistory.empty":
    "Попыток публикации пока нет. Попробуйте кнопку «Опубликовать на…» в одиночной генерации.",
  "pubHistory.deletedDomain": "(удалён)",

  // bulk runs
  "bulkRuns.title": "Массовые публикации",
  "bulkRuns.subtitle":
    "Запускаются из массовой таблицы → «Массовая публикация…». Откройте запуск, чтобы увидеть результаты по строкам и поставить на паузу/возобновить/отменить.",
  "bulkRuns.colStarted": "Запущено",
  "bulkRuns.colTable": "Таблица",
  "bulkRuns.colDomain": "Домен",
  "bulkRuns.colProfile": "Профиль",
  "bulkRuns.colStatus": "Статус",
  "bulkRuns.colProgress": "Прогресс",
  "bulkRuns.empty": "Массовых запусков пока нет.",
  "bulkRuns.tableFallback": "Таблица №{id}",
  "bulkRuns.failedSuffix": "(ошибок: {count})",
  "bulkRuns.colLang": "Язык",
  "bulkRuns.perRowLang": "из колонки",
  "bulkRuns.perRowLangHint": "Каждая строка читает язык из колонки таблицы.",
  "bulkRuns.multiDomain": "несколько сайтов",
  "bulkRuns.multiDomainHint": "Каждая строка публикуется в домен из колонки — единого адреса нет.",
  "bulkRun.colLang": "Язык",
  "bulkRuns.clearCompleted": "Очистить завершённые",
  "bulkRuns.clearCompletedConfirm":
    "Удалить все завершённые прогоны (done / failed / cancelled) и их задачи публикации? Это действие необратимо.",
  "bulkRuns.clearCompletedResult": "Удалено прогонов: {count}.",
  "bulkRuns.deleteRow": "Удалить",
  "bulkRuns.deleteConfirm":
    "Удалить прогон #{id} и его задачи публикации? Это действие необратимо.",
  "bulkRuns.colActions": "",
  "pubHistory.clearCompleted": "Очистить завершённые",
  "pubHistory.clearCompletedConfirm":
    "Удалить все завершённые задачи публикации (posted / failed)? Это действие необратимо.",
  "pubHistory.clearCompletedResult": "Удалено задач: {count}.",
  "pubHistory.deleteRow": "Удалить",
  "pubHistory.deleteConfirm":
    "Удалить эту задачу публикации? Это действие необратимо.",
  "pubHistory.colActions": "",

  // bulk run detail
  "bulkRun.back": "← Назад к запускам",
  "bulkRun.runHash": "Запуск №{id}",
  "bulkRun.pause": "Пауза",
  "bulkRun.resume": "Возобновить",
  "bulkRun.rerunFailed": "Перезапустить ошибки ({count})",
  "bulkRun.rerunFailedHint":
    "Запустить новый прогон только для строк с ошибкой ({count})",
  "bulkRun.rerunFailedFailed": "Перезапуск не удался",
  "bulkRun.copyUrls": "Копировать URL",
  "bulkRun.copyUrlsHint": "Скопировать все опубликованные URL ({count}) в буфер обмена",
  "bulkRun.copiedUrls": "Скопировано: {count}",
  "bulkRun.noUrls": "Пока нет опубликованных URL.",
  "bulkRun.failedToLoad": "Не удалось загрузить запуск",
  "bulkRun.processed": "{done} / {total} обработано",
  "bulkRun.donePrefix": "✓ {count} готово",
  "bulkRun.failedPrefix": "✗ {count} с ошибкой",
  "bulkRun.skippedPrefix": "{count} пропущено",
  "bulkRun.colTime": "Время",
  "bulkRun.colRow": "Строка",
  "bulkRun.colSlug": "Слаг",
  "bulkRun.slugEmpty": "(пусто)",
  "bulkRun.colDomain": "Сайт",
  "bulkRun.colProfile": "Профиль",
  "bulkRun.colStatus": "Статус",
  "bulkRun.httpCodeTip": "HTTP-код ответа CMS",
  "bulkRun.colPost": "Запись",
  "bulkRun.colError": "Ошибка / предупреждения",
  "bulkRun.colRequest": "Запрос",
  "bulkRun.viewRequest": "curl",
  "bulkRun.requestTitle": "Запрос для задачи #{id}",
  "bulkRun.copyCurl": "Копировать curl",
  "bulkRun.requestNone": "Для этой строки запрос ещё не отправлялся (в очереди или не удалось определить цель).",
  "bulkRun.responseStatus": "Ответ: HTTP {code}",
  "bulkRun.responseBody": "Тело ответа",
  "bulkRun.empty": "Результатов по строкам пока нет.",
  "bulkRun.viewLink": "Открыть",
  "bulkRun.modeSingle": "Один сайт",
  "bulkRun.modeMulti": "Несколько сайтов",
  "bulkRun.opUpdate": "Update",
  "bulkRun.opUpdateHint":
    "Прогон обновляет существующие посты (поиск по {kind}). Поля с пустыми ячейками остаются без изменений.",
  "bulkRun.perRowLang": "Язык из колонки",
  "bulkRun.perRowLangHint":
    "Язык каждой строки берётся из колонки таблицы, а не из общего параметра прогона.",
  "bulkRun.acrossDomains": "по {count} сайтам",
  "bulkRun.byDomainHeading": "По сайтам ({count})",
  "bulkRun.colTotal": "Всего",
  "bulkRun.colPosted": "Опубликовано",
  "bulkRun.colFailed": "С ошибкой",
  "bulkRun.unresolved": "(не определён)",
  "bulkRun.allFailed": "все упали",
  "bulkRun.allFailedHint": "Все строки на этот сайт завершились ошибкой — проверьте сначала учётные данные и доступность.",
  "bulkRun.filter": "Фильтр",
  "bulkRun.filterAll": "все",
  "bulkRun.filterDomain": "Сайт",
  "bulkRun.filterStatus": "Статус",
  "bulkRun.clearFilters": "Сбросить фильтры",

  // bulk publish modal
  "bulkPub.title": "Массовая публикация",
  "bulkPub.subtitle":
    "Каждая строка таблицы {table} становится отдельной записью. Сопоставьте поля публикации с колонками; при необходимости укажите колонки, в которые будут записаны новый ID и URL записи.",
  "bulkPub.cmsType": "Тип CMS",
  "bulkPub.cmsTypeWordPress": "WordPress",
  "bulkPub.cmsTypeCustom": "Custom CMS",
  "bulkPub.cmsTypeWordPressHint":
    "Показать настройки для WordPress (профили, Создать/Обновить, поиск, конфликт slug). В списке доменов ниже будут только WordPress-сайты.",
  "bulkPub.cmsTypeCustomHint":
    "Показать настройки для Custom CMS. В списке доменов ниже будут только Custom-CMS-сайты.",
  "bulkPub.noDomainsForType":
    "нет доменов этого типа CMS — добавьте в /publish/domains или переключите тип выше",
  "domainCombo.placeholder": "Поиск доменов по названию или URL…",
  "domainCombo.loading": "Загрузка…",
  "domainCombo.loadFailed": "Не удалось загрузить домены",
  "domainCombo.noMatches": "Нет доменов по запросу {q}",
  "domainCombo.noDomainsForType":
    "Нет доменов этого типа CMS. Добавьте в /publish/domains.",
  "domainCombo.noCreds": "нет ключей",
  "domainCombo.refineHint": "Показано {shown} из {total} — введите для фильтрации.",
  "bulkPub.opUpsert": "Upsert",
  "bulkPub.customCreateHint":
    "Отправляется action=create. Слаг, заголовок, контент (и любые другие поля body_template) создают новую страницу на сайте.",
  "bulkPub.customUpdateHint":
    "Отправляется action=update. Укажите колонку с upstream id строки в разделе «Найти существующие записи по»; остальные сопоставленные поля будут обновлены на странице (включая новый slug, если переименовываете).",
  "bulkPub.customUpsertHint":
    "Отправляется action=upsert. Сервер ищет страницу по slug — если нашёл, обновляет; если нет, создаёт новую. Переименовать slug через upsert нельзя — используйте Update.",
  "bulkPub.upsertCustomOnly":
    "Upsert поддерживается только для Custom CMS. Для WordPress используйте Create или Update.",
  "bulkPub.customUpdateNeedsId":
    "Для Update в Custom CMS укажите колонку с id в разделе «Найти существующие записи по».",
  "bulkPub.customLookupHint":
    "Выберите колонку с upstream id записи. Переименовываете slug? Сопоставьте новый slug отдельно в разделе «Поля для записи» ниже — поиск идёт по id, тело отправляется с новым slug.",
  "bulkPub.customLookupSlugDisabled":
    "Поиск по slug сервером пока не поддерживается — endpoint __add_content не принимает параметр old_slug. Используйте поиск по id; вы всё равно можете переименовать slug, указав его в «Поля для записи».",
  "bulkPub.pageType": "Тип страницы",
  "bulkPub.pageTypeOrdinary": "Обычная",
  "bulkPub.pageTypeMatch": "Матч",
  "bulkPub.pageTypeOrdinaryHint":
    "Обычная страница — использует endpoint и шаблон тела каждого целевого сайта.",
  "bulkPub.pageTypeMatchHint":
    "Спортивная страница матча с набором полей матча (lang, дата, время, площадка, группа, кэфы, top). Создание публикуется на {createEndpoint}; Обновление — на {updateEndpoint} (укажите колонку id в «Найти существующие записи по»). Сопоставьте колонку языка с полем lang для языка по строкам, иначе все строки используют язык всего прогона. Поле «top» принимает текст true/false и отправляется как булево значение.",
  "bulkPub.mode": "Режим",
  "bulkPub.modeSingle": "Один сайт",
  "bulkPub.modeMulti": "Несколько сайтов",
  "bulkPub.modeSingleHint":
    "Все строки этого запуска отправляются на один домен и в один профиль (тип записи).",
  "bulkPub.modeMultiHint":
    "Каждая строка читает целевой сайт (и при желании — профиль) из колонок таблицы. Подходит для сетей сателлитов: одна таблица содержит контент для множества сайтов.",
  "bulkPub.fieldDomain": "Домен",
  "bulkPub.fieldDomainColumn": "Колонка с доменом",
  "bulkPub.fieldProfileColumn": "Колонка с профилем (необязательно)",
  "bulkPub.profileColumnDefault": "— использовать профиль по умолчанию для каждого домена —",
  "bulkPub.profileColumnHint":
    "Если задано — каждая строка берёт имя профиля из этой колонки. Имя должно совпадать с настроенным на целевом домене.",
  "bulkPub.fieldLanguageColumn": "Колонка с языком (необязательно)",
  "bulkPub.languageColumnDefault": "— использовать язык всего прогона —",
  "bulkPub.languageColumnHint":
    "Если задано — каждая строка берёт язык из этой колонки (регистр не важен). Значение должно совпадать с одним из языков, настроенных на целевом домене. Пустая ячейка → строка падает. Если включаете эту колонку — заполните её во всех строках.",
  "bulkPub.pickColumn": "— выберите колонку —",
  "bulkPub.fieldPostType": "Тип записи",
  "bulkPub.fieldLanguage": "Язык",
  "bulkPub.rows": "Строки",
  "bulkPub.rowsAll": "Все ({count})",
  "bulkPub.rowsSelected": "Выбранные ({count})",
  "bulkPub.rowsRange": "Диапазон",
  "bulkPub.cellFilter": "Фильтр по ячейкам",
  "bulkPub.cellAll": "Все (перезаписать)",
  "bulkPub.cellUnpublished": "Только неопубликованные",
  "bulkPub.cellFailed": "Только с ошибкой",
  "bulkPub.cellNeedTarget":
    "Фильтры «Только неопубликованные/с ошибкой» работают по колонке обратной записи. Чтобы их включить, выберите колонку для «Колонка для ID записи» ниже.",
  "bulkPub.mapHeading": "Сопоставление полей публикации с колонками",
  "bulkPub.clearMapping": "Очистить сохранённое сопоставление",
  "bulkPub.skip": "— пропустить —",
  "bulkPub.noFieldsDetected":
    "Для этого назначения не обнаружено полей публикации. Для Custom CMS в шаблоне тела должны быть значения {{плейсхолдеров}}; для WP — настройте форму публикации на домене.",
  "bulkPub.noFieldsCustomEmpty":
    "В шаблоне тела домена {name} нет {{плейсхолдеров}}, сопоставлять нечего. Отредактируйте домен в /publish/domains, добавив плейсхолдеры, либо выберите другой домен в поиске выше.",
  "bulkPub.backFill": "Колонки для обратной записи (необязательно)",
  "bulkPub.backFillHint":
    "После каждой успешной публикации новый ID и URL записи записываются в указанные колонки массовой таблицы.",
  "bulkPub.postIdTarget": "Колонка для ID записи",
  "bulkPub.postUrlTarget": "Колонка для URL записи",
  "bulkPub.backFillNone": "— нет —",
  "bulkPub.remember":
    "Запомнить это сопоставление для будущих запусков на это назначение",
  "bulkPub.willPublish": "Будет опубликовано строк: {count}.",
  "bulkPub.willPublishAcross": "Будет опубликовано строк: {count} по {domains} сайтам.",
  "bulkPub.willUpdate": "Будет обновлено существующих постов: {count}.",
  "bulkPub.willUpdateAcross": "Будет обновлено постов: {count} по {domains} сайтам.",
  "bulkPub.operation": "Операция",
  "bulkPub.opCreate": "Создать",
  "bulkPub.opUpdate": "Обновить",
  "bulkPub.opCreateHint": "Публикация новых постов. Каждая строка создаёт пост.",
  "bulkPub.opUpdateHint":
    "Обновление существующих постов. Для каждой строки ищется существующий пост (по id или slug) и патчится. Только для WordPress.",
  "bulkPub.lookupKind": "Искать пост по",
  "bulkPub.lookupKindId": "ID поста",
  "bulkPub.lookupKindSlug": "Slug",
  "bulkPub.lookupColumn": "Колонка для поиска",
  "bulkPub.lookupColumnPlaceholder": "выберите колонку",
  "bulkPub.lookupHintId":
    "Ячейка в каждой строке должна быть числовым ID поста WordPress. Строки с нечисловым/пустым значением упадут.",
  "bulkPub.lookupHintSlug":
    "Ячейка содержит slug поста WordPress. Принимаются также полные URL — slug берётся как последний сегмент пути, так что колонку cms_post_url можно использовать для поиска. Ищется по постам любых статусов.",
  "bulkPub.updateBlankHint":
    "Поля с пустыми ячейками не отправляются — на стороне WP они остаются без изменений. Маппьте только то, что хотите перезаписать.",
  "bulkPub.updateWpOnly":
    "Update-режим работает только с WordPress. {name} — не WP-домен; выберите WP-домен или переключитесь на Create.",
  "bulkPub.updateLookupRequired":
    "Выберите колонку, в которой лежит id или slug существующего поста — без неё Update нельзя запустить.",
  "bulkPub.updateMapAtLeastOne":
    "Нужно замаппить хотя бы одно поле на колонку — иначе в PATCH нечего отправлять.",
  "bulkPub.startUpdate": "Запустить обновление ({count})",
  "bulkPub.onSlugConflict": "Если slug уже занят",
  "bulkPub.onSlugCreate": "Создать всё равно",
  "bulkPub.onSlugSkip": "Пропустить",
  "bulkPub.onSlugUpdate": "Обновить существующий",
  "bulkPub.onSlugCreateHint":
    "По умолчанию. POST для каждой строки. Если slug совпал на той же языке, WordPress автоматически добавит суффикс ('canada' → 'canada-2').",
  "bulkPub.onSlugSkipHint":
    "Перед каждой строкой проверяем WP на наличие поста с таким slug в языке этой строки. Если есть — статус 'skipped', не публикуем. +1 GET на строку. Polylang/WPML: проверка по языку — EN 'canada' НЕ блокирует новый RU 'canada'.",
  "bulkPub.onSlugUpdateHint":
    "Upsert. Если пост с таким slug есть (в языке строки) — PATCH; иначе — POST нового. Поля с пустыми ячейками не меняют существующее. +1 GET на строку.",
  "bulkPub.slugConflictNeedsSlug":
    "Этот режим требует, чтобы поле 'slug' было сопоставлено с колонкой.",
  "bulkRun.onSlugSkip": "Skip dupes",
  "bulkRun.onSlugSkipHint":
    "Строки с уже существующим slug помечаются как skipped (по языкам).",
  "bulkRun.onSlugUpsert": "Upsert",
  "bulkRun.onSlugUpsertHint":
    "Строки с уже существующим slug обновляют существующий пост вместо создания нового (по языкам).",
  "bulkPub.andMore": "…и ещё {count}",

  // Pre-flight language sync (Multi-mode bulk publish, Custom CMS)
  "langSync.title": "Сначала синхронизируйте языки на сайтах",
  "langSync.subtitle":
    "Отправьте на каждый сайт набор языков, который ему нужен (берётся из таблицы). Уже существующие языки игнорируются — это безопасно.",
  "langSync.syncButton": "Отправить на {count} сайт(а)",
  "langSync.syncing": "Отправка…",
  "langSync.summary":
    "Готово — {ok} ок, {fail} с ошибкой, {skip} пропущено",
  "langSync.skipped": "Пропущено",
  "langSync.viewThisRun": "Открыть этот прогон →",
  "langSync.viewHistory": "История прогонов",

  // Standalone language-sync page (/publish/languages)
  "langPage.title": "Языки",
  "langPage.subtitle":
    "Отправка наборов языков на Custom CMS-сайты. История всех прогонов хранится здесь.",
  "langPage.newSync": "Новая синхронизация",
  "langPage.newSyncTitle": "Запустить новую синхронизацию",
  "langPage.newSyncHint":
    "Выберите Custom CMS-домен и впишите языки для upsert (через запятую или по одному на строку).",
  "langPage.fieldDomain": "Целевой домен",
  "langPage.fieldDomains": "Целевые домены",
  "langPage.fieldLanguages": "Языки",
  "langPage.languagesPlaceholder": "en, es, fr — или по одному на строку",
  "langPage.overridePerSite": "Свой набор языков для каждого сайта",
  "langPage.chipRemove": "Убрать",
  "langPage.willApplyToCount":
    "Будут отправлены [{langs}] на {count} сайт(ов).",
  "langPage.willSyncCount": "Будет {count} сайт(ов) в одном прогоне.",
  "langPage.importCsv": "Импорт CSV…",

  // CSV import modal for language sync
  "langCsv.title": "Импорт сайтов и языков из CSV",
  "langCsv.subtitle":
    "Загрузите CSV, чтобы заполнить форму сразу до 500 сайтов. Каждая строка станет отдельным чипом со своим набором языков.",
  "langCsv.hint":
    "Формат: два столбца — `domain` и `languages`. Языки можно перечислять через запятую, пробел или точку с запятой внутри ячейки. Заголовок необязателен.",
  "langCsv.downloadSample": "Скачать образец CSV",
  "langCsv.fileLabel": "CSV-файл",
  "langCsv.validating": "Проверка имён доменов…",
  "langCsv.previewTitle": "Готово к применению — распознано сайтов: {count}",
  "langCsv.applyButton": "Применить к форме",
  "langCsv.errorRead": "Не удалось прочитать файл: {err}",
  "langCsv.errorEmpty": "CSV-файл пуст.",
  "langCsv.errorNoRows": "В CSV не найдено пригодных строк.",
  "langCsv.errorRowShape": "Строка {line}: ожидается 2 столбца, получено {cols}.",
  "langCsv.errorRowEmptyDomain": "Строка {line}: ячейка domain пуста.",
  "langCsv.errorRowEmptyLangs":
    "Строка {line} ({domain}): ячейка languages пуста.",
  "langCsv.errorUnknown":
    "Имён доменов нет в /publish/domains — импорт отклонён ({count}):",
  "langCsv.errorUnknownFix":
    "Исправьте CSV (переименуйте или удалите эти строки) и загрузите снова. Ничего не отправлено.",
  // Multi-domain picker (popover with search + checkboxes)
  "multiPicker.openEmpty": "Выберите Custom CMS-домены…",
  "multiPicker.openWithCount": "Выбрано: {count}",
  "multiPicker.searchPlaceholder": "Поиск доменов по имени…",
  "multiPicker.loading": "Загрузка…",
  "multiPicker.empty": "Подходящих доменов нет.",
  "multiPicker.noCreds": "без ключей",
  "multiPicker.tickedCount": "Отмечено: {count}",
  "multiPicker.apply": "Применить",
  "multiPicker.cancel": "Отмена",
  "langPage.cancel": "Отмена",
  "langPage.startSync": "Синхронизировать",
  "langPage.runningSync": "Отправка…",
  "langPage.historyTitle": "Прошлые прогоны",
  "langPage.historyEmpty": "Прогонов пока нет — запустите из модалки массовой публикации или с этой страницы.",
  "langPage.colWhen": "Когда",
  "langPage.colBy": "Кто",
  "langPage.colSource": "Источник",
  "langPage.colTotals": "Счётчики",
  "langPage.colActions": "",
  "langPage.viewLink": "Открыть",
  "langPage.sourceBulkModal": "Модалка публикации",
  "langPage.sourceStandalone": "Со страницы",
  "langPage.runTitle": "Прогон #{id}",
  "langPage.runBack": "← К списку прогонов языков",
  "langPage.runMeta": "{date} · автор: {by} · {source}",
  "langPage.runCounts": "{total} всего · {ok} ок · {fail} с ошибкой · {skip} пропущено",
  "langPage.resultDomain": "Домен",
  "langPage.resultLanguages": "Языки",
  "langPage.resultStatus": "Статус",
  "langPage.resultDetail": "Детали",
  "langPage.resultElapsed": "Время",
  "langPage.resultOk": "ок",
  "langPage.resultFail": "с ошибкой",
  "langPage.resultSkipped": "пропущено",
  "langPage.resultPending": "в очереди",
  "langPage.statusActive": "идёт",
  "langPage.runStatusQueued": "В очереди",
  "langPage.runStatusRunning": "Выполняется",
  "langPage.runStatusDone": "Готово",
  "langPage.runProgress": "Обработано {done}/{total} сайтов…",
  "langPage.runRetryFailed": "Повторить неудачные ({n})",
  "langPage.runResume": "Возобновить",
  "langPage.runResumeHint": "Перезапустить, если прогон завис (рестарт воркера)",
  "bulkPub.missingRequired":
    "Не выбрана колонка для обязательных полей: {fields}",
  "bulkPub.noRowsSelected": "Не выбрано ни одной строки.",
  "bulkPub.failedToStart": "Не удалось запустить",
  "bulkPub.confirmClearMapping":
    "Очистить сохранённое сопоставление для этого назначения?",
  "bulkPub.start": "Запустить ({count})",
  "bulkPub.starting": "Запуск…",

  // HTML viewer
  "htmlViewer.title": "Вывод",
  "htmlViewer.preview": "Предпросмотр",
  "htmlViewer.raw": "Сырой текст",
  "htmlViewer.words": "слов: {n}",
  "htmlViewer.wordsHint": "Количество слов в видимом тексте (без HTML-тегов и комментариев)",
  "htmlViewer.openWindow": "Открыть в новом окне",
  "htmlViewer.tooLarge":
    "Содержимое слишком велико для встроенного предпросмотра.",
  "htmlViewer.openInWindow": "открыть в новом окне",
  "htmlViewer.copyAction": "скопировать",

  // ---------- стоимость генерации текста ----------
  "cellCost.value": "{usd} за генерацию",
  "cellCost.notPriced": "тариф для модели не задан",
  "cellCost.hint": "{model} · токенов: {inTok} вход / {outTok} выход · {when}",

  // ---------- публичные ссылки для просмотра ----------
  "share.button": "Поделиться",
  "share.buttonShared": "Ссылка создана",
  "share.buttonHint":
    "Создать ссылку только для чтения — аккаунт не нужен",
  "share.panelHint":
    "Любой, у кого есть эта ссылка, сможет прочитать текст до {date}. Всегда показывается актуальная версия.",
  "share.revoke": "Отозвать",
  "share.confirmRevoke":
    "Отозвать ссылку? Все, у кого она есть, сразу потеряют доступ.",
  "share.pageEyebrow": "Общий просмотр",
  "share.rowNumber": "· строка {n}",
  "share.notFound":
    "Ссылка больше недоступна — возможно, истёк срок действия или её отозвали.",
  "share.loadFailed": "Не удалось загрузить просмотр. Попробуйте ещё раз.",
  "share.footerNote":
    "Просмотр только для чтения · ссылка действует до {date}",

  // user chip
  "userChip.tooltip": "Создал: {name}",

  // ----- Прогресс bulk-генерации + страница деталей (миграция 0030) -----
  "genBanner.generating": "Генерация {done}/{total}",
  "genBanner.failedCount": "Ошибок: {n}",
  "genBanner.skippedCount": "Отменено: {n}",
  "genBanner.details": "Подробнее →",
  "genBanner.cancel": "Отменить",
  "genBanner.cancelConfirm":
    "Отменить генерацию? Незавершённые ячейки получат статус «Отменено».",
  "genBanner.recover": "Восстановить",
  "genBanner.recoverTitle":
    "Похоже, генерация зависла. Принудительно вернуть застрявшие ячейки, чтобы повторить их.",
  "genBanner.recovered":
    "Восстановлено ячеек: {n}. Повторите их через «Только ошибки».",
  "genBanner.recoverNoop": "Нечего восстанавливать — генерация ещё идёт.",

  "genRun.title": "Генерация #{id}",
  "genRun.meta": "Запустил: {by} · {when}",
  "genRun.backToTable": "← Назад к таблице",
  "genRun.cancel": "Отменить",
  "genRun.cancelConfirm":
    "Отменить генерацию? Незавершённые ячейки получат статус «Отменено».",
  "genRun.counters": "{done} из {total} ячеек",
  "genRun.colDone": "Готово",
  "genRun.colFailed": "Ошибка",
  "genRun.colSkipped": "Отменено",
  "genRun.elapsed": "Время: {elapsed}",
  "genRun.statusQueued": "В очереди",
  "genRun.statusRunning": "Идёт",
  "genRun.statusDone": "Готово",
  "genRun.statusCancelled": "Отменено",
  "genRun.statusFailed": "Сбой",

  // ---------- контент-инструменты (под таблицей) ----------
  "tools.heading": "Инструменты контента",
  "tools.findReplace.title": "Найти и заменить",
  "tools.findReplace.desc":
    "Поиск и массовая замена текста в ячейках. Поддержка regex; замены можно откатить.",
  "tools.structureFormat.title": "Структура и форматирование",
  "tools.structureFormat.desc":
    "Чистка вывода ИИ: markdown→HTML, удаление мусора в начале, инлайн-CSS и жирный/курсив.",
  "tools.normalize.title": "Нормализация",
  "tools.normalize.desc":
    "Приведение значений ячеек: убрать пробелы, схему URL и слэши, нижний регистр. Откатывается.",

  // ---------- пагинация ----------
  "pager.showing": "Показано {from}–{to} из {total}",
  "pager.prev": "Назад",
  "pager.next": "Вперёд",
  "pager.pageOf": "Страница {page} из {total}",

  // ---------- найти и заменить ----------
  "findReplace.backToTable": "← Назад к таблице",
  "findReplace.title": "Найти и заменить",
  "findReplace.onTable": "В таблице «{name}»",
  "findReplace.modeFind": "Найти",
  "findReplace.modeReplace": "Заменить",
  "findReplace.patternLabel": "Найти",
  "findReplace.patternPlaceholder":
    "По одному значению в строке, напр.\nкот\nООО «Ромашка»",
  "findReplace.replacementLabel": "Заменить на",
  "findReplace.replacementPlaceholder":
    "По одной в строке, в пару к «Найти», напр.\nпёс\nGlobex",
  "findReplace.optRegex": "Regex",
  "findReplace.optCase": "Учитывать регистр",
  "findReplace.optWholeCell": "Вся ячейка",
  "findReplace.columnsLabel": "Колонки для поиска",
  "findReplace.allColumns": "Все колонки",
  "findReplace.findBtn": "Найти",
  "findReplace.previewBtn": "Показать совпадения",
  "findReplace.replaceBtn": "Заменить всё →",
  "findReplace.multiHint":
    "По одному значению в строке. Строка N в «Найти» заменяется строкой N в «Заменить»; оставьте «Заменить» пустым, чтобы удалить все термины. Каждый термин применяется к исходному тексту, поэтому результат одного правила не подхватывается другим.",
  "findReplace.pairOk": "{n} пар найти → заменить",
  "findReplace.pairDeleteAll": "Удаление {finds} термин(ов)",
  "findReplace.mismatchError":
    "{finds} строк(и) в «Найти», но {replaces} в «Заменить» — количество должно совпадать (оставьте «Заменить» пустым, чтобы удалить все термины).",
  "findReplace.morePairs": "+ ещё {n}",
  "findReplace.confirmReplace":
    "Заменить все совпадения «{pattern}» на «{replacement}»? Замену можно откатить.",
  "findReplace.confirmReplaceMulti":
    "Применить все {n} пар найти → заменить ко всем совпадениям? Замену можно откатить.",
  "findReplace.summary": "{matches} совпадений в {cells} ячейках",
  "findReplace.colRow": "Строка",
  "findReplace.colColumn": "Колонка",
  "findReplace.colValue": "Значение",
  "findReplace.colMatches": "Совпадений",
  "findReplace.historyHeading": "История замен",
  "findReplace.historyCells": "{n} ячеек",
  "findReplace.reverted": "откатано",

  // ---------- детали запуска замены ----------
  "replaceRun.backToTool": "← Найти и заменить",
  "replaceRun.backToTable": "Назад к таблице",
  "replaceRun.title": "Замена #{id}",
  "replaceRun.meta": "{cells} ячеек · {matches} совпадений · {by} · {when}",
  "replaceRun.caseInsensitive": "без учёта регистра",
  "replaceRun.revert": "Откатить замену",
  "replaceRun.revertedAt": "Откатано · {when}",
  "replaceRun.confirmRevert":
    "Вернуть все изменённые этой заменой ячейки к прежним значениям?",
  "replaceRun.confirmRevertDrift":
    "{n} ячеек были отредактированы после этой замены. Откат отменит и эти изменения. Продолжить?",
  "replaceRun.driftWarning":
    "{n} ячеек были изменены после этой замены — откат отменит и эти изменения.",
  "replaceRun.colBefore": "Было",
  "replaceRun.colAfter": "Стало",
  "replaceRun.editedSince": "изменено позже",
  "replaceRun.revertedRow": "Откачено",

  // ---------- проверка ссылок ----------
  // ---------- инструмент структуры и форматирования ----------
  "structureFormat.backToTable": "← Назад к таблице",
  "structureFormat.title": "Структура и форматирование",
  "structureFormat.onTable": "В таблице «{name}»",
  "structureFormat.opsLabel": "Операции",
  "structureFormat.opsHint":
    "Выбранные операции выполняются в указанном порядке — последующие опираются на предыдущие.",
  "structureFormat.op.markdown.title": "Markdown → HTML",
  "structureFormat.op.markdown.desc":
    "Преобразовать оставшийся markdown (заголовки, жирный, курсив, ссылки, списки, код) в HTML-теги.",
  "structureFormat.op.response_start.title": "Начало ответа",
  "structureFormat.op.response_start.desc":
    "Убрать ведущее «html» / ограждение ``` и обёртку <!DOCTYPE>/<html>/<head>/<body>, чтобы ячейка начиналась с реального тега.",
  "structureFormat.op.close_tags.title": "Незакрытые HTML-теги",
  "structureFormat.op.close_tags.desc":
    "Чинит сломанный HTML: вставляет пропущенный > у тега, склеенного с текстом (<pтекст → <p>текст), и дописывает недостающие </tag> для незакрытых тегов (например, в обрезанном <div><p>…). Корректную разметку не трогает.",
  "structureFormat.op.inline_css.title": "Инлайн-CSS",
  "structureFormat.op.inline_css.desc":
    "Удалить атрибуты style=\"…\" и блоки <style>; прочие атрибуты сохраняются.",
  "structureFormat.op.em_dash.title": "Заменить длинное тире",
  "structureFormat.op.em_dash.desc":
    "Меняет длинное тире (—) на обычный дефис — заметный признак ИИ-текста. С пробелами: «быстро—надёжно» становится «быстро - надёжно». Короткое тире (–) и дефисы не трогает.",
  "structureFormat.op.html_format.title": "HTML-форматирование",
  "structureFormat.op.html_format.desc":
    "Снять теги <b> <strong> <i> <em> <u>, сохранив текст внутри.",
  "structureFormat.columnsLabel": "Колонки для чистки",
  "structureFormat.previewBtn": "Предпросмотр",
  "structureFormat.previewResult": "Изменится {change} из {total} ячеек",
  "structureFormat.previewHeading": "Предпросмотр — ячейки, которые изменятся",
  "structureFormat.previewNone": "С текущим выбором ни одна ячейка не изменится.",
  "structureFormat.applyBtn": "Применить",
  "structureFormat.confirmApply":
    "Применить выбранные операции ко всем ячейкам выбранных колонок? Выполняется в фоне, действие можно откатить.",
  "structureFormat.historyHeading": "История",
  "structureFormat.historyCells": "{n} изменено",
  "structureFormat.runLabel": "Запуск #{id}",
  "structureFormat.reverted": "откачено",

  // ---------- запуск структуры и форматирования ----------
  "structureFormatRun.title": "Запуск структуры #{id}",
  "structureFormatRun.meta": "{cells} изменено · {by} · {when}",
  "structureFormatRun.colApplied": "Применено",
  "structureFormatRun.colChanges": "Изменения",
  "structureFormatRun.filterLabel": "Применено:",
  "structureFormatRun.filterAllOps": "Все операции",
  "structureFormatRun.noFilterMatch": "Эта операция не изменила ни одной ячейки.",
  "structureFormatRun.processing": "Обработано {done} / {total} ячеек…",
  "structureFormatRun.preparing": "Подготовка…",
  "structureFormatRun.cancel": "Отменить",
  "structureFormatRun.resume": "Возобновить",
  "structureFormatRun.resumeHint": "Поставить заново, если запуск завис",
  "structureFormatRun.confirmCancel":
    "Остановить запуск? Уже обработанные ячейки сохранят изменения (и их можно откатить); остальные не тронуты.",
  "structureFormatRun.noChanges":
    "Ничего не изменилось — выбранные ячейки уже чистые.",
  "structureFormatRun.revert": "Откатить",
  "structureFormatRun.revertedAt": "Откачено · {when}",
  "structureFormatRun.confirmRevert":
    "Восстановить все изменённые этим запуском ячейки к прежним значениям?",
  "structureFormatRun.confirmRevertDrift":
    "{n} ячеек были изменены после этого запуска. Откат отменит и эти изменения. Продолжить?",
  "structureFormatRun.driftWarning":
    "{n} ячеек были изменены после этого запуска — откат отменит эти изменения.",

  // ---------- инструмент нормализации ----------
  "normalize.backToTable": "← Назад к таблице",
  "normalize.title": "Нормализация",
  "normalize.onTable": "В таблице «{name}»",
  "normalize.opsLabel": "Операции",
  "normalize.opsHint":
    "Выбранные операции выполняются в указанном порядке — последующие опираются на предыдущие.",
  "normalize.op.trim.title": "Убрать пробелы",
  "normalize.op.trim.desc":
    "Удалить пробелы, табуляции и переводы строк в начале и конце.",
  "normalize.op.strip_scheme.title": "Убрать схему URL",
  "normalize.op.strip_scheme.desc":
    "Удалить ведущий http:// / https:// (и ведущий //) — удобно для колонки доменов.",
  "normalize.op.strip_slashes.title": "Убрать слэши по краям",
  "normalize.op.strip_slashes.desc":
    "Удалить символы «/» в начале и конце значения.",
  "normalize.op.lowercase.title": "Нижний регистр",
  "normalize.op.lowercase.desc":
    "Перевести всю ячейку в нижний регистр — применять только к колонкам языка/slug.",
  "normalize.columnsLabel": "Колонки для нормализации",
  "normalize.previewBtn": "Предпросмотр",
  "normalize.previewResult": "Изменится {change} из {total} ячеек",
  "normalize.previewHeading": "Предпросмотр — ячейки, которые изменятся",
  "normalize.previewNone": "С текущим выбором ни одна ячейка не изменится.",
  "normalize.applyBtn": "Применить",
  "normalize.confirmApply":
    "Применить выбранные операции ко всем ячейкам выбранных колонок? Действие можно откатить.",
  "normalize.historyHeading": "История",
  "normalize.historyCells": "{n} изменено",
  "normalize.runLabel": "Запуск #{id}",
  "normalize.reverted": "откатано",

  // ---------- детали запуска нормализации ----------
  "normalizeRun.title": "Нормализация #{id}",
  "normalizeRun.meta": "{cells} изменено · {by} · {when}",
  "normalizeRun.colBefore": "Было",
  "normalizeRun.colAfter": "Стало",
  "normalizeRun.revert": "Откатить нормализацию",
  "normalizeRun.revertedAt": "Откатано · {when}",
  "normalizeRun.confirmRevert":
    "Вернуть все изменённые этой нормализацией ячейки к прежним значениям?",
  "normalizeRun.confirmRevertDrift":
    "{n} ячеек были отредактированы после этой нормализации. Откат отменит и эти изменения. Продолжить?",
  "normalizeRun.driftWarning":
    "{n} ячеек были изменены после этой нормализации — откат отменит и эти изменения.",
  "normalizeRun.editedSince": "изменено позже",
  "normalizeRun.revertedRow": "Откачено",
  "normalizeRun.filterLabel": "Применено:",
  "normalizeRun.filterAllOps": "Все операции",
  "normalizeRun.noFilterMatch": "Эта операция не изменила ни одной ячейки.",

  "tools.linkCheck.title": "Проверка ссылок",
  "tools.linkCheck.desc":
    "Находит пропущенные, выдуманные и нерабочие (404) ссылки в контенте.",

  // breadcrumbs (назад к таблице › инструмент › запуск)
  "breadcrumb.table": "Назад к таблице",
  "breadcrumb.run": "Запуск #{id}",
  "breadcrumb.fix": "ИИ-исправление #{id}",
  "breadcrumb.replace": "Замена ссылок #{id}",
  "breadcrumb.strip": "Удаление ссылок #{id}",

  "linkCheck.backToTable": "← Назад к таблице",
  "linkCheck.title": "Проверка ссылок",
  "linkCheck.onTable": "В таблице «{name}»",
  "linkCheck.modeCheck": "Проверить",
  "linkCheck.modeCorrect": "Исправить ИИ (скоро)",
  "linkCheck.correctSoonHint": "Исправление ссылок ИИ появится в следующей версии.",
  "linkCheck.columnsLabel": "Колонки для проверки",
  "linkCheck.checksLabel": "Какие проверки выполнить",
  "linkCheck.optCrawl": "Обойти ссылки и проверить HTTP-статус",
  "linkCheck.optCrawlHint": "Запрашивает каждую ссылку; ловит опечатки / битые ссылки (404).",
  "linkCheck.optIncludeOk": "Включить рабочие ссылки",
  "linkCheck.optIncludeOkHint":
    "Также показать ссылки со статусом OK (2xx/3xx) — полный список по каждой ссылке.",
  "linkCheck.optJuxtapose": "Сравнить с колонками ожидаемых ссылок",
  "linkCheck.optJuxtaposeHint":
    "Отмечает ссылки, отсутствующие в выводе (пропущенные) или не из списка ожидаемых (выдуманные).",
  "linkCheck.expectedLabel": "Колонки ожидаемых ссылок",
  "linkCheck.expectedPlaceholder": "Выберите колонку…",
  "linkCheck.optTranslation": "Проверить ссылки переводов",
  "linkCheck.optTranslationHint":
    "Строит ожидаемые локализованные ссылки из оригинала (добавляет подпапку /язык/) и сравнивает их со ссылками в переводе.",
  "linkCheck.tOriginal": "Колонка оригинала",
  "linkCheck.tOriginalHint":
    "Контент на исходном языке, ссылки которого локализуются.",
  "linkCheck.tTranslated": "Колонка перевода",
  "linkCheck.tTranslatedHint":
    "Перевод, ссылки которого проверяются (и исправляются).",
  "linkCheck.tLang": "Колонка языка",
  "linkCheck.tLangHint":
    "Код целевого языка в строке, используется как подпапка без изменений (например, es → /es/).",
  "linkCheck.tInternalTreatment": "Внутренние ссылки",
  "linkCheck.tExternalTreatment": "Внешние ссылки",
  "linkCheck.treatSkip": "Пропустить (без изменений)",
  "linkCheck.treatLocalize": "Локализовать (добавить подпапку /язык/)",
  "linkCheck.tDomainCols": "Колонки внутренних доменов",
  "linkCheck.tDomainColsHint":
    "Выберите колонку(и) с собственным доменом сайта для каждой строки. Ссылки на эти хосты — внутренние; вручную список вводить не нужно.",
  "linkCheck.tProductDomain": "Домен(ы) продуктов",
  "linkCheck.tProductDomainHint":
    "Ссылки на этот хост — продуктовые (всегда локализуются, кроме исключений). Несколько — через запятую.",
  "linkCheck.tExceptions": "Исключения продуктов (язык, страница…)",
  "linkCheck.tExceptionsHint":
    "Одна строка на язык: код языка, затем одна или несколько страниц (полный URL, путь или слаг) через запятую. Эти страницы сохраняют корневой URL — без подпапки языка.",
  "linkCheck.linkTypesLabel": "Типы ссылок (необязательно)",
  "linkCheck.linkTypesHint":
    "Классифицировать каждую проверяемую ссылку как продуктовую / внутреннюю / внешнюю, чтобы фильтровать результаты по типу. Оставьте пустым, чтобы пропустить.",
  "linkCheck.tDefaultLangs": "Языки по умолчанию для продуктов (домен, язык)",
  "linkCheck.tDefaultLangsHint":
    "Одна строка на продуктовый сайт: домен, затем язык, который он отдаёт в корне. Если целевой язык ссылки совпадает с языком сайта по умолчанию, ожидаемая ссылка остаётся в корне — подпапка языка не добавляется.",
  "linkCheck.rerunBanner":
    "Повторный запуск на основе проверки #{id}. Измените критерии ниже и запустите снова — будет создана новая проверка, исходная не изменится.",
  "linkCheck.rerunViewSource": "Открыть исходную",
  "linkCheck.checkBtn": "Проверить ссылки",
  "linkCheck.historyHeading": "История проверок",
  "linkCheck.runLabel": "Запуск #{id} — Проверка ссылок",
  "linkCheck.runLabelWithMode": "Запуск #{id} — Проверка ссылок · {mode}",
  "linkCheck.violCount": "{n} проблем",
  "linkCheck.statusQueued": "В очереди",
  "linkCheck.statusRunning": "Идёт",
  "linkCheck.statusDone": "Готово",
  "linkCheck.statusCancelled": "Отменено",
  "linkCheck.statusFailed": "Сбой",

  // ---------- детали проверки ссылок ----------
  "linkCheckRun.backToTool": "← Проверка ссылок",
  "linkCheckRun.backToTable": "Назад к таблице",
  "linkCheckRun.title": "Проверка ссылок #{id}",
  "linkCheckRun.meta": "{by} · {when}",
  "linkCheckRun.cancel": "Отменить",
  "linkCheckRun.resume": "Возобновить",
  "linkCheckRun.resumeHint":
    "Повторно поставить в очередь оставшиеся ссылки, если обход завис (также происходит автоматически).",
  "linkCheckRun.retryFailed": "Повторить неудачные ({n})",
  "linkCheckRun.retryFailedHint":
    "Повторно обойти только неудачные ссылки ({n}) — рабочие ссылки не перепроверяются.",
  "linkCheckRun.confirmRetryFailed":
    "Повторно обойти неудачные ссылки ({n})? Временные ошибки (таймауты, 5xx) могут пройти; рабочие ссылки не затрагиваются.",
  "linkCheckRun.confirmCancel": "Остановить проверку ссылок?",
  "linkCheckRun.crawling": "Обход {done} / {total} ссылок…",
  "linkCheckRun.preparing": "Подготовка…",
  "linkCheckRun.broken": "Битые",
  "linkCheckRun.omitted": "Пропущены",
  "linkCheckRun.hallucinated": "Выдуманы",
  "linkCheckRun.tOmitted": "Отсутствует",
  "linkCheckRun.tHallucinated": "Неверная",
  "linkCheckRun.translationMode": "Ссылки переводов",
  "linkCheckRun.modeCrawl": "HTTP-статус",
  "linkCheckRun.modeJuxtapose": "Ожидаемые ссылки",
  "linkCheckRun.titleWithMode": "Проверка ссылок · {mode} #{id}",
  "linkCheckRun.viewRawTable": "Открыть сырую таблицу",
  "linkCheckRun.rerunWithChanges": "Перезапустить с изменениями",
  "linkCheckRun.rawTableTitle": "Сырая таблица",
  "linkCheckRun.rawTableSubtitle":
    "Разбивка ссылок по строкам — вычисляется по запросу, в массовую таблицу не добавляется. Показаны только строки со ссылками.",
  "linkCheckRun.rawLang": "Язык",
  "linkCheckRun.rawOriginal": "Ссылки оригинала",
  "linkCheckRun.rawExpected": "Ожидаемые ссылки",
  "linkCheckRun.rawTranslation": "Ссылки перевода",
  "linkCheckRun.rawMismatches": "Несоответствия",
  "linkCheckRun.rawTableEmpty": "Нет строк.",
  "linkCheckRun.rawTableEmptyDiscrepancies": "Нет строк с несоответствиями ссылок.",
  "linkCheckRun.rawTableEmptyDismissed": "Нет отклонённых ошибок.",
  "linkCheckRun.rawTableEmptySolved": "Пока нет исправленных ссылок.",
  "linkCheckRun.rawViewActive": "Несоответствия",
  "linkCheckRun.rawViewAll": "Все строки со ссылками",
  "linkCheckRun.rawViewDismissed": "Отклонённые",
  "linkCheckRun.rawViewSolved": "Исправленные",
  "linkCheckRun.selectedErrorsRows": "Выбрано: {n} ссылок в {rows} строках",
  "linkCheckRun.clearSelection": "Очистить",
  "linkCheckRun.selectAll": "Выбрать все на этой странице",
  "linkCheckRun.selectAllMatches": "Выбрать все совпадения (все страницы)",
  "linkCheckRun.dismissSelected": "Отклонить ({n})",
  "linkCheckRun.restoreSelected": "Восстановить ({n})",
  "linkCheckRun.replaceSelected": "Заменить ({n})",
  "linkCheckRun.fixSelectedAi": "Исправить с ИИ ({n})",
  "linkCheckRun.confirmReplace":
    "Заменить неверные ссылки перевода на ожидаемые в выбранных элементах ({n})? Это изменит переведённый контент и будет записано как откатываемая задача.",
  "linkCheckRun.stripSelected": "Удалить ссылки ({n})",
  "linkCheckRun.stripSelectedCount": "Выбрано ссылок: {n}",
  "linkCheckRun.stripRowHint": "Выбрать эту ссылку для удаления (текст ссылки останется)",
  "linkCheckRun.confirmStrip":
    "Удалить выбранные ссылки ({n}) — убрать тег <a>, оставив текст? Это изменит содержимое ячейки и будет записано как откатываемая задача.",
  "linkCheckRun.rawLegendOk": "Совпадает с ожидаемой",
  "linkCheckRun.rawLegendDiscrepancy": "Несоответствие",
  "linkCheckRun.rawLegendInvented": "Выдуманная",
  "linkCheckRun.rawLegendUnderline": "Тот же домен — путь отличается",
  "linkCheckRun.rawExpectedTooltip": "Ожидалось: {url}",
  "linkCheckRun.rawTypeAll": "Все типы ссылок",
  "linkCheckRun.rawTypeProduct": "Продуктовые",
  "linkCheckRun.rawTypeInternal": "Внутренние",
  "linkCheckRun.rawTypeExternal": "Внешние",
  "linkCheckRun.ok": "OK",
  "linkCheckRun.status5xx": "5xx",
  "linkCheckRun.status3xx": "3xx",
  "linkCheckRun.status2xx": "200",
  "linkCheckRun.statusCountsHint":
    "Счётчики — по уникальным ссылкам; в таблице ниже показано каждое вхождение (ссылка может встречаться в нескольких ячейках).",
  "linkCheckRun.errorBadge": "Ошибка",
  "linkCheckRun.noViolations": "Проблем со ссылками не найдено.",
  "linkCheckRun.colRow": "Строка",
  "linkCheckRun.colColumn": "Колонка",
  "linkCheckRun.colProblem": "Проблема",
  "linkCheckRun.colLink": "Ссылка",
  "linkCheckRun.colDetail": "Детали",
  "linkCheckRun.fix": "Исправить",
  "linkCheckRun.filterAllProblems": "Все проблемы",
  "linkCheckRun.filterAllCodes": "Все коды статуса",
  "linkCheckRun.filterAllResolutions": "Все (исправленные и нет)",
  "linkCheckRun.resSolved": "Решено",
  "linkCheckRun.resUnsolved": "Не решено",
  "linkCheckRun.resUntouched": "Не трогали",
  "linkCheckRun.searchPlaceholder": "Поиск по ссылкам…",
  "linkCheckRun.searchContains": "содержит",
  "linkCheckRun.searchNotContains": "не содержит",
  "linkCheckRun.noMatches": "Нет ссылок под текущий фильтр.",

  // текст по коду детали (локализуется из кода + статуса)
  "linkCheckDetail.expectedMissing": "Ожидалась, но отсутствует",
  "linkCheckDetail.notInExpected": "Нет в списке ожидаемых",
  "linkCheckDetail.httpError": "HTTP {code}",
  "linkCheckDetail.timeout": "Тайм-аут",
  "linkCheckDetail.unreachable": "Недоступно (хост не найден)",
  "linkCheckDetail.blocked": "Заблокировано (непубличный адрес)",
  "linkCheckDetail.redirect": "OK после редиректа ({code})",
  "linkCheckDetail.ok": "OK ({code})",

  // AI-исправление ссылок
  "linkFix.fixHint": "Исправить отмеченные ссылки с помощью ИИ.",
  "linkFix.fixHintFiltered": "Исправить только отфильтрованные ссылки с ИИ.",
  "linkFix.selectedRows": "Выбрано строк: {n}",
  "linkFix.fixSelected": "Исправить выбранные ({n}) с ИИ",
  "linkFix.fixAll": "Исправить все с ИИ",
  "linkFix.fixAllShown": "Исправить все показанные с ИИ",
  "linkFix.modalTitle": "Исправить ссылки с ИИ",
  "linkFix.modalSubtitle": "Будет исправлено ячеек: {n}.",
  "linkFix.promptLabel": "Промпт для исправления",
  "linkFix.promptHint":
    "Инструкции для ИИ. По умолчанию — промпт из вашего прошлого задания; при необходимости измените его для этого запуска.",
  "linkFix.targetLabel": "Записать исправленный результат в",
  "linkFix.targetNew": "➕ Новую колонку",
  "linkFix.targetExisting": "Колонка: {name}",
  "linkFix.targetOverwrite": "Перезаписать проверяемую колонку",
  "linkFix.newColumnName": "Название новой колонки",
  "linkFix.newNameMatchesExisting":
    "Колонка «{name}» уже существует — исправленные ячейки запишутся в неё, дубликат не создаётся. Укажите другое название, чтобы создать отдельную колонку.",
  "linkFix.overwriteWarn":
    "Это заменит исходный контент на месте. Лучше выберите новую колонку, чтобы сохранить оригинал.",
  "linkFix.startFix": "Запустить исправление",
  "linkFix.correctionsHeading": "Исправления из этого запуска",
  "linkFix.fixedBadge": "Исправлено",
  "linkFix.runLabel": "ИИ-исправление #{id}",
  "linkFix.replaceRunLabel": "Замена ссылок #{id}",
  "linkFix.stripRunLabel": "Удаление ссылок #{id}",
  "linkFixRun.revertedBadge": "откачено",
  // Общие действия переименования/удаления запусков
  "runs.rename": "Переименовать",
  "runs.delete": "Удалить запуск",
  "runs.renamePrompt": "Название запуска (пусто — очистить):",
  "runs.confirmDelete": "Удалить этот запуск? Действие необратимо.",
  "linkFix.selectRowHint": "Выбрать строку для исправления ИИ",
  "linkFix.needExpected":
    "Для исправления ИИ нужна колонка с ожидаемыми ссылками. Перезапустите проверку с включённым «Сравнить с ожидаемыми ссылками», чтобы ИИ знал правильные ссылки.",
  "linkFixRun.title": "ИИ-исправление ссылок #{id}",
  "linkFixRun.replaceTitle": "Замена ссылок #{id}",
  "linkFixRun.stripTitle": "Удаление ссылок #{id}",
  "linkFixRun.confirmCancel": "Остановить это ИИ-исправление?",
  "linkFixRun.confirmRevert":
    "Вернуть все изменённые этим запуском ячейки к значению до исправления? Ячейки, отредактированные после, не трогаются.",
  "linkFixRun.revert": "Откатить",
  "linkFixRun.resumeStalledHint":
    "Запуск давно не двигался — возобновите, чтобы поставить оставшиеся ячейки в очередь заново.",
  "linkFixRun.stalledNote":
    "Прогресса давно нет — запуск мог зависнуть. Его можно возобновить.",
  "linkFixRun.revertedNote": "Откачено {when}.",
  "linkFixRun.revertSkippedNote":
    "Восстановлено ячеек: {reverted}; пропущено {skipped}, которые изменились после этого исправления (правка вручную или более новое исправление). Сначала откатите более новые запуски, чтобы восстановить их.",
  "linkFixRun.fixing": "Исправлено {done} / {total} ячеек…",
  "linkFixRun.fixed": "Исправлено",
  "linkFixRun.failed": "Ошибки",
  "linkFixRun.skipped": "Пропущено",
  "linkFixRun.total": "Всего",
  "linkFixRun.linksReplacedNote": "Заменено ссылок: {links} (в {cells} строках — по одной ячейке на строку).",
  "linkFixRun.linksStrippedNote": "Удалено ссылок: {links} (в {cells} ячейках — текст ссылок сохранён).",
  "linkFixRun.viewRecheck": "Что теперь Решено / Не решено — на странице проверки →",
  "linkFixRun.before": "До",
  "linkFixRun.after": "После",
  "linkFixRun.showFull": "Показать весь текст",
  "linkFixRun.showSnippet": "Только изменения",
  "linkFixRun.state.pending": "В очереди",
  "linkFixRun.state.done": "Исправлено",
  "linkFixRun.state.failed": "Ошибка",
  "linkFixRun.state.skipped": "Пропущено",

  // ---------- Импорт из Google Docs ----------
  "gdocsImport.title": "Импорт из Google Docs",
  "gdocsImport.subtitle":
    "Превратите Google-таблицу со страницами и связанными Google-документами в таблицу для Custom CMS. Загрузите JSON, который формирует вспомогательный скрипт — одно- или мультисайт определяется по доменам в таблице.",
  "gdocsImport.helpToggle": "Как получить JSON-файл?",
  "gdocsImport.step1":
    "Откройте свою Google-таблицу, затем Расширения → Apps Script.",
  "gdocsImport.step2":
    "Вставьте Code.gs, задайте SHEET_URL вверху и сохраните. Манифест appsscript.json ниже — необязательный: Apps Script сам определяет нужные разрешения из кода, а манифест лишь фиксирует среду V8 и ограничивает доступ к таблицам режимом «только чтение».",
  "gdocsImport.step3":
    "Запустите функцию `run` один раз и выдайте запрошенные разрешения — скрипт работает от вашего имени, поэтому видит документы с ограниченным доступом.",
  "gdocsImport.step4":
    "Он запишет JSON-файл на ваш Диск (ссылка появится в логе). Скачайте этот файл.",
  "gdocsImport.step5": "Загрузите JSON здесь.",
  "gdocsImport.downloadCode": "Скачать Code.gs",
  "gdocsImport.downloadManifest": "Скачать appsscript.json (необязательно)",
  "gdocsImport.tableName": "Название таблицы",
  "gdocsImport.tableNamePlaceholder": "напр. Июньская партия статей",
  "gdocsImport.jsonFile": "JSON-файл Apps Script",
  "gdocsImport.folder": "Папка",
  "gdocsImport.noFolder": "Без папки",
  "gdocsImport.aiHeading": "AI-модель",
  "gdocsImport.aiHelp":
    "Используется для извлечения мета-данных и сопоставления страниц с документами. Оставьте по умолчанию, чтобы использовать первого включённого провайдера рабочего пространства.",
  "gdocsImport.start": "Начать импорт",
  "gdocsImport.starting": "Запуск…",
  "gdocsImport.recentHeading": "Недавние импорты",

  // ---------- Панель структуры сайта (импорт из Google Docs) ----------
  "gdocsStructure.heading": "Структура сайта (из импорта Google Docs)",
  "gdocsStructure.summary": "сайтов: {sites} · запланировано страниц: {pages}",
  "gdocsStructure.help":
    "Полный список запланированных страниц по каждому сайту из колонки «Структура» — включая страницы, для которых ещё нет документа (поэтому их нет в строках выше). Скопируйте список сайта, чтобы передать его ИИ.",
  "gdocsStructure.copy": "Копировать",
  "gdocsStructure.copied": "Скопировано",
  "gdocsStructure.noDomain": "(без домена)",

  // ---------- Панель аудита слагов от ИИ (Google Docs) ----------
  "gdocsSlugAudit.heading": "Сопоставление слагов ИИ (из импорта Google Docs)",
  "gdocsSlugAudit.summary":
    "строк: {total} · изменено: {changed} · без точного слага: {unmatched}",
  "gdocsSlugAudit.help":
    "Что ИИ сделал со слагом каждой строки при импорте: исходный якорь ссылки (До) → итоговый слаг из колонки «Структура» (После). Жёлтый — ИИ изменил его относительно якоря; красный — не удалось сопоставить со страницей структуры (no-exact-slug). Отражает момент импорта, без учёта последующих ручных правок.",
  "gdocsSlugAudit.colDomain": "Домен",
  "gdocsSlugAudit.colLang": "Язык",
  "gdocsSlugAudit.colSeoTitle": "SEO-заголовок",
  "gdocsSlugAudit.colBefore": "До (якорь)",
  "gdocsSlugAudit.colAfter": "После (слаг)",

  // ---------- Импорт из Google Docs (страница прогресса) ----------
  "gdocsRun.title": "Импорт #{id}",
  "gdocsRun.meta": "Запущен {when}",
  "gdocsRun.mode.single": "односайтовый",
  "gdocsRun.mode.multi": "мультисайтовый",
  "gdocsRun.aiUsed": "AI: {provider} · {model}",
  "gdocsRun.cancel": "Отменить",
  "gdocsRun.cancelConfirm":
    "Отменить импорт? Уже обработанные документы сохранятся.",
  "gdocsRun.delete": "Удалить",
  "gdocsRun.deleteConfirm":
    "Удалить этот импорт из истории? Созданная таблица (если есть) сохранится.",
  "gdocsRun.docsHeading": "Документы очищены + извлечены мета-данные",
  "gdocsRun.colDocsTotal": "Всего",
  "gdocsRun.colDocsDone": "Готово",
  "gdocsRun.colDocsFailed": "Ошибки",
  "gdocsRun.pagesHeading": "Страницы сопоставлены с документами",
  "gdocsRun.colPagesTotal": "Всего",
  "gdocsRun.colPagesMatched": "Сопоставлено",
  "gdocsRun.colPagesUnmatched": "Без пары",
  "gdocsRun.coverageSummary":
    "Покрытие: {rows} строк из {links} привязанных документ(ов) на {planned} запланированных страниц структуры.",
  "gdocsRun.coverageLow":
    "Контент получают только привязанные страницы — у {missing} запланированных страниц(ы) ещё нет документа. Если ожидали больше, проверьте, что документ каждой страницы привязан ссылкой к её записи в структуре.",
  "gdocsRun.builtSummary": "Создано строк: {rows} ({mode}).",
  "gdocsRun.openTable": "Открыть таблицу →",
  "gdocsRun.warningsHeading": "Предупреждения ({count})",
  "gdocsRun.statusQueued": "В очереди",
  "gdocsRun.statusRunning": "Выполняется",
  "gdocsRun.statusDone": "Готово",
  "gdocsRun.statusCancelled": "Отменён",
  "gdocsRun.statusFailed": "Ошибка",
};
