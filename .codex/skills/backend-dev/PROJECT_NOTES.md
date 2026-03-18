# Backend project notes for robochi_bot v2

## Purpose
This file gives additional context for backend decisions inside the skill.

## Product context
robochi_bot backend supports a Telegram Mini App and related platform logic.

Backend suggestions should prioritize:
- correctness
- clear explanation
- minimal safe edits
- stability
- preserving architecture
- explicit risk awareness

## Developer preferences
Important preferences for answers:
- explain in Russian unless explicitly asked otherwise
- explain step by step
- do not rewrite the whole file if a fragment is enough
- always provide exact file path
- always provide exact place for the change
- always show "before / after"
- if actual code is missing, request the current file from repository
- do not invent structure or hidden logic
- formulate task understanding first
- separate code changes from commands and tests

## Likely backend areas
These are likely but must be confirmed from real code:
- Django apps
- models
- serializers
- views
- services
- tasks
- settings
- PostgreSQL-backed persistence
- Redis/Celery integrations
- Telegram-related backend modules
- environment-specific settings logic

## Common backend risks
- changing business logic unintentionally
- breaking API compatibility
- forgetting migrations
- introducing side effects
- hiding assumptions
- suggesting commands without tying them to exact code change
- mixing infrastructure advice with code edits without clear separation
- breaking Telegram integration flow
- changing async behavior without warning

## What good answers look like
A good answer:
- explains the root cause
- points to exact file and exact place
- gives minimal patch
- separates code changes from commands
- mentions migrations if needed
- tells what to test
- warns about risks

A bad answer:
- invents models or endpoints
- rewrites a large module without reason
- gives vague advice
- hides uncertainty
- mixes backend and frontend
