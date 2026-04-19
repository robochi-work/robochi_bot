from django.shortcuts import render

from work.models import AgreementText


def legal_offer_view(request):
    """Public offer agreement and Privacy policy page."""
    agreement = AgreementText.objects.filter(role=AgreementText.TYPE_OFFER).first()
    return render(
        request,
        "work/legal_offer.html",
        {
            "agreement": agreement,
        },
    )
