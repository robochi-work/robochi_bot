# ARCHITECTURE.md --- robochi_bot System Architecture

## Overview

robochi_bot is a Telegram-based platform connecting employers and
workers.

System architecture:

Telegram Client \| v Telegram Bot (pyTelegramBotAPI) \| v Nginx -\>
Gunicorn -\> Django \| +--- PostgreSQL \| +--- Redis \| +--- Celery
Workers

## Components

### Telegram Bot

Handles: - /start command - user interaction - WebApp buttons

### Django Backend

Responsibilities:

-   user accounts
-   job listings
-   Telegram authentication
-   Mini App pages

### Celery

Runs background tasks:

-   notifications
-   scheduled jobs
-   heavy processing

### Redis

Message broker for Celery.

### PostgreSQL

Main database.

### Nginx + Gunicorn

Nginx receives HTTP traffic. Gunicorn runs Django.

## Telegram Mini App Flow

1 User clicks WebApp button 2 Telegram opens web page 3
telegram-web-app.js loads 4 initData injected 5 initData sent to backend
6 Backend verifies signature 7 User logged in

Reference:

https://core.telegram.org/bots/webapps
