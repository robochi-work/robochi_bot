# PROJECT_RULES.md --- robochi_bot Development Rules

This document defines **rules that AI assistants and developers must
follow** when modifying the robochi_bot repository.

## General Principles

1.  Never break production.
2.  Always explain changes before applying them.
3.  Always give commands that can be executed on the server.
4.  Never expose secrets.

## Server Development Model

All development happens on the server through SSH.

Workflow:

1.  AI explains the task
2.  AI provides bash commands
3.  Artem executes them
4.  Artem returns terminal output
5.  AI analyzes the output

AI must assume it **cannot access the server directly**.

## Git Rules

Development branch:

develop

Typical workflow:

git add `<files>`{=html} git commit -m "description" git push origin
develop

Never push directly to main.

## Security Rules

Never commit:

.env tokens private keys

Never print:

Telegram bot token webhook secret database passwords

## Django Rules

Always run:

python3 manage.py check

When models change:

python3 manage.py makemigrations python3 manage.py migrate

Never modify migrations that were already applied in production.

## Service Restart Rules

If Python code changes:

sudo systemctl restart gunicorn.service

If Celery tasks change:

sudo systemctl restart celery-worker sudo systemctl restart celery-beat

## Logging

Gunicorn logs:

sudo journalctl -u gunicorn.service --since "10 min ago" --no-pager

Celery logs:

sudo journalctl -u celery-worker --since "10 min ago" --no-pager

## Debugging

Check service status:
```bash
sudo systemctl status gunicorn.service
sudo systemctl status celery-worker.service
sudo systemctl status celery-beat.service
```

Check service logs:
```bash
sudo journalctl -u gunicorn.service --since "10 min ago"
sudo journalctl -u celery-worker.service --since "10 min ago"
```

Application logs:
```bash
tail -f logs/django.log
tail -f logs/bot.log
tail -f logs/errors.log
```

## AI Behavior Rules

AI must:

explain tasks generate ready commands request output analyze logs

AI must not:

guess server state invent file paths invent secrets

## Invariants (architectural rules — do not break)

Each invariant has stable ID (INV-NNN), reasoning, and where enforced.

### INV-001: One role per telegram_id
User registers as Worker OR Employer, never both. Enforced in wizard registration flow.

### INV-002: User.id == Telegram user_id
Django PK equals Telegram user_id. No separate telegram_id field.

### INV-003: Group.id == Telegram chat_id (negative int)
Group PK equals Telegram chat_id (e.g. -100123...).
Enforced: telegram/models.py → Group(Chat).

### INV-004: Bot does NOT create invite_links automatically
Reason: Bot API limitations (can_invite_users=True auto-generates primary link; export_chat_invite_link revokes existing).
Enforced: service/group.py — no create_chat_invite_link / export_chat_invite_link in business logic.
Exception: admin manually creates links in Telegram UI and pastes into Django admin.
Decided: sessions 31.03.2026, 11.04.2026.

### INV-005: All entry checks happen in callback handler (apply_vacancy.py)
Reason: `chat_join_request` handler (`auto_approve`) does NOT trigger for standard invite links. All 12 filtering checks (block, gender, role, capacity) run in the callback handler `telegram/handlers/callback/apply_vacancy.py`. The `chat_member_handler` in `group.py` has a safety-net INV-005 FIX block that kicks users who somehow bypass the callback.
Enforced in: `telegram/handlers/callback/apply_vacancy.py`, `telegram/handlers/member/user/group.py`

### INV-006: Channel invite_links use creates_join_request=False
Reason: channels are for browsing — filtering happens at "Apply for vacancy" button click (leads to group where INV-005 applies).
Enforced: telegram/handlers/member/bot/channel.py:22.

### INV-007: chat_member_handler has safety-net filters (INV-005 FIX)
Reason: Primary filtering is in callback handler (INV-005). The `chat_member_handler` has a secondary INV-005 FIX block that kicks users who bypass the callback (e.g. if someone shares an invite link directly). Admin bypass: admins get `UserInGroup` with ADMINISTRATOR status but no `VacancyUser` record.
Enforced in: `telegram/handlers/member/user/group.py`

### INV-008: supergroup guard in both group handlers
Reason: Telegram sends chat_member/chat_join_request events with linked channel IDs — without guard, channels get inserted into Group table.
Enforced: group.py:26 (auto_approve), group.py:~206 (handle_user_status_change) — both `if chat.type != "supergroup": return`.
Regression test: tests/test_bugfix_channel_in_groups.py.
Decided: 09.04.2026.

### INV-009: User.is_active=False ONLY for BlockType.PERMANENT
Reason: BlockService.block_user sets is_active=False only for PERMANENT blocks.
TEMPORARY blocks leave is_active=True; active block status determined by UserBlock.is_active=True.
Consequence: admin filters must use blocks__is_active=True, NOT is_active=False (user/models.py → UserBlock with related_name="blocks").
Enforced: user/services.py → BlockService.block_user.
Bug history: work/views/admin_panel.py:78 used is_active=False until 16.04.2026 — fixed to blocks__is_active=True.
Regression test: TODO.
