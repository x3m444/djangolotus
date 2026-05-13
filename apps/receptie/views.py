from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import Client, Comanda, ComandaLinie, Livrator, PlanificareZi, Produs

CATEGORII_LABELS = {
    'felul_1':  'Felul 1',
    'felul_2':  'Felul 2',
    'salate':   'Salată',
    'desert':   'Desert',
    'sandwich': 'Sandwich',
    'special':  'Special',
}
CATEGORII_ORDINE = ['felul_1', 'felul_2', 'salate', 'desert', 'sandwich', 'special']


@login_required
def index(request):
    azi = timezone.localdate()
    status_filter = request.GET.get('status', '')

    qs = (
        Comanda.objects
        .exclude(client_id=999)
        .filter(data_comanda=azi)
        .select_related('client')
        .prefetch_related('linii')
        .order_by('-id')
    )
    if status_filter:
        qs = qs.filter(status=status_filter)

    comenzi = list(qs)
    sumar = Comanda.objects.exclude(client_id=999).filter(data_comanda=azi).aggregate(
        total=Count('id'),
        noi=Count('id', filter=Q(status='nou')),
        livrate=Count('id', filter=Q(status='livrat')),
        anulate=Count('id', filter=Q(status='anulat')),
    )

    plan_pranz = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan='pranz')
        .select_related('produs').order_by('produs__categorie')
    )
    livratori = list(Livrator.objects.filter(activ=True).order_by('nume'))
    clienti   = list(Client.objects.exclude(pk=999).order_by('nume_client'))

    return render(request, 'receptie/index.html', {
        'azi':            azi,
        'comenzi':        comenzi,
        'sumar':          sumar,
        'status_filter':  status_filter,
        'plan_pranz':     plan_pranz,
        'livratori':      livratori,
        'clienti':        clienti,
        'STATUS_CHOICES': Comanda.STATUS_CHOICES,
        'TIP_CHOICES':    Comanda.TIP_CHOICES,
        'PLATA_CHOICES':  Comanda.PLATA_CHOICES,
    })


@login_required
def comanda_detail(request, pk):
    comanda = get_object_or_404(
        Comanda.objects.select_related('client').prefetch_related('linii'), pk=pk
    )
    return render(request, 'receptie/comanda_detail.html', {'comanda': comanda})


@login_required
def comanda_nou(request):
    azi       = timezone.localdate()
    clienti   = list(Client.objects.exclude(pk=999).order_by('nume_client'))
    livratori = list(Livrator.objects.filter(activ=True).order_by('nume'))

    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan='pranz')
        .select_related('produs').order_by('produs__categorie')
    )

    nomenclator = cache.get('nomenclator_produse')
    if nomenclator is None:
        nomenclator = list(Produs.objects.prefetch_related('reteta').order_by('categorie', 'nume'))
        cache.set('nomenclator_produse', nomenclator, 300)

    plan_pe_cat = defaultdict(list)
    for pz in plan_zi:
        plan_pe_cat[pz.produs.categorie].append(pz.produs)

    f1_plan  = plan_pe_cat.get('felul_1', [])
    f2_plan  = plan_pe_cat.get('felul_2', [])
    sal_plan = plan_pe_cat.get('salate',  [])

    speciale  = [p for p in nomenclator if p.categorie == 'special']
    toate_f1  = [p for p in nomenclator if p.categorie == 'felul_1']
    toate_f2  = [p for p in nomenclator if p.categorie == 'felul_2']
    toate_sal = [p for p in nomenclator if p.categorie == 'salate']

    toate_pe_cat = defaultdict(list)
    for p in nomenclator:
        toate_pe_cat[p.categorie].append(p)
    categorii_toate = [
        (cod, CATEGORII_LABELS.get(cod, cod), toate_pe_cat[cod])
        for cod in CATEGORII_ORDINE if toate_pe_cat[cod]
    ]
    for cod, produse in toate_pe_cat.items():
        if cod not in CATEGORII_ORDINE:
            categorii_toate.append((cod, cod.replace('_', ' ').title(), produse))

    ORA_CHOICES = [
        ('09:00', '09:00 – 09:30'),
        ('09:30', '09:30 – 10:00'),
        ('10:00', '10:00 – 10:30'),
        ('10:30', '10:30 – 11:00'),
        ('11:00', '11:00 – 11:30'),
        ('11:30', '11:30 – 12:00'),
        ('12:00', '12:00 – 12:30'),
        ('12:30', '12:30 – 13:00'),
        ('13:00', '13:00 – 13:30'),
        ('13:30', '13:30 – 14:00'),
        ('08:00', '⚡ URGENT'),
    ]

    return render(request, 'receptie/comanda_nou.html', {
        'azi':             azi,
        'clienti':         clienti,
        'livratori':       livratori,
        'f1_plan':         f1_plan,
        'f2_plan':         f2_plan,
        'sal_plan':        sal_plan,
        'speciale':        speciale,
        'categorii_toate': categorii_toate,
        'ORA_CHOICES':     ORA_CHOICES,
        'PLATA_CHOICES':   Comanda.PLATA_CHOICES,
    })


