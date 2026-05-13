from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import (
    AngajatFirma, Comanda, Firma, PlanificareZi, Produs,
    ServireGhiseu, ServireGhiseuLinie,
)


def _plan_componente(azi, tip_plan='pranz'):
    """Returns (meniu_optiuni list, tip_to_produse dict) for today's plan."""
    plan = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan)
        .select_related('produs')
    )
    f1     = next((r.produs for r in plan if r.produs.categorie == 'felul_1'), None)
    f2list = [r.produs for r in plan if r.produs.categorie == 'felul_2']
    f2v1   = f2list[0] if len(f2list) >= 1 else None
    f2v2   = f2list[1] if len(f2list) >= 2 else None
    sal    = next((r.produs for r in plan if r.produs.categorie == 'salate'), None)

    def _label(produse, fallback):
        names = [p.nume for p in produse if p]
        return ' + '.join(names) if names else fallback

    raw = [
        ({'key': 'v1',        'label': _label([f1, f2v1, sal], 'Meniu V1'),            'produse': [p for p in [f1, f2v1, sal] if p]} if f1 and f2v1 else None),
        ({'key': 'v2',        'label': _label([f1, f2v2, sal], 'Meniu V2'),            'produse': [p for p in [f1, f2v2, sal] if p]} if f1 and f2v2 else None),
        ({'key': 'solo_f1',   'label': _label([f1],            'Solo Felul 1'),        'produse': [p for p in [f1] if p]}            if f1          else None),
        ({'key': 'solo_f2v1', 'label': _label([f2v1, sal],     'Solo Felul 2 (v.1)'), 'produse': [p for p in [f2v1, sal] if p]}     if f2v1        else None),
        ({'key': 'solo_f2v2', 'label': _label([f2v2, sal],     'Solo Felul 2 (v.2)'), 'produse': [p for p in [f2v2, sal] if p]}     if f2v2        else None),
    ]
    optiuni = [o for o in raw if o and o['produse']]
    for o in optiuni:
        o['pret'] = float(sum(p.pret_standard or 0 for p in o['produse']))
    tip_to_produse = {o['key']: o['produse'] for o in optiuni}
    return optiuni, tip_to_produse


def _componente_pentru_meniu(tip_meniu, f1, f2v1, f2v2, sal):
    """Returnează lista de chei componente pentru un tip de meniu."""
    harta = {
        'v1':        [k for k, p in [('f1', f1), ('f2v1', f2v1), ('sal', sal)] if p],
        'v2':        [k for k, p in [('f1', f1), ('f2v2', f2v2), ('sal', sal)] if p],
        'solo_f1':   [k for k, p in [('f1', f1)] if p],
        'solo_f2v1': [k for k, p in [('f2v1', f2v1), ('sal', sal)] if p],
        'solo_f2v2': [k for k, p in [('f2v2', f2v2), ('sal', sal)] if p],
    }
    return harta.get(tip_meniu, [])


def _verifica_buffer(azi, tip_meniu, tip_ridicare, f1, f2v1, f2v2, sal, qty=1, tip_plan='pranz'):
    """Returnează True dacă există suficient disponibil în buffer."""
    with connection.cursor() as cur:
        if tip_ridicare == 'la_masa':
            comp_keys = _componente_pentru_meniu(tip_meniu, f1, f2v1, f2v2, sal)
            for comp in comp_keys:
                cur.execute("""
                    SELECT GREATEST(cantitate - distribuit, 0)
                    FROM buffer_componente
                    WHERE data_zi = %s AND componenta = %s AND tip_servire = 'masa' AND tip_plan = %s
                """, [azi, comp, tip_plan])
                row = cur.fetchone()
                if not row or row[0] < qty:
                    return False
        else:
            cur.execute("""
                SELECT GREATEST(cantitate - distribuit, 0)
                FROM buffer_componente
                WHERE data_zi = %s AND componenta = %s AND tip_servire = 'pachet' AND tip_plan = %s
            """, [azi, tip_meniu, tip_plan])
            row = cur.fetchone()
            if not row or row[0] < qty:
                return False
    return True


