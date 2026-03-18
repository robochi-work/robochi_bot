# Backend examples for robochi_bot skill v2

## Example 1
Task:
A Django traceback appears after saving a form.

Good response style:
1. Read traceback carefully
2. Identify first relevant project frame
3. Explain root cause simply
4. Point to exact file and exact place
5. Show minimal "before / after"
6. Say what to test after patch

## Example 2
Task:
Need to add a new field to a model.

Good response style:
1. Show exact model fragment
2. Show serializer change if needed
3. Explicitly state migration is required
4. Mention validation and API effect
5. Tell what to test

## Example 3
Task:
Business logic is too heavy inside a Django view.

Good response style:
1. Explain why current view is overloaded
2. Suggest minimal extraction if code supports it
3. Do not redesign everything
4. Show exact local move in "before / after" format
5. Mention what must remain compatible

## Example 4
Task:
Celery task behaves incorrectly.

Good response style:
1. Separate task logic from queue/config assumptions
2. Ask for current task code if missing
3. Do not invent retries or broker settings
4. Show exact patch only after code is provided
5. Mention what to test after running worker

## Example 5
Task:
Need to optimize a slow queryset.

Good response style:
1. Explain current ORM problem
2. Suggest exact local improvement
3. Warn about behavior changes if relevant
4. Show "before / after"
5. Mention what result and performance must be checked

## Example 6
Task:
Need to change backend internals without breaking API contract.

Good response style:
1. State the current contract that must remain unchanged
2. Show only internal patch
3. Mention serializer/view/service impact explicitly
4. Tell what response fields and status codes must be retested
