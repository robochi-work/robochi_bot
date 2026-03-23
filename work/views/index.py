from django.core.handlers.wsgi import WSGIRequest
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from work.blocks.registry import block_registry


@login_required
def index(request: WSGIRequest):
    user = request.user

    # If phone not confirmed, redirect to phone-required page
    if not user.phone_number:
        return redirect('work:phone_required')

    # Administrator — separate dashboard, skip wizard check
    if user.is_staff:
        return render(request, 'work/admin_dashboard.html', {
            'work_profile': getattr(user, 'work_profile', None),
        })

    profile = getattr(user, 'work_profile', None)

    # Employer / Worker — standard block-based dashboard
    blocks = []
    for block in block_registry.get_visible_blocks(request):
        ctx = block.get_context(request)
        ctx['block'] = block
        blocks.append(ctx)

    context = {
        "rendered_blocks": blocks,
        'work_profile': profile,
    }
    return render(request, 'work/index.html', context=context)
