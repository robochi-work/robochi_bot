from django.core.handlers.wsgi import WSGIRequest
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from work.blocks.registry import block_registry
from work.choices import WorkProfileRole


@login_required
def index(request: WSGIRequest):
    # If phone not confirmed, redirect to phone-required page
    if not request.user.phone_number:
        return redirect('work:phone_required')

    profile = getattr(request.user, 'work_profile', None)

    # Administrator — separate dashboard
    if profile and profile.role == WorkProfileRole.ADMINISTRATOR:
        return render(request, 'work/admin_dashboard.html', {
            'work_profile': profile,
        })

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
