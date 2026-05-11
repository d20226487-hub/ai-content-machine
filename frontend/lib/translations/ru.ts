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
  "common.retry": "Повторить",
  "common.save": "Сохранить",
  "common.saving": "Сохранение…",
  "common.saved": "Сохранено",
  "common.savedDot": "Сохранено.",
  "common.cancel": "Отмена",
  "common.close": "Закрыть",
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
  "app.brand": "AI Content Machine",
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
    "Удалить пользователя {email}? Это действие нельзя отменить.",
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
    "Удалить «{name}» и все его версии? Это действие нельзя отменить.",
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
  "library.newTable": "+ Новая таблица",
  "library.searchPlaceholder": "Поиск таблиц…",
  "library.searchInFolderPlaceholder": "Поиск в «{folder}»…",
  "library.foldersHeading": "Папки ({count})",
  "library.tablesHeading": "Таблицы",
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
  "library.folderNamePrompt": "Название папки:",
  "library.renameFolderPrompt": "Переименовать папку:",
  "library.confirmDeleteFolder":
    "Удалить папку «{name}»? Папка должна быть пустой (сначала переместите все таблицы).",
  "library.newTablePrompt": "Название новой таблицы:",
  "library.confirmDeleteTable":
    "Удалить «{name}»? Это действие нельзя отменить.",
  "library.movePickerNoFolder": "— без папки —",
  "library.breadcrumbRoot": "Библиотека",
  "library.inFolder": "в",

  // table detail
  "libraryTable.back": "← Библиотека",
  "libraryTable.exportCsv": "Экспорт CSV",
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

  // cell editor
  "cellEditor.edit": "Редактирование",
  "cellEditor.preview": "Предпросмотр",
  "cellEditor.empty": "Ячейка пуста",
  "cellEditor.unsavedChanges": "Несохранённые изменения",
  "cellEditor.noChanges": "Изменений нет",
  "cellEditor.toSave": "для сохранения",

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
  "csvImport.delimiter": "Разделитель",
  "csvImport.delimiterComma": ", (запятая)",
  "csvImport.delimiterSemicolon": "; (точка с запятой)",
  "csvImport.delimiterTab": "табуляция",
  "csvImport.delimiterPipe": "| (вертикальная черта)",
  "csvImport.firstRowHeader": "Первая строка — заголовок",
  "csvImport.previewLabel": "Предпросмотр",

  // ---------- create / single ----------
  "create.title": "Создать",
  "create.subtitle": "Сгенерируйте контент по своим промптам.",
  "single.pickPrompt": "Выберите промпт",
  "single.savedGenerations": "Сохранённые генерации",
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

  // domains page
  "domains.title": "Домены",
  "domains.subtitle":
    "Подключённые сайты, на которые можно публиковать.",
  "domains.import": "Импорт CSV",
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
  "domains.confirmDelete": "Удалить домен «{name}»?",
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
  "domainMod.fieldBearerToken": "Bearer-токен",
  "domainMod.bearerHintEdit":
    "Оставьте пустым, чтобы сохранить текущий токен.",
  "domainMod.bearerPlaceholder": "вставьте токен",
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
  "domainCsv.sample": "Пример CSV",
  "domainCsv.sampleStart": "Возьмите за основу.",
  "domainCsv.downloadSample": "Скачать domains_sample.csv",
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
  "pubHistory.colProfile": "Профиль",
  "pubHistory.colStatus": "Статус",
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
  "bulkRun.failedToLoad": "Не удалось загрузить запуск",
  "bulkRun.processed": "{done} / {total} обработано",
  "bulkRun.donePrefix": "✓ {count} готово",
  "bulkRun.failedPrefix": "✗ {count} с ошибкой",
  "bulkRun.skippedPrefix": "{count} пропущено",
  "bulkRun.colTime": "Время",
  "bulkRun.colRow": "Строка",
  "bulkRun.colDomain": "Сайт",
  "bulkRun.colProfile": "Профиль",
  "bulkRun.colStatus": "Статус",
  "bulkRun.colPost": "Запись",
  "bulkRun.colError": "Ошибка / предупреждения",
  "bulkRun.empty": "Результатов по строкам пока нет.",
  "bulkRun.viewLink": "Открыть",
  "bulkRun.modeSingle": "Один сайт",
  "bulkRun.modeMulti": "Несколько сайтов",
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
  "bulkPub.andMore": "…и ещё {count}",
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
  "htmlViewer.openWindow": "Открыть в новом окне",
  "htmlViewer.tooLarge":
    "Содержимое слишком велико для встроенного предпросмотра.",
  "htmlViewer.openInWindow": "открыть в новом окне",
  "htmlViewer.copyAction": "скопировать",

  // user chip
  "userChip.tooltip": "Создал: {name}",
};
