## ⚠️ Before doing anything — load context in this order:
1. Read AGENTS.md → AI_QUICK_START.md → docs/PROJECT_CONTEXT.md (tail for recent sessions)
2. Check PROJECT_RULES.md → section "Invariants" for hard rules
3. Use conversation_search tool to find prior discussions

---

# Claude Code Instructions for robochi_bot

## Project
Django + Telegram Bot + Telegram Mini App (WebApp) for short-term job matching in Ukrainian cities.
Server: `/home/webuser/robochi_bot/` on Fornex VPS, domain `robochi.pp.ua`.

## Critical Rules

### Before any manage.py command:
```bash
set -a; source .env; set +a
```

### Deploy after every change:
```bash
python3 manage.py collectstatic --clear --noinput
sudo systemctl restart gunicorn.service
```

### CSS file requires force-add:
```bash
git add -f telegram/static/css/styles.css
```

### PostgreSQL:
Always use `-h localhost -p 5432` (not default 5433).

### Tests:
```bash
DJANGO_SETTINGS_MODULE=config.django.local pytest tests/ -v
```

## CSS Architecture (Clean Slate Theme — April 2026)

### Theme System
- File: `telegram/static/css/styles.css`
- Light: `--background: #f1f5f9`, `--card: #ffffff`, `--primary: #6366f1`, `--border: #cbd5e1`
- Dark (via `prefers-color-scheme: dark`): `--background: #0f172a`, `--card: #1e293b`, `--primary: #818cf8`
- **Never hardcode colors** — always use `var(--variable-name)`
- Legacy aliases (`--btn-bg`, `--btn-shadow`, `--accent-dark`, `--steel-bottom`) mapped to new vars for backward compatibility with inline `<style>` blocks

### Key CSS Classes
- `.btn-primary` — indigo filled button (primary actions)
- `.btn-secondary` — white/bordered button (secondary actions)
- `.btn-danger` — red destructive button
- `.worker-btn` — dashboard card-button with icon + title + subtitle
- `.worker-btn--compact` — smaller variant for top/bottom pinned buttons
- `.modal-overlay` + `.modal-card` — centered alert modal
- `.modal-overlay` + `.modal-sheet` — bottom sheet modal (admin forms)
- `.modal-field`, `.modal-label`, `.modal-select`, `.modal-textarea` — form fields inside modals
- `.employer-layout` — 3-zone dashboard layout (top/middle/bottom)
- `.admin-tabs` + `.admin-tab` — reui-style tabs with sliding indicator

### Dashboard Layout Pattern
```html
<div class="employer-layout">
    <div class="employer-top"><!-- pinned top --></div>
    <div class="employer-middle"><!-- centered content --></div>
    <div class="employer-bottom"><!-- pinned bottom --></div>
</div>
```

### Adding New Modals
Use CSS classes, NOT inline styles:
```html
<div id="my-modal" class="modal-overlay" style="display:none;">
    <div class="modal-card">
        <p class="modal-text">Message text</p>
        <button class="btn-primary" onclick="...">OK</button>
    </div>
</div>
```

### Android Telegram WebApp Constraints
- Native `<select>` picker cannot be styled via CSS (system UI)
- `<select>` option filtering via JS breaks on Android — use server-side rendering
- Always test on mobile Telegram (not just desktop)

## File Structure (key files)
telegram/static/css/styles.css     — ALL styles (Clean Slate theme)
templates/base.html                — base template
work/templates/work/
worker_dashboard.html            — Worker ЛК
employer_dashboard.html          — Employer ЛК
admin_dashboard.html             — Admin ЛК
admin_search_results.html        — Admin user/vacancy search
admin_vacancy_card.html          — Admin vacancy card
admin_moderate_vacancy.html      — Admin moderation page
vacancy/templates/vacancy/
vacancy_form.html                — Vacancy creation form
vacancy_detail.html              — Vacancy detail page
vacancy_my_list.html             — My vacancies list
vacancy_members.html             — Members management
vacancy_user_list.html           — User list with modal
vacancy_payment.html             — Payment page

## Git Workflow
- Working branch: `develop`
- Exclude from commits: `celerybeat-schedule.bak/.dat/.dir`
- Pre-commit hooks: ruff check/format, django-upgrade, trailing-whitespace
- After pre-commit auto-fixes: `git add -u && git commit`

## FAQ System (FaqItem — April 2026)

### Model
- `work.models.FaqItem` — dynamic FAQ entries managed from Django admin
- Fields: `role` (employer/worker), `question`, `answer`, `image` (ImageField), `video_url` (YouTube URL), `order`, `is_active`
- `video_embed_url` property — auto-converts YouTube watch/youtu.be URLs to embed format
- Separate FAQ entries for Employer and Worker roles
- Admin: `/taya-panel/` → FAQ записи (filterable by role, sortable by order)

### Pages
- Employer: `/work/employer/faq/` → `work:employer_faq` → `employer_faq.html`
- Worker: `/work/faq/` → `work:worker_faq` → `worker_faq.html`
- Button label: **«Як це працює?»** (renamed from «Що робити якщо?»)

### Templates
- Dynamic content from DB via `faq_items` context
- `<details>` accordion with optional image (fullscreen on click) and video (YouTube iframe embed)
- Empty state: «Інформація поки що не додана.»

### Media
- MEDIA_URL = `/media/`, MEDIA_ROOT = `BASE_DIR / "media"`
- Nginx serves `/media/` → `/home/webuser/robochi_bot/media/`
- Images uploaded to `media/faq/`
- Video: YouTube URL only (no file upload) — embed iframe in template
