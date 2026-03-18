# Frontend project notes for robochi_bot v2

## Purpose
This file gives additional context for frontend decisions inside the skill.

## Product context
robochi_bot is a Telegram Mini App related to job/work workflows.

Frontend decisions should support:
- fast understanding
- simple interaction
- low friction
- role-based user flow
- stable work inside Telegram mobile environment

## Developer preferences
Important preferences for answers:
- explain in Russian unless explicitly asked otherwise
- explain step by step
- do not give the whole file if only one fragment must be changed
- always give exact file path
- always give exact place for the change
- always provide "before / after"
- if current code is missing, request the exact current file from repository
- do not invent code structure
- formulate the task understanding first
- prefer point changes, not full rewrites

## Frontend priorities
- clarity
- stable mobile layout
- minimal regressions
- exact local edits
- preserving current architecture
- preserving current design direction unless redesign is requested
- preserving Telegram Mini App stability
- preserving existing tracking hooks if present

## Likely frontend areas
These are likely but must be confirmed from real code:
- landing blocks
- role selection blocks
- forms
- modal windows
- call-to-action buttons
- responsive sections
- static CSS and JS
- template-based rendering
- Telegram WebApp buttons and viewport logic
- analytics event bindings for important actions

## Common risks
- breaking layout on mobile
- breaking Telegram Mini App viewport
- global CSS side effects
- changing spacing across unrelated pages
- changing shared template blocks unintentionally
- removing classes or attributes used by tracking
- breaking role-select buttons or modal actions

## What good answers look like
A good answer:
- explains what is wrong
- points to exact file and place
- gives only the necessary patch
- warns about side effects
- tells what to test after change

A bad answer:
- rewrites everything
- invents missing structure
- mixes backend and frontend
- hides uncertainty
- gives vague advice without exact edit location
