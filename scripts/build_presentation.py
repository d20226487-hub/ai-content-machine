"""
Builds a high-level Russian-language PDF presentation about Content Beast
(ACM) — the internal content generation + publishing tool.

Audience: colleagues (managers + content generators) seeing the tool for
the first time. Sent BEFORE a live demo as context, kept AFTER as a recall
aid. Visual style: slide-deck (landscape), sparse text, color accents,
geometric icon glyphs — no deep technical detail.

Run: python scripts/build_presentation.py
Output: content-beast-overview-ru.pdf in the repo root.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ---------- fonts ----------
# Arial ships with Windows and has full Cyrillic coverage. Default ReportLab
# Type 1 fonts (Helvetica/Times) do NOT support Cyrillic — text would render
# as boxes.
FONTS_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("RegFont", str(FONTS_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("BoldFont", str(FONTS_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("ItalicFont", str(FONTS_DIR / "ariali.ttf")))

# ---------- palette ----------
NAVY = HexColor("#0F172A")      # primary dark — titles, headers
ACCENT = HexColor("#F97316")    # orange — emphasis, badges
BLUE = HexColor("#3B82F6")      # secondary — bullets, dividers
GREEN = HexColor("#10B981")     # tertiary — checkmarks, success
PURPLE = HexColor("#8B5CF6")    # tertiary — alt accent
BG_TINT = HexColor("#F8FAFC")   # soft background
TEXT = HexColor("#1E293B")      # body text
MUTED = HexColor("#64748B")     # secondary text
BORDER = HexColor("#E2E8F0")    # subtle dividers

# Slide geometry — A4 landscape gives us 297mm × 210mm.
PAGE_W, PAGE_H = landscape(A4)
MARGIN = 18 * mm


# ---------- primitives ----------

def slide_chrome(c: canvas.Canvas, page_no: int, total: int, section: str):
    """Background, top bar, and footer that every slide shares.

    Keeps the eye anchored across slides: a thin colored bar at the top
    flags which section the slide belongs to (visible recall aid), and
    the page counter at the bottom-right tells the viewer where they
    are in the deck without counting.
    """
    # Soft background
    c.setFillColor(BG_TINT)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # Top accent bar
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H - 8 * mm, 60 * mm, 8 * mm, stroke=0, fill=1)

    # Brand mark + section label inside the top bar
    c.setFillColor(white)
    c.setFont("BoldFont", 9)
    c.drawString(MARGIN, PAGE_H - 5.5 * mm, "CONTENT BEAST")
    c.setFillColor(HexColor("#CBD5E1"))
    c.setFont("RegFont", 9)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 5.5 * mm, section)

    # Footer page number
    c.setFillColor(MUTED)
    c.setFont("RegFont", 8)
    c.drawRightString(
        PAGE_W - MARGIN, 9 * mm, f"{page_no} / {total}"
    )


def big_title(c: canvas.Canvas, text: str, y: float, color=NAVY):
    """Slide title — left-aligned, hefty, with a colored stub underneath."""
    c.setFillColor(color)
    c.setFont("BoldFont", 32)
    c.drawString(MARGIN, y, text)
    c.setFillColor(ACCENT)
    c.rect(MARGIN, y - 4 * mm, 18 * mm, 1.5 * mm, stroke=0, fill=1)


def subtitle(c: canvas.Canvas, text: str, y: float):
    c.setFillColor(MUTED)
    c.setFont("RegFont", 14)
    c.drawString(MARGIN, y, text)


def card(
    c: canvas.Canvas,
    x: float, y: float, w: float, h: float,
    *,
    label: str,
    title: str,
    body: list[str],
    accent_color=BLUE,
    icon: str | None = None,
):
    """A "concept card" used on the multi-card slides.

    Layout: thin colored bar at the top, then label (uppercase),
    a big title, and bullet-style body lines. Icon is rendered as a
    large glyph in the top-right (Unicode geometric shape, so Arial
    handles it without needing emoji fonts).
    """
    # Card body
    c.setFillColor(white)
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, 4 * mm, stroke=1, fill=1)

    # Accent strip
    c.setFillColor(accent_color)
    c.roundRect(x, y + h - 3 * mm, w, 3 * mm, 2 * mm, stroke=0, fill=1)
    # Fill the bottom of the strip so only the top is rounded
    c.rect(x, y + h - 3 * mm, w, 1.5 * mm, stroke=0, fill=1)

    # Icon in top-right
    if icon:
        c.setFillColor(accent_color)
        c.setFont("BoldFont", 28)
        c.drawRightString(x + w - 6 * mm, y + h - 16 * mm, icon)

    # Label
    c.setFillColor(accent_color)
    c.setFont("BoldFont", 9)
    c.drawString(x + 6 * mm, y + h - 12 * mm, label.upper())

    # Title
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 16)
    c.drawString(x + 6 * mm, y + h - 22 * mm, title)

    # Body lines
    c.setFillColor(TEXT)
    c.setFont("RegFont", 11)
    line_y = y + h - 32 * mm
    for line in body:
        # Wrap manually if too long — keep visual rhythm tight
        c.drawString(x + 6 * mm, line_y, line)
        line_y -= 6 * mm


def bullet_list(
    c: canvas.Canvas,
    x: float, y: float,
    items: list[str],
    *,
    bullet_color=ACCENT,
    line_height: float = 8 * mm,
    font_size: int = 13,
):
    """Vertical list with a colored ● marker per row.

    Empirically — see the glyph-coverage probe in build_presentation —
    Arial Bold on Windows is missing ▸ / ▶ / ★ / ✓ and most other
    Geometric Shapes block characters. The reliable subset that ships
    with the font is: ○ ● ■ ▲ ♦ →  We use ● here.
    """
    cur = y
    for item in items:
        c.setFillColor(bullet_color)
        c.setFont("BoldFont", font_size + 1)
        c.drawString(x, cur, "●")
        c.setFillColor(TEXT)
        c.setFont("RegFont", font_size)
        c.drawString(x + 6 * mm, cur, item)
        cur -= line_height


def divider(c: canvas.Canvas, y: float, color=BORDER):
    c.setStrokeColor(color)
    c.setLineWidth(0.4)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)


# ---------- slide builders ----------

TOTAL = 15


def slide_01_title(c: canvas.Canvas):
    """Cover. Big brand, one-line pitch, footer note."""
    # Full-bleed dark background for visual contrast with the rest of the deck
    c.setFillColor(NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # Orange accent strip
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H - 4 * mm, PAGE_W, 4 * mm, stroke=0, fill=1)
    c.rect(0, 0, 80 * mm, 4 * mm, stroke=0, fill=1)

    # Title
    c.setFillColor(white)
    c.setFont("BoldFont", 64)
    c.drawString(MARGIN, PAGE_H / 2 + 8 * mm, "Content")
    c.setFillColor(ACCENT)
    c.drawString(MARGIN, PAGE_H / 2 - 12 * mm, "Beast")

    # Tagline
    c.setFillColor(HexColor("#E2E8F0"))
    c.setFont("RegFont", 18)
    c.drawString(
        MARGIN,
        PAGE_H / 2 - 32 * mm,
        "Внутренний инструмент для генерации",
    )
    c.drawString(
        MARGIN,
        PAGE_H / 2 - 40 * mm,
        "и публикации контента",
    )

    # Footer
    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("RegFont", 11)
    c.drawString(MARGIN, MARGIN, "Превью перед демо · Высокоуровневый обзор")
    c.setFont("BoldFont", 11)
    c.setFillColor(ACCENT)
    c.drawRightString(PAGE_W - MARGIN, MARGIN, "1 / " + str(TOTAL))


def slide_02_what(c: canvas.Canvas):
    """What is it? One sentence + before/after framing."""
    slide_chrome(c, 2, TOTAL, "ЧТО ЭТО")
    big_title(c, "Что это?", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Замена «таблицы в Google Sheets + ручной копипаст» полноценным веб-инструментом.",
        PAGE_H - 48 * mm,
    )

    # Two cards: было / стало
    card_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    card_h = 95 * mm
    card_y = MARGIN + 15 * mm

    card(
        c,
        MARGIN, card_y, card_w, card_h,
        label="Раньше",
        title="Google Sheets + ручной труд",
        body=[
            "•  Промпты в разрозненных таблицах",
            "•  Копипаст в ChatGPT / Gemini",
            "•  Копипаст результата обратно",
            "•  Публикация — отдельно, вручную",
            "•  Никто не знает, кто что сделал",
        ],
        accent_color=MUTED,
        icon="○",  # U+25CB — Arial has it (U+25EF "Large Circle" rendered as a box)
    )
    card(
        c,
        MARGIN + card_w + 10 * mm, card_y, card_w, card_h,
        label="Сейчас",
        title="Один инструмент от идеи до публикации",
        body=[
            "•  Библиотека промптов с версиями",
            "•  Генерация одним кликом: Single и Bulk",
            "•  Генерация с источниками (Google)",
            "•  Инструменты правки таблиц + AI-помощник",
            "•  Публикация: WordPress, Custom CMS, Autotool",
            "•  Корзина, роли, бэкапы, учёт расходов",
        ],
        accent_color=ACCENT,
        icon="●",
    )


def slide_03_flow(c: canvas.Canvas):
    """Главный сценарий: prompt → content → publish."""
    slide_chrome(c, 3, TOTAL, "ГЛАВНЫЙ СЦЕНАРИЙ")
    big_title(c, "От идеи до публикации — за один проход", PAGE_H - 35 * mm)

    # Three big boxes connected by arrows
    box_w = 65 * mm
    box_h = 55 * mm
    gap = (PAGE_W - 2 * MARGIN - 3 * box_w) / 2
    y = PAGE_H / 2 - box_h / 2

    steps = [
        ("01", "ПРОМПТ", "Готовый шаблон\nс переменными", BLUE),
        ("02", "ГЕНЕРАЦИЯ", "Любой провайдер,\nлюбая модель", ACCENT),
        ("03", "ПУБЛИКАЦИЯ", "WordPress / Custom CMS,\nодин сайт или много", GREEN),
    ]
    for i, (num, label, desc, color) in enumerate(steps):
        x = MARGIN + i * (box_w + gap)
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, y, box_w, box_h, 4 * mm, stroke=1, fill=1)
        # Big number
        c.setFillColor(color)
        c.setFont("BoldFont", 42)
        c.drawString(x + 6 * mm, y + box_h - 18 * mm, num)
        # Label
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 14)
        c.drawString(x + 6 * mm, y + box_h - 30 * mm, label)
        # Description
        c.setFillColor(TEXT)
        c.setFont("RegFont", 10)
        for j, line in enumerate(desc.split("\n")):
            c.drawString(x + 6 * mm, y + box_h - 40 * mm - j * 5 * mm, line)
        # Arrow to next
        if i < 2:
            arrow_x = x + box_w + gap / 2
            arrow_y = y + box_h / 2
            c.setFillColor(ACCENT)
            c.setFont("BoldFont", 28)
            c.drawCentredString(arrow_x, arrow_y - 4 * mm, "→")

    # Bottom note
    c.setFillColor(MUTED)
    c.setFont("ItalicFont", 11)
    c.drawCentredString(
        PAGE_W / 2,
        MARGIN + 18 * mm,
        "Каждый шаг — отдельный экран, но переходить между ними можно «одним кликом»",
    )


def slide_04_modes(c: canvas.Canvas):
    """Two modes: Single + Bulk."""
    slide_chrome(c, 4, TOTAL, "ДВА РЕЖИМА РАБОТЫ")
    big_title(c, "Два режима: Single и Bulk", PAGE_H - 35 * mm)
    subtitle(c, "Выбираете под задачу — один пост или сразу сотни.", PAGE_H - 48 * mm)

    card_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    card_h = 95 * mm
    card_y = MARGIN + 15 * mm

    card(
        c,
        MARGIN, card_y, card_w, card_h,
        label="Single",
        title="Один пост за раз",
        body=[
            "•  Выбрали промпт, заполнили переменные",
            "•  Сгенерировали — смотрите результат",
            "•  Сохранили или сразу опубликовали",
            "•  Подходит для штучных задач",
            "•  Идеально для писем, лендингов, тестов",
        ],
        accent_color=BLUE,
        # Tried ◆ (U+25C6) and ▶ (U+25B6) — both render as blank boxes
        # in our Arial build. ♦ (U+2666, Black Diamond Suit) IS in Arial
        # and still reads as "one focused unit".
        icon="♦",
    )
    card(
        c,
        MARGIN + card_w + 10 * mm, card_y, card_w, card_h,
        label="Bulk",
        title="Таблица как в Excel",
        body=[
            "•  Колонки = переменные + результаты",
            "•  Строки = по одному посту в каждой",
            "•  Запускаете генерацию по всей колонке",
            "•  Подходит для массовой генерации статей",
            "•  CSV-импорт + готовые шаблоны",
        ],
        accent_color=ACCENT,
        # ▦ (U+25A6 crosshatch square) is not in Arial; ■ (U+25A0 black
        # square) is. Still reads as "filled grid / table".
        icon="■",
    )


def slide_05_prompts(c: canvas.Canvas):
    """Prompts as a library — versioned, organized, AI-assisted."""
    slide_chrome(c, 5, TOTAL, "ПРОМПТЫ")
    big_title(c, "Промпты — единый источник правды", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Один раз настроили — все коллеги работают с теми же текстами и переменными.",
        PAGE_H - 48 * mm,
    )

    # Left column: bullet list
    bullet_list(
        c,
        MARGIN,
        PAGE_H - 62 * mm,
        [
            "Версии — каждое изменение сохраняется, можно откатить",
            "Переменные {{вот так}} — заполняются перед генерацией",
            "Категории и теги — папки + ярлыки",
            "ИИ помогает составить черновик промпта",
            "Песочница — тест промпта перед генерацией",
        ],
        bullet_color=ACCENT,
        line_height=11 * mm,
        font_size=13,
    )

    # Right: stylized "prompt card" mockup
    box_x = PAGE_W - MARGIN - 95 * mm
    box_y = MARGIN + 25 * mm
    box_w = 95 * mm
    box_h = 78 * mm
    c.setFillColor(white)
    c.setStrokeColor(BORDER)
    c.roundRect(box_x, box_y, box_w, box_h, 4 * mm, stroke=1, fill=1)

    # Header strip
    c.setFillColor(NAVY)
    c.roundRect(box_x, box_y + box_h - 12 * mm, box_w, 12 * mm, 4 * mm, stroke=0, fill=1)
    c.rect(box_x, box_y + box_h - 12 * mm, box_w, 6 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("BoldFont", 12)
    c.drawString(box_x + 5 * mm, box_y + box_h - 8 * mm, "SEO-вступление в блог")
    c.setFillColor(HexColor("#94A3B8"))
    c.setFont("RegFont", 9)
    c.drawRightString(box_x + box_w - 5 * mm, box_y + box_h - 8 * mm, "v3 · Анна")

    # Body
    c.setFillColor(TEXT)
    c.setFont("RegFont", 10)
    lines = [
        "Напиши вступление к статье про {{тема}},",
        "тон {{тональность}}, длина около {{слов}} слов.",
        "Аудитория — {{аудитория}}.",
    ]
    for i, ln in enumerate(lines):
        c.drawString(box_x + 5 * mm, box_y + box_h - 22 * mm - i * 6 * mm, ln)

    # Tags
    c.setFillColor(BLUE)
    c.setFont("BoldFont", 8)
    tags = ["blog", "seo", "intro"]
    tag_x = box_x + 5 * mm
    for tag in tags:
        text_w = c.stringWidth("#" + tag, "BoldFont", 8) + 6
        c.setFillColor(HexColor("#DBEAFE"))
        c.roundRect(tag_x, box_y + 18 * mm, text_w, 6 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(BLUE)
        c.drawString(tag_x + 3, box_y + 20 * mm, "#" + tag)
        tag_x += text_w + 4


def slide_06_folders(c: canvas.Canvas):
    """Drive-style organization everywhere."""
    slide_chrome(c, 6, TOTAL, "ОРГАНИЗАЦИЯ")
    big_title(c, "Папки везде, где это нужно", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Промпты, таблицы и сайты — всё раскладывается по папкам, как в Google Drive.",
        PAGE_H - 48 * mm,
    )

    # Three icon cards side by side
    items = [
        ("Промпты", "Категории + теги", BLUE),
        ("Bulk-таблицы", "Папки для проектов", ACCENT),
        ("Сайты для публикации", "Группы клиентов / регионов", GREEN),
    ]
    card_w = (PAGE_W - 2 * MARGIN - 20 * mm) / 3
    card_h = 60 * mm
    card_y = PAGE_H / 2 - card_h / 2 - 5 * mm

    for i, (title, desc, color) in enumerate(items):
        x = MARGIN + i * (card_w + 10 * mm)
        # Card
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, card_y, card_w, card_h, 4 * mm, stroke=1, fill=1)
        # Accent square as "folder"
        c.setFillColor(color)
        c.roundRect(x + 6 * mm, card_y + card_h - 22 * mm, 14 * mm, 12 * mm, 2 * mm, stroke=0, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.rect(x + 6 * mm, card_y + card_h - 26 * mm, 14 * mm, 4 * mm, stroke=0, fill=1)
        c.setFillColor(color)
        c.rect(x + 6 * mm, card_y + card_h - 26 * mm, 8 * mm, 3 * mm, stroke=0, fill=1)
        # Title + desc
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 14)
        c.drawString(x + 6 * mm, card_y + card_h - 35 * mm, title)
        c.setFillColor(MUTED)
        c.setFont("RegFont", 10)
        c.drawString(x + 6 * mm, card_y + card_h - 42 * mm, desc)

    # Bottom feature note
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 12)
    c.drawString(
        MARGIN,
        MARGIN + 22 * mm,
        "Плюс — поиск, хлебные крошки, перемещение между папками одним кликом.",
    )


def slide_07_tools(c: canvas.Canvas):
    """Bulk-table mini-tools — mass operations over a whole table, all
    revertable. AI Helper gets its own slide next, so it's referenced but
    not shown among these four."""
    slide_chrome(c, 7, TOTAL, "ИНСТРУМЕНТЫ ТАБЛИЦ")
    big_title(c, "Инструменты для таблиц", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Массовые операции над всей таблицей. Каждый запуск можно отменить.",
        PAGE_H - 48 * mm,
    )

    card_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    card_h = 55 * mm
    top_y = PAGE_H / 2 - 2 * mm
    bot_y = top_y - card_h - 6 * mm

    card(
        c,
        MARGIN, top_y, card_w, card_h,
        label="Найти и заменить",
        title="Массовая замена текста",
        body=[
            "•  Поиск и замена по всем ячейкам",
            "•  Поддержка regex",
            "•  Замены откатываются",
        ],
        accent_color=BLUE,
        icon="→",
    )
    card(
        c,
        MARGIN + card_w + 10 * mm, top_y, card_w, card_h,
        label="Проверка ссылок",
        title="Ссылки под контролем",
        body=[
            "•  Битые (404), выдуманные, пропущенные",
            "•  Чинит ссылки с ИИ прямо из результатов",
            "•  По всей таблице сразу",
        ],
        accent_color=ACCENT,
        icon="●",
    )
    card(
        c,
        MARGIN, bot_y, card_w, card_h,
        label="Структура и формат",
        title="Чистка вывода ИИ",
        body=[
            "•  markdown → HTML",
            "•  Убирает мусор в начале ответа",
            "•  Инлайн-стили, жирный / курсив",
        ],
        accent_color=GREEN,
        icon="■",
    )
    card(
        c,
        MARGIN + card_w + 10 * mm, bot_y, card_w, card_h,
        label="Нормализация",
        title="Единый вид значений",
        body=[
            "•  Пробелы, регистр, схема URL и слэши",
            "•  Приводит колонку к одному формату",
            "•  Откатывается",
        ],
        accent_color=PURPLE,
        icon="▲",
    )

    c.setFillColor(MUTED)
    c.setFont("ItalicFont", 11)
    c.drawString(
        MARGIN, MARGIN + 6 * mm,
        "AI-помощник — самый мощный из инструментов — на следующем слайде.",
    )


def slide_08_ai_helper(c: canvas.Canvas):
    """AI Helper — a prompt-driven per-cell AI mini-tool over a table."""
    slide_chrome(c, 8, TOTAL, "AI-ПОМОЩНИК")
    big_title(c, "AI-помощник по ячейкам", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Промпт + колонки → ИИ читает или правит каждую строку. Как формула, но текстом.",
        PAGE_H - 48 * mm,
    )

    # Left: what it does
    bullet_list(
        c,
        MARGIN,
        PAGE_H - 64 * mm,
        [
            "Read — результат в новую колонку",
            "Edit — правит текст на месте",
            "Несколько колонок за один прогон",
            "Дёшево: один вызов ИИ на строку",
            "Можно слать только первые N% текста",
            "Полный откат прогона",
        ],
        bullet_color=ACCENT,
        line_height=10 * mm,
        font_size=12,
    )

    # Right: sample table showing input → generated columns
    _sample_table(
        c,
        PAGE_W - MARGIN - 135 * mm, MARGIN + 20 * mm, 135 * mm, 86 * mm,
        label="Одна таблица — несколько ИИ-колонок",
        color=ACCENT,
        columns=["Контент", "Заголовок (ИИ)", "Мета (ИИ)"],
        rows=[
            ["<p>Ставки на спорт…</p>", "Ставки на спорт и киберспорт", "Коэффициенты и бонусы"],
            ["<p>Онлайн-казино…</p>", "Топ онлайн-казино 2026", "500+ слотов, бонус новичкам"],
            ["<p>Букмекеры…</p>", "Лучшие букмекеры России", "Легальные конторы: обзор"],
            ["<p>Слоты…</p>", "Играть в слоты онлайн", "Демо и на деньги, без риска"],
        ],
    )


def slide_09_grounding(c: canvas.Canvas):
    """Grounded generation — live Google Search + attached sources."""
    slide_chrome(c, 9, TOTAL, "ГЕНЕРАЦИЯ С ИСТОЧНИКАМИ")
    big_title(c, "Генерация с источниками", PAGE_H - 35 * mm)
    subtitle(
        c,
        "ИИ ищет тему в Google в реальном времени и прикладывает ссылки на источники.",
        PAGE_H - 48 * mm,
    )

    # Left: how it works
    bullet_list(
        c,
        MARGIN,
        PAGE_H - 64 * mm,
        [
            "Включается для отдельной колонки",
            "«Google Search — исследовать тему»",
            "Источники сохраняются и видны в ячейке",
            "Ссылки можно выгрузить в соседнюю колонку",
            "Нужен Google Vertex AI + модель Gemini",
            "Небольшая доплата за запрос — видна заранее",
        ],
        bullet_color=BLUE,
        line_height=10 * mm,
        font_size=12,
    )

    # Right: a "cell with sources" mock card
    box_x = PAGE_W - MARGIN - 120 * mm
    box_y = MARGIN + 28 * mm
    box_w = 120 * mm
    box_h = 72 * mm
    c.setFillColor(white)
    c.setStrokeColor(BORDER)
    c.roundRect(box_x, box_y, box_w, box_h, 4 * mm, stroke=1, fill=1)
    # Header
    c.setFillColor(NAVY)
    c.roundRect(box_x, box_y + box_h - 12 * mm, box_w, 12 * mm, 4 * mm, stroke=0, fill=1)
    c.rect(box_x, box_y + box_h - 12 * mm, box_w, 6 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("BoldFont", 11)
    c.drawString(box_x + 5 * mm, box_y + box_h - 8 * mm, "Ячейка · Источники (3)")

    sources = [
        ("sport-express.ru", "Обзор коэффициентов сезона", BLUE),
        ("rating-bet.ru", "Рейтинг букмекеров 2026", ACCENT),
        ("igaming-news.ru", "Тренды рынка ставок", GREEN),
    ]
    row_y = box_y + box_h - 24 * mm
    for domain, snippet, color in sources:
        c.setFillColor(color)
        c.circle(box_x + 8 * mm, row_y + 1.2 * mm, 1.6 * mm, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 10)
        c.drawString(box_x + 13 * mm, row_y, domain)
        c.setFillColor(MUTED)
        c.setFont("RegFont", 9)
        c.drawString(box_x + 13 * mm, row_y - 5 * mm, snippet)
        row_y -= 15 * mm


def _sample_table(
    c: canvas.Canvas,
    x: float, y: float, w: float, h: float,
    *,
    label: str,
    color,
    columns: list[str],
    rows: list[list[str]],
):
    """One labeled sample-table card. Used to show what a real content
    table looks like (import shapes on the publish slide; generated columns
    on the AI-helper slide).

    The data values are tiny — picked to fit the column widths at 7.5pt —
    but recognizable as content (slugs that look like slugs, languages that
    look like languages). Overlong cells are trimmed with an ellipsis.
    """
    # Card outline
    c.setFillColor(white)
    c.setStrokeColor(BORDER)
    c.roundRect(x, y, w, h, 3 * mm, stroke=1, fill=1)

    # Header band with the scenario label
    band_h = 9 * mm
    c.setFillColor(color)
    c.roundRect(x, y + h - band_h, w, band_h, 3 * mm, stroke=0, fill=1)
    c.rect(x, y + h - band_h, w, 3 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont("BoldFont", 10)
    c.drawString(x + 4 * mm, y + h - band_h + 3 * mm, label)

    # Table area below the band
    pad = 3 * mm
    table_left = x + pad
    table_right = x + w - pad
    table_top = y + h - band_h - pad
    table_bot = y + pad
    col_w = (table_right - table_left) / len(columns)
    row_h = (table_top - table_bot) / (len(rows) + 1)  # +1 for header

    # Header row
    c.setFillColor(HexColor("#E2E8F0"))
    c.rect(table_left, table_top - row_h, table_right - table_left, row_h, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 7.5)
    for i, col in enumerate(columns):
        c.drawString(table_left + i * col_w + 1.5 * mm, table_top - row_h + 1.8 * mm, col)

    # Data rows — alternating zebra stripe, tiny mono-ish look via RegFont
    for j, row in enumerate(rows):
        cur_y = table_top - row_h * (j + 2)
        if j % 2 == 1:
            c.setFillColor(HexColor("#F8FAFC"))
            c.rect(
                table_left, cur_y,
                table_right - table_left, row_h,
                stroke=0, fill=1,
            )
        c.setFillColor(TEXT)
        c.setFont("RegFont", 7.5)
        for i, cell in enumerate(row):
            cell_str = str(cell)
            # Trim with ellipsis if it would overflow the column
            max_w = col_w - 3 * mm
            while c.stringWidth(cell_str + "…", "RegFont", 7.5) > max_w and len(cell_str) > 3:
                cell_str = cell_str[:-1]
            if len(cell_str) < len(str(cell)):
                cell_str += "…"
            c.drawString(table_left + i * col_w + 1.5 * mm, cur_y + 1.8 * mm, cell_str)

    # Light grid lines between columns
    c.setStrokeColor(HexColor("#F1F5F9"))
    c.setLineWidth(0.3)
    for i in range(1, len(columns)):
        col_x = table_left + i * col_w
        c.line(col_x, table_bot, col_x, table_top)


def slide_10_publish(c: canvas.Canvas):
    """Publishing — the four import-table shapes (CMS-type × site-count),
    plus a note about Autotool as the third, pull-based delivery mode.
    """
    slide_chrome(c, 10, TOTAL, "ПУБЛИКАЦИЯ")
    big_title(c, "Как выглядит таблица для импорта", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Четыре сценария — четыре формы таблицы. Колонка домена появляется только когда сайтов несколько.",
        PAGE_H - 48 * mm,
    )

    # 2×2 grid of mini-tables
    card_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    card_h = 50 * mm
    top_y = PAGE_H / 2 - 2 * mm
    bot_y = top_y - card_h - 6 * mm

    # WP single — basic post fields
    _sample_table(
        c,
        MARGIN, top_y, card_w, card_h,
        label="WordPress · один сайт",
        color=BLUE,
        columns=["title", "content", "slug", "status"],
        rows=[
            ["Зимняя распродажа", "<p>Скидки до 50%…</p>", "winter-sale", "publish"],
            ["Гид по подаркам", "<p>Идеи для друзей…</p>", "gift-guide", "publish"],
            ["Анонс коллекции", "<p>Скоро в продаже…</p>", "spring-coll", "draft"],
        ],
    )

    # WP multi — adds domain column upfront
    _sample_table(
        c,
        MARGIN + card_w + 10 * mm, top_y, card_w, card_h,
        label="WordPress · несколько сайтов",
        color=PURPLE,
        columns=["domain", "language", "title", "content"],
        rows=[
            ["shop-ru.example", "ru", "Зимняя распродажа", "<p>Скидки до 50%…</p>"],
            ["shop-de.example", "de", "Winter-Sale", "<p>Bis zu 50% Rabatt…</p>"],
            ["news.example.org", "en", "Q4 results", "<p>Strong growth…</p>"],
        ],
    )

    # Custom CMS single — placeholder-driven fields (no `status`, has seo_*)
    _sample_table(
        c,
        MARGIN, bot_y, card_w, card_h,
        label="Custom CMS · один сайт",
        color=ACCENT,
        columns=["title", "content", "slug", "seo_title"],
        rows=[
            ["Зимняя распродажа", "<p>Скидки до 50%…</p>", "winter-sale", "Зимняя распродажа · Сэкономьте"],
            ["Гид по подаркам", "<p>Идеи для друзей…</p>", "gift-guide", "Лучшие подарки 2026"],
            ["Анонс коллекции", "<p>Скоро в продаже…</p>", "spring-coll", "Весенняя коллекция"],
        ],
    )

    # Custom CMS multi — domain + language up front
    _sample_table(
        c,
        MARGIN + card_w + 10 * mm, bot_y, card_w, card_h,
        label="Custom CMS · несколько сайтов",
        color=GREEN,
        columns=["domain", "language", "title", "slug"],
        rows=[
            ["crm.example.com", "ru", "Зимняя распродажа", "winter-sale"],
            ["api.client-a.com", "en", "Holiday gift guide", "holiday-guide"],
            ["api.client-b.com", "de", "Frühjahrs-Look", "spring-look"],
        ],
    )

    # Third delivery mode: Autotool (pull-based public CSV)
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 11)
    c.drawString(MARGIN, MARGIN + 9 * mm, "Третий способ — Autotool")
    c.setFillColor(TEXT)
    c.setFont("RegFont", 10.5)
    c.drawString(
        MARGIN, MARGIN + 3.5 * mm,
        "таблица отдаётся публичным CSV по секретной ссылке — внешний сервис сам забирает строки и публикует.",
    )


def slide_11_providers(c: canvas.Canvas):
    """Multiple AI providers."""
    slide_chrome(c, 11, TOTAL, "AI-ПРОВАЙДЕРЫ")
    big_title(c, "Несколько AI-провайдеров", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Не заперты в одной модели: переключаетесь между ними прямо из интерфейса.",
        PAGE_H - 48 * mm,
    )

    # 4 provider boxes in a row
    providers = [
        ("Google AI Studio", "Gemini · API-ключ", BLUE),
        ("Google Vertex AI", "Корпоративные квоты · GCP", ACCENT),
        ("OpenRouter", "Claude, GPT, Llama — всё в одном", GREEN),
        ("GitHub Models", "OpenAI / Meta · через GitHub", PURPLE),
    ]
    card_w = (PAGE_W - 2 * MARGIN - 30 * mm) / 4
    card_h = 65 * mm
    card_y = PAGE_H / 2 - card_h / 2 - 5 * mm

    for i, (name, desc, color) in enumerate(providers):
        x = MARGIN + i * (card_w + 10 * mm)
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, card_y, card_w, card_h, 4 * mm, stroke=1, fill=1)
        # Colored circle at top
        c.setFillColor(color)
        c.circle(x + card_w / 2, card_y + card_h - 16 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("BoldFont", 14)
        c.drawCentredString(x + card_w / 2, card_y + card_h - 18 * mm, str(i + 1))
        # Name
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 12)
        c.drawCentredString(x + card_w / 2, card_y + card_h - 32 * mm, name)
        # Desc — wrap
        c.setFillColor(MUTED)
        c.setFont("RegFont", 9)
        for j, line in enumerate(desc.split(" · ")):
            c.drawCentredString(
                x + card_w / 2,
                card_y + card_h - 42 * mm - j * 5 * mm,
                line,
            )

    # Footer note
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 11)
    c.drawString(
        MARGIN,
        MARGIN + 18 * mm,
        "Каждый промпт или колонка может работать со своей моделью — на одну задачу тонкая, на другую самая сильная.",
    )


def slide_12_roles(c: canvas.Canvas):
    """Roles: admin / manager / content_generator."""
    slide_chrome(c, 12, TOTAL, "РОЛИ И ДОСТУП")
    big_title(c, "Роли — каждый видит своё", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Менеджеры управляют людьми и сайтами, контент-генераторы — пишут.",
        PAGE_H - 48 * mm,
    )

    # Three role cards. Bullets kept short enough to fit the ~80mm card
    # width at 11pt — longer phrasing wraps off the right edge.
    roles = [
        ("Admin",
         "Полный контроль",
         ["Настройки и AI-ключи",
          "Пользователи и роли",
          "Логи, расходы, бэкапы"],
         NAVY),
        ("Manager",
         "Управление проектами",
         ["Сайты и публикация",
          "Пользователи команды",
          "История работы"],
         BLUE),
        # Content generator deliberately omits publishing — only admin and
        # manager can publish in the current role matrix.
        ("Content generator",
         "Создаёт контент",
         ["Свои промпты и таблицы",
          "Single и Bulk генерация",
          "Сохранение черновиков"],
         ACCENT),
    ]
    card_w = (PAGE_W - 2 * MARGIN - 20 * mm) / 3
    card_h = 90 * mm
    card_y = MARGIN + 15 * mm

    for i, (title, sub, perms, color) in enumerate(roles):
        x = MARGIN + i * (card_w + 10 * mm)
        # Card
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, card_y, card_w, card_h, 4 * mm, stroke=1, fill=1)
        # Top color block
        c.setFillColor(color)
        c.roundRect(x, card_y + card_h - 20 * mm, card_w, 20 * mm, 4 * mm, stroke=0, fill=1)
        c.rect(x, card_y + card_h - 20 * mm, card_w, 8 * mm, stroke=0, fill=1)
        # Title
        c.setFillColor(white)
        c.setFont("BoldFont", 18)
        c.drawString(x + 6 * mm, card_y + card_h - 10 * mm, title)
        c.setFillColor(HexColor("#E2E8F0"))
        c.setFont("RegFont", 10)
        c.drawString(x + 6 * mm, card_y + card_h - 17 * mm, sub)
        # Permissions — bullet is drawn as a small filled circle (a real
        # shape, not a glyph) so we don't depend on Arial having ✓ U+2713
        # (which it doesn't in our build — used to render as a blank box).
        line_y = card_y + card_h - 32 * mm
        for p in perms:
            c.setFillColor(color)
            # Circle baseline lifted ~1.2 mm so the dot visually centers
            # on the text x-height of the label next to it.
            c.circle(x + 7 * mm, line_y + 1.2 * mm, 1.4 * mm, stroke=0, fill=1)
            c.setFillColor(TEXT)
            c.setFont("RegFont", 11)
            c.drawString(x + 12 * mm, line_y, p)
            line_y -= 8 * mm


def slide_13_safety(c: canvas.Canvas):
    """Visibility & safety: trash, errors, spend, publish history, backups."""
    slide_chrome(c, 13, TOTAL, "ВИДИМОСТЬ И БЕЗОПАСНОСТЬ")
    big_title(c, "Ничего не теряется, всё видно", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Привычные «откатить», «посмотреть, что сломалось», «сколько мы потратили».",
        PAGE_H - 48 * mm,
    )

    # Five cards in a row — short one-word titles so they fit the ~44mm width
    # at 14pt. Only Расходы carries a glyph ("$"); Arial lacks ♻ / ⚠ / 📜 / 💾
    # so those cards stay icon-less rather than rendering broken boxes.
    items = [
        ("Корзина", "Восстановить\nудалённое (50 дн.)", BLUE, ""),
        ("Ошибки", "Все сбои\nс фильтрами", ACCENT, ""),
        ("Расходы", "Траты на ИИ\nпо людям", GREEN, "$"),
        ("Публикации", "Кто, куда,\nкогда, код", PURPLE, ""),
        ("Бэкапы", "Дамп базы\nкаждый день, S3", BLUE, ""),
    ]
    card_w = (PAGE_W - 2 * MARGIN - 40 * mm) / 5
    card_h = 72 * mm
    card_y = PAGE_H / 2 - card_h / 2 - 5 * mm

    for i, (title, desc, color, glyph) in enumerate(items):
        x = MARGIN + i * (card_w + 10 * mm)
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, card_y, card_w, card_h, 4 * mm, stroke=1, fill=1)
        # Top accent stripe
        c.setFillColor(color)
        c.roundRect(x, card_y + card_h - 4 * mm, card_w, 4 * mm, 2 * mm, stroke=0, fill=1)
        c.rect(x, card_y + card_h - 4 * mm, card_w, 2 * mm, stroke=0, fill=1)
        # Big glyph — only drawn when one is supplied.
        if glyph:
            c.setFillColor(color)
            c.setFont("BoldFont", 36)
            c.drawString(x + 5 * mm, card_y + card_h - 26 * mm, glyph)
        # Title
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 14)
        c.drawString(x + 5 * mm, card_y + card_h - 40 * mm, title)
        # Desc
        c.setFillColor(TEXT)
        c.setFont("RegFont", 9.5)
        for j, line in enumerate(desc.split("\n")):
            c.drawString(x + 5 * mm, card_y + card_h - 49 * mm - j * 5 * mm, line)


def slide_14_demo(c: canvas.Canvas):
    """Demo agenda — what to expect live."""
    slide_chrome(c, 14, TOTAL, "ЧТО БУДЕТ В ДЕМО")
    big_title(c, "Что увидите вживую", PAGE_H - 35 * mm)
    subtitle(
        c,
        "Эти 6 шагов покажу на демо — сохраните слайд, чтобы потом восстановить картинку.",
        PAGE_H - 48 * mm,
    )

    # Labels trimmed to ≤ ~24 chars so they fit the card width minus the
    # number-badge column at 13pt bold.
    steps = [
        ("01", "Логин и интерфейс", BLUE),
        ("02", "Создание промпта", ACCENT),
        ("03", "Single и Bulk генерация", GREEN),
        ("04", "Инструменты + AI-помощник", PURPLE),
        ("05", "Публикация и Autotool", BLUE),
        ("06", "Корзина, бэкапы, расходы", ACCENT),
    ]

    # 2 columns × 3 rows grid
    col_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    row_h = 22 * mm
    grid_top = PAGE_H - 70 * mm

    for i, (num, label, color) in enumerate(steps):
        col = i % 2
        row = i // 2
        x = MARGIN + col * (col_w + 10 * mm)
        y = grid_top - row * (row_h + 4 * mm) - row_h

        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, y, col_w, row_h, 3 * mm, stroke=1, fill=1)
        # Number badge — drawCentredString places the BASELINE at the given
        # y; offset ~half a cap-height below the circle center so the digit
        # sits centered.
        c.setFillColor(color)
        c.circle(x + 12 * mm, y + row_h / 2, 7 * mm, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("BoldFont", 13)
        c.drawCentredString(x + 12 * mm, y + row_h / 2 - 1.7 * mm, num)
        # Label
        c.setFillColor(NAVY)
        c.setFont("BoldFont", 13)
        c.drawString(x + 26 * mm, y + row_h / 2 - 1.7 * mm, label)


def slide_15_closing(c: canvas.Canvas):
    """Closing — what to do next."""
    slide_chrome(c, 15, TOTAL, "ДАЛЬШЕ")

    # Big closing message
    c.setFillColor(NAVY)
    c.setFont("BoldFont", 44)
    c.drawString(MARGIN, PAGE_H / 2 + 18 * mm, "Готовы?")
    c.setFillColor(ACCENT)
    c.rect(MARGIN, PAGE_H / 2 + 14 * mm, 22 * mm, 2 * mm, stroke=0, fill=1)

    c.setFillColor(TEXT)
    c.setFont("RegFont", 16)
    c.drawString(
        MARGIN,
        PAGE_H / 2 - 2 * mm,
        "На демо покажу всё, что в этой презентации, — в реальном интерфейсе.",
    )
    c.drawString(
        MARGIN,
        PAGE_H / 2 - 14 * mm,
        "Берите ноутбук — после демо вы сможете залогиниться и попробовать.",
    )

    # Three small action cards at the bottom
    actions = [
        ("До демо", "Просмотрите эти слайды — они займут 5 минут.", BLUE),
        ("На демо", "Задавайте вопросы по ходу. Все увиденные функции — рабочие.", ACCENT),
        ("После демо", "Доступ выдам по списку. Возвращайтесь к слайдам для напоминания.", GREEN),
    ]
    card_w = (PAGE_W - 2 * MARGIN - 20 * mm) / 3
    card_h = 38 * mm
    card_y = MARGIN + 18 * mm

    for i, (title, desc, color) in enumerate(actions):
        x = MARGIN + i * (card_w + 10 * mm)
        c.setFillColor(white)
        c.setStrokeColor(BORDER)
        c.roundRect(x, card_y, card_w, card_h, 3 * mm, stroke=1, fill=1)
        c.setFillColor(color)
        c.roundRect(x, card_y + card_h - 3 * mm, card_w, 3 * mm, 1.5 * mm, stroke=0, fill=1)
        c.rect(x, card_y + card_h - 3 * mm, card_w, 1.5 * mm, stroke=0, fill=1)
        c.setFillColor(color)
        c.setFont("BoldFont", 10)
        c.drawString(x + 6 * mm, card_y + card_h - 12 * mm, title.upper())
        c.setFillColor(TEXT)
        c.setFont("RegFont", 10)
        # Wrap
        words = desc.split(" ")
        line, lines = "", []
        for w in words:
            test = (line + " " + w).strip()
            if c.stringWidth(test, "RegFont", 10) > card_w - 12 * mm:
                lines.append(line)
                line = w
            else:
                line = test
        if line:
            lines.append(line)
        for j, ln in enumerate(lines[:3]):
            c.drawString(x + 6 * mm, card_y + card_h - 20 * mm - j * 5 * mm, ln)


# ---------- build ----------

def build(path: Path):
    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    c.setTitle("Content Beast — обзор")
    c.setAuthor("Content Beast")
    c.setSubject("Внутренний инструмент для генерации и публикации контента")

    slides = [
        slide_01_title,
        slide_02_what,
        slide_03_flow,
        slide_04_modes,
        slide_05_prompts,
        slide_06_folders,
        slide_07_tools,
        slide_08_ai_helper,
        slide_09_grounding,
        slide_10_publish,
        slide_11_providers,
        slide_12_roles,
        slide_13_safety,
        slide_14_demo,
        slide_15_closing,
    ]
    for fn in slides:
        fn(c)
        c.showPage()
    c.save()


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "content-beast-overview-ru.pdf"
    build(out)
    print(f"wrote {out}")