def _decrement_buffer(azi, tip_meniu, tip_ridicare, f1, f2v1, f2v2, sal, tip_plan='pranz'):
    """
    La masă  → decrementează componentele individuale (f1/f2v1/sal etc.)
    La pachet → decrementează meniul compus ambalat (v1/v2/solo_f1 etc.)
    """
    with connection.cursor() as cur:
        if tip_ridicare == 'la_masa':
            comp_keys = _componente_pentru_meniu(tip_meniu, f1, f2v1, f2v2, sal)
            for comp in comp_keys:
                cur.execute("""
                    UPDATE buffer_componente
                    SET distribuit = distribuit + 1
                    WHERE data_zi = %s AND componenta = %s AND tip_servire = 'masa'
                      AND tip_plan = %s AND distribuit < cantitate
                """, [azi, comp, tip_plan])
        else:
            cur.execute("""
                UPDATE buffer_componente
                SET distribuit = distribuit + 1
                WHERE data_zi = %s AND componenta = %s AND tip_servire = 'pachet'
                  AND tip_plan = %s AND distribuit < cantitate
            """, [azi, tip_meniu, tip_plan])


def _get_buffer(azi, plan_zi, tip_plan='pranz'):
    """Returnează buffer-ul zilei: componente masă + meniuri pachet, cu etichete reale."""
    f1     = next((r.produs for r in plan_zi if r.produs.categorie == 'felul_1'), None)
    f2list = [r.produs for r in plan_zi if r.produs.categorie == 'felul_2']
    f2v1   = f2list[0] if len(f2list) >= 1 else None
    f2v2   = f2list[1] if len(f2list) >= 2 else None
    sal    = next((r.produs for r in plan_zi if r.produs.categorie == 'salate'), None)

    def _lbl(produse, fallback):
        names = [p.nume for p in produse if p]
        return ' + '.join(names) if names else fallback

    # Componente individuale (masă)
    comp_def = [
        (k, lbl) for k, lbl, p in [
            ('f1',   f1.nume   if f1   else 'Felul 1',       f1),
            ('f2v1', f2v1.nume if f2v1 else 'Felul 2 (v.1)', f2v1),
            ('f2v2', f2v2.nume if f2v2 else 'Felul 2 (v.2)', f2v2),
            ('sal',  sal.nume  if sal  else 'Salată',         sal),
        ] if p
    ]

    # Meniuri compuse (pachet) — incluse doar când componenta definitorie există în plan
    meniu_def = [
        (k, lbl) for k, lbl, guard, produse in [
            ('v1',        _lbl([f1, f2v1, sal], 'Meniu V1'),            f1 and f2v1, [p for p in [f1, f2v1, sal] if p]),
            ('v2',        _lbl([f1, f2v2, sal], 'Meniu V2'),            f1 and f2v2, [p for p in [f1, f2v2, sal] if p]),
            ('solo_f1',   _lbl([f1],            'Solo Felul 1'),        f1,          [p for p in [f1] if p]),
            ('solo_f2v1', _lbl([f2v1, sal],     'Solo Felul 2 (v.1)'), f2v1,        [p for p in [f2v1, sal] if p]),
            ('solo_f2v2', _lbl([f2v2, sal],     'Solo Felul 2 (v.2)'), f2v2,        [p for p in [f2v2, sal] if p]),
        ] if guard and produse
    ]

    with connection.cursor() as cur:
        cur.execute("""
            SELECT componenta, tip_servire, cantitate, distribuit,
                   GREATEST(cantitate - distribuit, 0) AS disponibil
            FROM buffer_componente
            WHERE data_zi = %s AND tip_plan = %s
        """, [azi, tip_plan])
        cols = [c[0] for c in cur.description]
        rows = {(r[0], r[1]): dict(zip(cols, r)) for r in cur.fetchall()}

    buffer_masa = []
    for comp, lbl in comp_def:
        row = rows.get((comp, 'masa'), {'componenta': comp, 'tip_servire': 'masa', 'cantitate': 0, 'distribuit': 0, 'disponibil': 0})
        buffer_masa.append({**row, 'label': lbl})

    buffer_pachet = []
    for comp, lbl in meniu_def:
        row = rows.get((comp, 'pachet'), {'componenta': comp, 'tip_servire': 'pachet', 'cantitate': 0, 'distribuit': 0, 'disponibil': 0})
        buffer_pachet.append({**row, 'label': lbl})

    buffer = buffer_masa + buffer_pachet
    return buffer, buffer_masa, buffer_pachet, f1, f2v1, f2v2, sal


