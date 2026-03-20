from django.core.handlers.wsgi import WSGIRequest
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from work.blocks.registry import block_registry


@login_required
def index(request: WSGIRequest):
    # If phone not confirmed, redirect to phone-required page
    if not request.user.phone_number:
        from django.shortcuts import redirect
        return redirect('work:phone_required')
    blocks = []
    for block in block_registry.get_visible_blocks(request):
        ctx = block.get_context(request)
        ctx['block'] = block
        blocks.append(ctx)

    context = {
        "rendered_blocks": blocks,
        'work_profile': request.user.work_profile,
    }
    return render(request, 'work/index.html', context=context)