@login_required
@require_POST
def comanda_add(request):
    azi = timezone.localdate()
    try:
        data_raw = request.POST.get('data_comanda', '').strip()
        data_comanda = date_cls.fromisoformat(data_raw) if data_raw else azi
    except ValueError:
        data_comanda = azi

    # ── Client ──────────────────────────────────────────────────
    client_id = request.POST.get('client_id', '').strip()
    if client_id:
        client = get_object_or_404(Client, pk=client_id)
    else:
        telefon = request.POST.get('client_telefon', '').strip()
        if not telefon:
            messages.error(request, 'Selectați un client sau introduceți telefonul.')
            return redirect('receptie:index')
        client = Client.objects.filter(telefon=telefon).first()
        if client is None:
            nume = request.POST.get('client_nume', '').strip() or telefon
            try:
                client = Client.objects.create(nume_client=nume, telefon=telefon)
            except IntegrityError:
                client = Client.objects.create(nume_client=f'{nume} ({telefon})', telefon=telefon)

    # ── Coș din qty_{pk} ────────────────────────────────────────
    qty_map = {}
    for key, val in request.POST.items():
        if key.startswith('qty_'):
            try:
                pk  = int(key[4:])
                qty = int(val)
                if qty > 0:
                    qty_map[pk] = qty
            except (ValueError, TypeError):
                pass

    if not qty_map:
        messages.error(request, 'Coșul este gol. Adaugă cel puțin un produs.')
        return redirect('receptie:comanda_nou')

    produse_map = {p.pk: p for p in Produs.objects.filter(pk__in=qty_map.keys())}

    linii  = []
    total  = Decimal('0')
    for pk, qty in qty_map.items():
        produs = produse_map.get(pk)
        if not produs:
            continue
        pret = produs.pret_standard or Decimal('0')
        tip  = 'special' if produs.categorie == 'special' else 'standard'
        total += pret * qty
        linii.append({'produs': produs, 'qty': qty, 'pret': pret, 'tip': tip})

    if not linii:
        messages.error(request, 'Coșul este gol. Adaugă cel puțin un produs.')
        return redirect('receptie:comanda_nou')

    # ── Params opționali ─────────────────────────────────────────
    tip_comanda  = 'livrare'
    metoda_plata = request.POST.get('metoda_plata') or None
    ora_raw      = request.POST.get('ora_livrare', '').strip()
    ora_livrare  = ora_raw if ora_raw else '12:00'
    sofer = request.POST.get('sofer', '').strip()
    if not sofer:
        messages.error(request, 'Selectați un livrator pentru această comandă.')
        return redirect('receptie:comanda_nou')
    observatii = request.POST.get('observatii', '').strip() or None

    # ── Salvare ──────────────────────────────────────────────────
    with transaction.atomic():
        comanda = Comanda.objects.create(
            client=client,
            data_comanda=data_comanda,
            tip_comanda=tip_comanda,
            metoda_plata=metoda_plata,
            ora_livrare_estimata=ora_livrare,
            total_plata=total if total else None,
            sofer=sofer,
            observatii=observatii,
            status='nou',
        )
        for linie in linii:
            ComandaLinie.objects.create(
                comanda=comanda,
                nume_produs=linie['produs'].nume,
                cantitate=linie['qty'],
                pret_unitar=linie['pret'] or None,
                tip_linie=linie['tip'],
            )

    messages.success(request, f'Comanda #{comanda.pk} pentru {client.nume_client} a fost înregistrată.')
    return redirect('receptie:comanda_detail', pk=comanda.pk)


@login_required
@require_POST
def comanda_status(request, pk):
    comanda = get_object_or_404(Comanda, pk=pk)
    nou_status = request.POST.get('status', '').strip()

    statuse_valide = [s[0] for s in Comanda.STATUS_CHOICES]
    if nou_status not in statuse_valide:
        messages.error(request, 'Status invalid.')
        return redirect('receptie:comanda_detail', pk=pk)

    now = timezone.now()
    update_fields = ['status']
    comanda.status = nou_status

    if nou_status == 'pregatit' and not comanda.pregatit_la:
        comanda.pregatit_la = now
        update_fields.append('pregatit_la')
    elif nou_status == 'pedrum' and not comanda.pedrum_la:
        comanda.pedrum_la = now
        update_fields.append('pedrum_la')
    elif nou_status == 'livrat' and not comanda.livrat_la:
        comanda.livrat_la = now
        update_fields.append('livrat_la')

    comanda.save(update_fields=update_fields)
    messages.success(request, f'Comanda #{pk} → {comanda.get_status_display()}.')
    return redirect('receptie:comanda_detail', pk=pk)


@login_required
@require_POST
def comanda_anuleaza(request, pk):
    comanda = get_object_or_404(Comanda, pk=pk)
    if comanda.status == 'livrat':
        messages.error(request, 'Nu se poate anula o comandă deja livrată.')
        return redirect('receptie:comanda_detail', pk=pk)
    comanda.status = 'anulat'
    comanda.save(update_fields=['status'])
    messages.warning(request, f'Comanda #{pk} a fost anulată.')
    return redirect('receptie:index')


@login_required
def clienti_cauta(request):
    q = request.GET.get('q', '').strip()
    if q:
        clienti = list(
            Client.objects
            .filter(Q(telefon__icontains=q) | Q(nume_client__icontains=q))
            .distinct().order_by('nume_client')
        )
    else:
        clienti = list(
            Client.objects.exclude(pk=999).order_by('nume_client')
        )
    return render(request, 'receptie/clienti_cauta.html', {'clienti': clienti, 'q': q})


@login_required
@require_POST
def client_add(request):
    telefon = request.POST.get('telefon', '').strip()
    nume    = request.POST.get('nume', '').strip()
    adresa  = request.POST.get('adresa', '').strip() or None

    if not telefon or not nume:
        messages.error(request, 'Numele și telefonul sunt obligatorii.')
        return redirect('receptie:clienti_cauta')

    if Client.objects.filter(telefon=telefon).exists():
        messages.warning(request, f'Clientul cu telefonul {telefon} există deja.')
        return redirect('receptie:clienti_cauta')

    Client.objects.create(nume_client=nume, telefon=telefon, adresa_principala=adresa)
    messages.success(request, f'Client „{nume}" adăugat.')
    return redirect('receptie:clienti_cauta')