@login_required
def index(request):
    azi = timezone.localdate()

    if request.GET.get('set_tip_plan') in ('pranz', 'cina'):
        request.session['tip_plan'] = request.GET['set_tip_plan']
    tip_plan = request.session.get('tip_plan', 'pranz')

    meniu_optiuni, _ = _plan_componente(azi, tip_plan)
    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan)
        .select_related('produs')
    )
    buffer, buffer_masa, buffer_pachet, _, _, _, _ = _get_buffer(azi, plan_zi, tip_plan)

    # ── Firme ──────────────────────────────────────────────────
    firme_qs = list(
        Firma.objects
        .filter(activ=True, tip_firma__in=['ghiseu', 'ghiseu_livrare'])
        .order_by('nume_firma')
    )
    angajati_qs = list(
        AngajatFirma.objects
        .filter(firma__in=firme_qs)
        .order_by('nume_angajat')
    )
    serviri_firme = list(
        ServireGhiseu.objects
        .filter(data_servire=azi, tip_servire='firma')
        .prefetch_related('linii')
        .order_by('id')
    )
    servire_map = {s.angajat_id: s for s in serviri_firme if s.angajat_id}

    firme_data = []
    for firma in firme_qs:
        ang_firma    = [a for a in angajati_qs if a.firma_id == firma.pk]
        ang_activi   = [a for a in ang_firma if a.activ]
        ang_inactivi = [a for a in ang_firma if not a.activ]

        angajati_data = []
        for a in ang_activi:
            servire = servire_map.get(a.pk)
            produse_str = ''
            if servire:
                linii = list(servire.linii.all())
                produse_str = ', '.join(l.nume_produs for l in linii)
            angajati_data.append({
                'angajat':     a,
                'servire':     servire,
                'produse_str': produse_str,
            })

        firme_data.append({
            'firma':        firma,
            'angajati':     angajati_data,
            'ang_inactivi': ang_inactivi,
            'nr_serviti':   sum(1 for d in angajati_data if d['servire']),
            'nr_total':     len(ang_activi),
        })

    # ── Comenzi speciale ghișeu ────────────────────────────────
    produse_speciale = list(Produs.objects.filter(categorie='special').order_by('nume'))
    comenzi_speciale_noi = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=998, status='nou')
        .prefetch_related('linii')
        .order_by('created_at', 'id')
    )
    comenzi_speciale_gata = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=998, status='pregatit')
        .prefetch_related('linii')
        .order_by('pregatit_la', 'id')
    )
    comenzi_speciale_livrate = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=998, status='livrat')
        .prefetch_related('linii')
        .order_by('-livrat_la')
    )

    # ── Loturi eveniment pregătite (gata de distribuit) ────────
    loturi_ev = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=999, tip_comanda__in=['eveniment', 'special'],
                status='pregatit')
        .prefetch_related('linii')
        .order_by('ora_livrare_estimata', 'id')
    )

    # ── Bon casă ───────────────────────────────────────────────
    serviri_bon = list(
        ServireGhiseu.objects
        .filter(data_servire=azi, tip_servire='bon_casa')
        .prefetch_related('linii')
        .order_by('-id')[:30]
    )
    # Total per bon (join cu prețuri produse)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT sg.id, COALESCE(SUM(p.pret_standard * sgl.cantitate), 0)
            FROM serviri_ghiseu sg
            JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
            JOIN produse p ON p.nume = sgl.nume_produs
            WHERE sg.data_servire = %s AND sg.tip_servire = 'bon_casa'
            GROUP BY sg.id
        """, [azi])
        total_per_bon = {r[0]: r[1] for r in cur.fetchall()}
    for s in serviri_bon:
        s.total_calculat = total_per_bon.get(s.pk, 0)

    # ── Raport / statistici ────────────────────────────────────
    serviri_azi = list(
        ServireGhiseu.objects
        .filter(data_servire=azi)
        .select_related('firma', 'angajat')
        .prefetch_related('linii')
        .order_by('-id')
    )
    loturi_ev_distribuite = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=999,
                tip_comanda__in=['eveniment', 'special'], status='livrat')
        .prefetch_related('linii')
        .order_by('livrat_la')
    )
    total_ev_distribuite = sum(
        (lot.total_plata or 0) for lot in loturi_ev_distribuite
    )

    # Rezumat produse servite — pentru raport operativ
    from collections import defaultdict
    _bon_prod   = defaultdict(int)
    _firme_prod = defaultdict(int)
    for s in serviri_azi:
        target = _bon_prod if s.tip_servire == 'bon_casa' else _firme_prod
        for l in s.linii.all():
            target[l.nume_produs] += l.cantitate

    rezumat_bon   = sorted(_bon_prod.items())
    rezumat_firme = sorted(_firme_prod.items())

    # Total bon casă (join cu produse pentru preț)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(p.pret_standard * sgl.cantitate), 0)
            FROM serviri_ghiseu sg
            JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
            JOIN produse p ON p.nume = sgl.nume_produs
            WHERE sg.data_servire = %s AND sg.tip_servire = 'bon_casa'
        """, [azi])
        total_bon = cur.fetchone()[0] or 0

    _special_prod = defaultdict(int)
    for cmd in comenzi_speciale_livrate:
        for l in cmd.linii.all():
            _special_prod[l.nume_produs] += l.cantitate
    rezumat_speciale  = sorted(_special_prod.items())
    total_speciale    = sum((cmd.total_plata or 0) for cmd in comenzi_speciale_livrate)

    nr_total_angajati  = sum(fd['nr_total']   for fd in firme_data)
    nr_serviti_angajati = sum(fd['nr_serviti'] for fd in firme_data)

    stats = {
        'bon':        sum(1 for s in serviri_azi if s.tip_servire == 'bon_casa'),
        'evenimente': len(loturi_ev_distribuite),
    }

    return render(request, 'ghiseu/index.html', {
        'azi':           azi,
        'firme_data':    firme_data,
        'loturi_ev':     loturi_ev,
        'meniu_optiuni': meniu_optiuni,
        'buffer':        buffer,
        'buffer_masa':   buffer_masa,
        'buffer_pachet': buffer_pachet,
        'tip_plan':      tip_plan,
        'serviri_bon':            serviri_bon,
        'serviri_azi':            serviri_azi,
        'loturi_ev_distribuite':    loturi_ev_distribuite,
        'total_ev_distribuite':     total_ev_distribuite,
        'rezumat_bon':              rezumat_bon,
        'total_bon':                total_bon,
        'rezumat_firme':            rezumat_firme,
        'rezumat_speciale':         rezumat_speciale,
        'total_speciale':           total_speciale,
        'nr_total_angajati':        nr_total_angajati,
        'nr_serviti_angajati':      nr_serviti_angajati,
        'stats':                  stats,
        'produse_speciale':          produse_speciale,
        'comenzi_speciale_noi':      comenzi_speciale_noi,
        'comenzi_speciale_gata':     comenzi_speciale_gata,
        'comenzi_speciale_livrate':  comenzi_speciale_livrate,
    })


