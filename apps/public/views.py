from django.shortcuts import render
from django.utils import timezone
from apps.core.models import Produs, PlanificareZi


def landing(request):
    azi = timezone.localdate()

    plan_pranz = (
        PlanificareZi.objects
        .filter(data_zi=azi, tip_plan='pranz')
        .select_related('produs')
        .order_by('produs__categorie')
    )

    meniu = [p.produs for p in plan_pranz]

    speciale = Produs.objects.filter(categorie='special').order_by('nume')

    return render(request, 'public/landing.html', {
        'azi': azi,
        'meniu': meniu,
        'speciale': speciale,
    })
