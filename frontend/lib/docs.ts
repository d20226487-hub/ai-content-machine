import type { RoleName } from "@/lib/types";

export interface DocArticle {
  slug: string;
  titleEn: string;
  titleRu: string;
  summaryEn: string;
  summaryRu: string;
  roles: RoleName[];
}

export const DOC_ARTICLES: DocArticle[] = [
  {
    slug: "dashboard",
    titleEn: "Overview & navigation",
    titleRu: "Обзор и навигация",
    summaryEn: "What lives where in the app, and which sections each role can use.",
    summaryRu:
      "Где что находится в приложении и какие разделы доступны для каждой роли.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "prompts",
    titleEn: "Prompts, folders, tags, versions",
    titleRu: "Промпты, папки, теги, версии",
    summaryEn:
      "How to create prompts with variables, organise them in folders, tag them, and work with the version history.",
    summaryRu:
      "Как создавать промпты с переменными, раскладывать по папкам, помечать тегами и работать с историей версий.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "single",
    titleEn: "Single — one-off generation",
    titleRu: "Single — генерация по одному",
    summaryEn:
      "Pick a prompt, fill the variables, generate, save the result, publish it.",
    summaryRu:
      "Выбрать промпт, заполнить переменные, сгенерировать, сохранить результат и опубликовать.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "bulk",
    titleEn: "Bulk — spreadsheet-style mass generation",
    titleRu: "Bulk — таблицы массовой генерации",
    summaryEn:
      "Build tables with input and output columns, run generation across many rows at once.",
    summaryRu:
      "Создавать таблицы с входными и выходными колонками и запускать генерацию по множеству строк сразу.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "bulk-tools",
    titleEn: "Bulk: content tools",
    titleRu: "Bulk: инструменты контента",
    summaryEn:
      "Find & Replace, Link Checker (+ AI fix), Structure & Formatting, and Normalize — table-wide tools under the grid.",
    summaryRu:
      "Найти и заменить, Проверка ссылок (+ ИИ-исправление), Структура и форматирование и Нормализация — инструменты по всей таблице.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "translate",
    titleEn: "Translate content",
    titleRu: "Перевод контента",
    summaryEn:
      "Translate bulk-table cells and other results in place; language picker, caching, Brain config.",
    summaryRu:
      "Перевод ячеек bulk-таблиц и других результатов на месте: выбор языка, кэш, настройка в «Мозге».",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "saved-generations",
    titleEn: "Saved generations",
    titleRu: "Сохранённые генерации",
    summaryEn: "Where your saved Single results live and how to reopen them.",
    summaryRu: "Где хранятся сохранённые результаты Single и как их открыть.",
    roles: ["admin", "manager", "content_generator"],
  },
  {
    slug: "publish-domains",
    titleEn: "Publish: domains & connections",
    titleRu: "Публикация: домены и подключение",
    summaryEn:
      "Add a WordPress or Custom CMS site, configure auth, languages, post types, profiles.",
    summaryRu:
      "Добавление сайта на WordPress или Custom CMS: авторизация, языки, типы записей, профили публикации.",
    roles: ["admin", "manager"],
  },
  {
    slug: "publish-single",
    titleEn: "Publish: single posts",
    titleRu: "Публикация: одиночная",
    summaryEn:
      "Send one saved generation to a domain — fields, profiles, history.",
    summaryRu:
      "Отправка одной сохранённой генерации в домен: поля, профили, история.",
    roles: ["admin", "manager"],
  },
  {
    slug: "publish-bulk",
    titleEn: "Publish: bulk runs",
    titleRu: "Публикация: массовая",
    summaryEn:
      "Publish many bulk-table rows at once — mappings, filters, pause/resume, rerun failed.",
    summaryRu:
      "Массовая публикация строк bulk-таблицы: сопоставление полей, фильтры, пауза/возобновление, повтор неудачных.",
    roles: ["admin", "manager"],
  },
  {
    slug: "errors",
    titleEn: "Error log",
    titleRu: "Журнал ошибок",
    summaryEn: "Where to find captured errors and how to read them.",
    summaryRu: "Где смотреть зафиксированные ошибки и как их читать.",
    roles: ["admin", "manager"],
  },
  {
    slug: "users",
    titleEn: "Users & roles",
    titleRu: "Пользователи и роли",
    summaryEn: "Adding colleagues, assigning roles, deactivating accounts.",
    summaryRu: "Добавление коллег, назначение ролей, отключение учётных записей.",
    roles: ["admin", "manager"],
  },
  {
    slug: "settings",
    titleEn: "Settings: providers, pricing, backups, Brain",
    titleRu: "Настройки: провайдеры, цены, бэкапы, Мозг",
    summaryEn:
      "Tabbed settings — provider keys & limits, publishing defaults, token pricing, DB backups, trash retention, Brain prompts.",
    summaryRu:
      "Вкладки настроек: ключи и лимиты провайдеров, дефолты публикации, цены токенов, бэкапы базы, корзина, промпты «Мозга».",
    roles: ["admin"],
  },
];

export function articlesForRole(role: RoleName): DocArticle[] {
  return DOC_ARTICLES.filter((a) => a.roles.includes(role));
}

export function getArticle(slug: string): DocArticle | undefined {
  return DOC_ARTICLES.find((a) => a.slug === slug);
}

export function canAccessArticle(role: RoleName, slug: string): boolean {
  const a = getArticle(slug);
  return !!a && a.roles.includes(role);
}