@login_required
@require_POST
def servire_add(request):
    """Servire angajat firmă — direct din buffer."""
    azi = timezone.localdate()
    try:
        firma_id   = int(request.POST.get('firma_id', 0))
        angajat_id = int(request.POST.get('angajat_id', 0))
    except (ValueError, TypeError):
        return redirect('/staff/ghiseu/?tab=firme')

    firma   = get_object_or_404(Firma, pk=firma_id)
    angajat = get_object_or_404(AngajatFirma, pk=angajat_id)

    tip_meniu    = request.POST.get('tip_meniu', 'v1')
    tip_ridicare = request.POST.get('tip_ridicare', 'la_masa')
    tip_plan     = request.session.get('tip_plan', 'pranz')

    _, tip_to_produse = _plan_componente(azi, tip_plan)
    produse = tip_to_produse.get(tip_meniu, [])

    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan).select_related('produs')
    )
    _, _, _, f1, f2v1, f2v2, sal = _get_buffer(azi, plan_zi, tip_plan)

    if not _verifica_buffer(azi, tip_meniu, tip_ridicare, f1, f2v1, f2v2, sal, tip_plan=tip_plan):
        messages.error(request, 'Buffer insuficient — nu mai sunt porții disponibile.')
        return redirect('/staff/ghiseu/?tab=firme')

    _decrement_buffer(azi, tip_meniu, tip_ridicare, f1, f2v1, f2v2, sal, tip_plan=tip_plan)

    servire = ServireGhiseu.objects.create(
        data_servire=azi,
        ora_servire=timezone.localtime().time(),
        tip_servire='firma',
        firma=firma,
        angajat=angajat,
        tip_ridicare=tip_ridicare,
        din_buffer=True,
    )
    for p in produse:
        ServireGhiseuLinie.objects.create(
            servire=servire,
            nume_produs=p.nume,
            cantitate=1,
        )

    return redirect('/staff/ghiseu/?tab=firme')


