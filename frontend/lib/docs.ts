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
    titleEn: "Settings: LLM provider keys",
    titleRu: "Настройки: ключи LLM-провайдеров",
    summaryEn:
      "Enabling providers, storing API keys, choosing models, tuning rate limits.",
    summaryRu:
      "Включение провайдеров, хранение API-ключей, выбор моделей, настройка лимитов.",
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
