# Frontend examples for robochi_bot skill v2

## Example 1
Task:
The mobile layout is broken and the buttons overlap.

Good response style:
1. Explain probable cause from provided CSS/HTML
2. Point to exact file
3. Show exact "before / after" CSS fragment
4. Tell what to test on mobile after applying

## Example 2
Task:
Need to improve role selection buttons without rewriting the whole page.

Good response style:
1. Keep current structure
2. Edit only button block and related CSS
3. Preserve existing semantics
4. Show exact fragment change
5. Mention hover/active/mobile states to test
6. Warn if tracking hooks may be affected

## Example 3
Task:
A modal window does not fit inside Telegram Mini App viewport.

Good response style:
1. Explain why fixed heights or viewport units may be the cause
2. Point to exact modal styles
3. Give minimal patch
4. Mention Telegram WebApp viewport check

## Example 4
Task:
Need to connect a UI button to Telegram MainButton or another Telegram WebApp action.

Good response style:
1. Ask for current integration code if missing
2. Do not invent initialization
3. Show exact JS fragment to update
4. Explain what should happen after click
5. Mention what to test inside Telegram

## Example 5
Task:
Need to improve one section visually.

Good response style:
1. Preserve project style
2. Avoid redesigning unrelated blocks
3. Change only local HTML/CSS
4. Explain how the section becomes more readable

## Example 6
Task:
Need to update CTA markup but preserve analytics.

Good response style:
1. Identify existing ids/classes/data attributes/event bindings
2. Preserve them unless change is explicitly requested
3. Show minimal markup update
4. Mention how to verify tracking still fires