@login_required
@require_POST
def bon_add(request):
    """Servire bon casă — coș cu mai multe meniuri și cantități."""
    from collections import defaultdict
    azi = timezone.localdate()
    tip_ridicare = request.POST.get('tip_ridicare', 'la_masa')
    tip_plan     = request.session.get('tip_plan', 'pranz')

    optiuni, tip_to_produse = _plan_componente(azi, tip_plan)
    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan).select_related('produs')
    )
    _, _, _, f1, f2v1, f2v2, sal = _get_buffer(azi, plan_zi, tip_plan)

    # Parsăm coșul: qty_v1=2, qty_solo_f1=1 etc.
    cart = []
    for opt in optiuni:
        try:
            qty = int(request.POST.get(f'qty_{opt["key"]}', 0))
        except (ValueError, TypeError):
            qty = 0
        if qty > 0:
            cart.append({'tip_meniu': opt['key'], 'produse': opt['produse'], 'qty': qty})

    if not cart:
        messages.error(request, 'Coșul este gol.')
        return redirect('/staff/ghiseu/?tab=bon')

    # Verificăm disponibilul pentru fiecare item din coș
    for item in cart:
        if not _verifica_buffer(azi, item['tip_meniu'], tip_ridicare, f1, f2v1, f2v2, sal, qty=item['qty'], tip_plan=tip_plan):
            messages.error(request, f'Buffer insuficient pentru „{item["tip_meniu"]}" — nu sunt suficiente porții disponibile.')
            return redirect('/staff/ghiseu/?tab=bon')

    # Decrementăm buffer-ul pentru fiecare unitate din coș
    for item in cart:
        for _ in range(item['qty']):
            _decrement_buffer(azi, item['tip_meniu'], tip_ridicare, f1, f2v1, f2v2, sal, tip_plan=tip_plan)

    # Agregăm produsele din toate meniurile
    produse_count = defaultdict(int)
    for item in cart:
        for p in item['produse']:
            produse_count[p.nume] += item['qty']

    servire = ServireGhiseu.objects.create(
        data_servire=azi,
        ora_servire=timezone.localtime().time(),
        tip_servire='bon_casa',
        tip_ridicare=tip_ridicare,
        din_buffer=True,
    )
    for nume_produs, cantitate in produse_count.items():
        ServireGhiseuLinie.objects.create(
            servire=servire,
            nume_produs=nume_produs,
            cantitate=cantitate,
        )

    return redirect('/staff/ghiseu/?tab=bon')


@login_required
@require_POST
def angajat_add(request):
    try:
        firma_id = int(request.POST.get('firma_id', 0))
    except (ValueError, TypeError):
        return redirect('/staff/ghiseu/?tab=firme')
    firma = get_object_or_404(Firma, pk=firma_id)
    nume = request.POST.get('nume_angajat', '').strip()
    if nume:
        AngajatFirma.objects.create(firma=firma, nume_angajat=nume, activ=True)
    return redirect('/staff/ghiseu/?tab=firme')


@login_required
@require_POST
def angajat_toggle(request, pk):
    angajat = get_object_or_404(AngajatFirma, pk=pk)
    angajat.activ = not angajat.activ
    angajat.save(update_fields=['activ'])
    return redirect('/staff/ghiseu/?tab=firme')


@login_required
@require_POST
def special_comanda_add(request):
    """Ghișeul creează o comandă specială → bucătărie."""
    azi = timezone.localdate()
    tip_ridicare = request.POST.get('tip_ridicare', 'la_masa')

    items = []
    for key, val in request.POST.items():
        if not key.startswith('qty_'):
            continue
        try:
            pid = int(key[4:])
            qty = int(val)
            if qty > 0:
                produs = Produs.objects.get(pk=pid, categorie='special')
                items.append({'produs': produs, 'qty': qty})
        except (ValueError, TypeError, Produs.DoesNotExist):
            pass

    if not items:
        messages.error(request, 'Selectați cel puțin un produs cu cantitate > 0.')
        return redirect('/staff/ghiseu/?tab=special')

    total = sum(float(item['produs'].pret_standard or 0) * item['qty'] for item in items)
    ridicare_label = 'la masă' if tip_ridicare == 'la_masa' else 'la pachet'

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO comenzi
                (client_id, data_comanda, ora_livrare_estimata, status,
                 total_plata, tip_comanda, tip_ridicare, observatii, created_at)
            VALUES (998, %s, NOW()::time, 'nou', %s, 'special', %s, %s, NOW())
            RETURNING id
        """, [azi, total, tip_ridicare, f'Comandă ghișeu — {ridicare_label}'])
        comanda_id = cur.fetchone()[0]

        for item in items:
            cur.execute("""
                INSERT INTO comenzi_linii
                    (comanda_id, nume_produs, cantitate, pret_unitar, tip_linie, status)
                VALUES (%s, %s, %s, %s, 'special', 'nou')
            """, [comanda_id, item['produs'].nume, item['qty'],
                  float(item['produs'].pret_standard or 0)])

    messages.success(request, f'Comandă specială #{comanda_id} trimisă la bucătărie.')
    return redirect('/staff/ghiseu/?tab=special')


@login_required
@require_POST
def special_livrat(request, pk):
    """Marchează o comandă specială ca livrată/servită de ghișeu."""
    comanda = get_object_or_404(Comanda, pk=pk, client_id=998)
    if comanda.status == 'pregatit':
        now = timezone.now()
        comanda.status = 'livrat'
        if not comanda.livrat_la:
            comanda.livrat_la = now
        comanda.save(update_fields=['status', 'livrat_la'])
        messages.success(request, f'Comanda #{pk} servită.')
    return redirect('/staff/ghiseu/?tab=special')


@login_required
@require_POST
def eveniment_distribuit(request, pk):
    """Marchează un lot eveniment ca distribuit (la masă)."""
    comanda = get_object_or_404(Comanda, pk=pk, client_id=999)
    if comanda.status not in ('anulat',):
        now = timezone.now()
        comanda.status = 'livrat'
        if not comanda.livrat_la:
            comanda.livrat_la = now
        comanda.save(update_fields=['status', 'livrat_la'])
        messages.success(request, f'Lotul #{pk} a fost marcat distribuit.')
    return redirect('/staff/ghiseu/?tab=firme')
