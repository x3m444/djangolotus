import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

import xlsxwriter

from apps.core.models import Comanda, ComandaLinie, Ingredient, NecesarZi, PlanificareZi


@login_required
def index(request):
    azi = timezone.localdate()

    # Produse din planul zilei (prânz + cină) — gătite în bulk din lot, nu individual
    produse_plan_azi = set(
        PlanificareZi.objects
        .filter(data_zi=azi, tip_plan__in=['pranz', 'cina'])
        .values_list('produs__nume', flat=True)
    )

    # Gătire: loturi lansate (client_id=999) + orice comandă individuală cu produse
    # care NU sunt în planul zilei (sandwich, special, orice din tab "Toate")
    produse_lot = list(
        ComandaLinie.objects
        .filter(comanda__data_comanda=azi)
        .exclude(comanda__status='anulat')
        .filter(
            Q(comanda__client_id=999) |
            ~Q(nume_produs__in=produse_plan_azi)
        )
        .values('nume_produs')
        .annotate(
            total=Sum('cantitate'),
            gatit=Sum('cantitate', filter=Q(status='gatit')),
        )
        .order_by('nume_produs')
    )
    # Calculăm nou = total - gatit
    for p in produse_lot:
        p['gatit'] = p['gatit'] or 0
        p['nou'] = p['total'] - p['gatit']
        p['toate_gata'] = (p['nou'] == 0)

    # Comenzi recepție de ambalat (status nou, toate liniile gatit = gata de ambalat)
    comenzi_ambalare = list(
        Comanda.objects
        .exclude(client_id=999)
        .filter(data_comanda=azi, status='nou')
        .select_related('client')
        .prefetch_related('linii')
        .order_by('ora_livrare_estimata', 'id')
    )
    for cmd in comenzi_ambalare:
        linii = list(cmd.linii.all())
        cmd.nr_total = len(linii)
        cmd.nr_gatite = sum(1 for l in linii if l.status == 'gatit')
        cmd.toate_gata = (cmd.nr_total > 0 and cmd.nr_total == cmd.nr_gatite)

    # Loturi eveniment de ambalat/pregătit
    loturi_ev_ambalare = list(
        Comanda.objects
        .filter(data_comanda=azi, client_id=999, tip_comanda__in=['eveniment', 'special'])
        .exclude(status__in=['anulat', 'livrat'])
        .prefetch_related('linii')
        .order_by('ora_livrare_estimata', 'id')
    )
    for lot in loturi_ev_ambalare:
        linii = list(lot.linii.all())
        lot.nr_total = len(linii)
        lot.nr_gatite = sum(1 for l in linii if l.status == 'gatit')
        lot.toate_gata = (lot.nr_total > 0 and lot.nr_total == lot.nr_gatite)

    # Pachete firme de ambalat (ServireGhiseu cu status_pachet='astept')
    with connection.cursor() as cur:
        cur.execute("""
            SELECT sg.id, f.nume_firma, ag.nume_angajat,
                   STRING_AGG(sgl.nume_produs, ', ' ORDER BY sgl.id) AS produse,
                   sg.status_pachet
            FROM serviri_ghiseu sg
            JOIN firme f ON f.id = sg.firma_id
            LEFT JOIN angajati_firme ag ON ag.id = sg.angajat_id
            JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
            WHERE sg.data_servire = %s AND sg.tip_servire = 'firma'
              AND sg.status_pachet IN ('astept', 'ambalat')
            GROUP BY sg.id, f.nume_firma, ag.nume_angajat, sg.status_pachet
            ORDER BY f.nume_firma, ag.nume_angajat
        """, [azi])
        cols = [c[0] for c in cur.description]
        pachete_firme = [dict(zip(cols, r)) for r in cur.fetchall()]

    # Buffer componente
    if request.GET.get('set_tip_plan') in ('pranz', 'cina'):
        request.session['tip_plan'] = request.GET['set_tip_plan']
    tip_plan = request.session.get('tip_plan', 'pranz')

    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan)
        .select_related('produs')
    )
    f1     = next((r.produs for r in plan_zi if r.produs.categorie == 'felul_1'), None)
    f2list = [r.produs for r in plan_zi if r.produs.categorie == 'felul_2']
    f2v1   = f2list[0] if len(f2list) >= 1 else None
    f2v2   = f2list[1] if len(f2list) >= 2 else None
    sal    = next((r.produs for r in plan_zi if r.produs.categorie == 'salate'), None)

    def _lbl(produse, fallback):
        names = [p.nume for p in produse if p]
        return ' + '.join(names) if names else fallback

    # Componente individuale (pentru servire la masă)
    componente_def = [
        {'key': 'f1',   'label': f1.nume   if f1   else 'Felul 1',       'produs': f1},
        {'key': 'f2v1', 'label': f2v1.nume if f2v1 else 'Felul 2 (v.1)', 'produs': f2v1},
        {'key': 'f2v2', 'label': f2v2.nume if f2v2 else 'Felul 2 (v.2)', 'produs': f2v2},
        {'key': 'sal',  'label': sal.nume  if sal  else 'Salată',         'produs': sal},
    ]
    componente_def = [c for c in componente_def if c['produs']]

    # Meniuri compuse (pentru ambalare la pachet)
    # Un meniu este valid doar dacă componenta sa definitorie (felul_2 variant) există în plan
    _raw_meniuri = [
        ({'key': 'v1',        'label': _lbl([f1, f2v1, sal], 'Meniu V1'),            'produse': [p for p in [f1, f2v1, sal] if p]} if f1 and f2v1 else None),
        ({'key': 'v2',        'label': _lbl([f1, f2v2, sal], 'Meniu V2'),            'produse': [p for p in [f1, f2v2, sal] if p]} if f1 and f2v2 else None),
        ({'key': 'solo_f1',   'label': _lbl([f1],            'Solo Felul 1'),        'produse': [p for p in [f1] if p]}            if f1          else None),
        ({'key': 'solo_f2v1', 'label': _lbl([f2v1, sal],     'Solo Felul 2 (v.1)'), 'produse': [p for p in [f2v1, sal] if p]}     if f2v1        else None),
        ({'key': 'solo_f2v2', 'label': _lbl([f2v2, sal],     'Solo Felul 2 (v.2)'), 'produse': [p for p in [f2v2, sal] if p]}     if f2v2        else None),
    ]
    meniuri_def = [m for m in _raw_meniuri if m and m['produse']]

    with connection.cursor() as cur:
        cur.execute("""
            SELECT componenta, tip_servire, cantitate, distribuit,
                   GREATEST(cantitate - distribuit, 0) AS disponibil
            FROM buffer_componente
            WHERE data_zi = %s AND tip_plan = %s
        """, [azi, tip_plan])
        cols = [c[0] for c in cur.description]
        buf_rows = {(r[0], r[1]): dict(zip(cols, r)) for r in cur.fetchall()}

    # Cantitate gătită per produs azi
    with connection.cursor() as cur:
        cur.execute("""
            SELECT cl.nume_produs, SUM(cl.cantitate)
            FROM comenzi_linii cl
            JOIN comenzi c ON c.id = cl.comanda_id
            WHERE c.data_comanda = %s AND cl.status = 'gatit'
              AND c.status != 'anulat'
            GROUP BY cl.nume_produs
        """, [azi])
        gatit_map = {r[0]: r[1] for r in cur.fetchall()}

    # Reverse mapping: produs.nume → toate (componenta, tip_servire) care îl conțin
    reverse_map = {}
    for comp in componente_def:
        if comp.get('produs'):
            reverse_map.setdefault(comp['produs'].nume, []).append((comp['key'], 'masa'))
    for meniu in meniuri_def:
        for p in meniu.get('produse', []):
            reverse_map.setdefault(p.nume, []).append((meniu['key'], 'pachet'))

    # Total alocat în buffer per produs (cross-component)
    total_buffer_per_produs = {
        pname: sum(buf_rows.get((comp, tip), {}).get('cantitate', 0) for comp, tip in comps)
        for pname, comps in reverse_map.items()
    }

    # Pot adăuga real per produs = gătit - total deja în TOATE bufferele
    real_disp = {
        pname: max(gatit_map.get(pname, 0) - total_buffer_per_produs.get(pname, 0), 0)
        for pname in reverse_map
    }

    # Buffer masă — componente individuale
    buffer_masa = []
    for comp in componente_def:
        row = buf_rows.get((comp['key'], 'masa'), {
            'componenta': comp['key'], 'tip_servire': 'masa',
            'cantitate': 0, 'distribuit': 0, 'disponibil': 0,
        })
        gatit = gatit_map.get(comp['produs'].nume, 0) if comp.get('produs') else 0
        pot_adauga = real_disp.get(comp['produs'].nume, 0) if comp.get('produs') else 0
        buffer_masa.append({**row, 'label': comp['label'], 'gatit': gatit, 'pot_adauga': pot_adauga})

    # Buffer pachet — meniuri compuse ambalate
    buffer_pachet = []
    for meniu in meniuri_def:
        row = buf_rows.get((meniu['key'], 'pachet'), {
            'componenta': meniu['key'], 'tip_servire': 'pachet',
            'cantitate': 0, 'distribuit': 0, 'disponibil': 0,
        })
        produse = meniu.get('produse', [])
        gatit = min((gatit_map.get(p.nume, 0) for p in produse), default=0) if produse else 0
        pot_adauga = min((real_disp.get(p.nume, 0) for p in produse), default=0) if produse else 0
        buffer_pachet.append({**row, 'label': meniu['label'], 'gatit': gatit, 'pot_adauga': pot_adauga})

    # Lista unificată pentru cardul informativ din ghișeu
    buffer = buffer_masa + buffer_pachet

    # ── Stoc nevândut — calcul automat per produs ──────────────
    # Baza: doar produsele care au fost efectiv gătite azi
    with connection.cursor() as cur:
        # Gătit azi (per produs, toate sursele)
        cur.execute("""
            SELECT cl.nume_produs, SUM(cl.cantitate) AS gatit
            FROM comenzi_linii cl
            JOIN comenzi c ON c.id = cl.comanda_id
            WHERE c.data_comanda = %s AND cl.status = 'gatit'
              AND c.status != 'anulat'
            GROUP BY cl.nume_produs
        """, [azi])
        gatit_map = {r[0]: r[1] for r in cur.fetchall()}

        # Servit la ghișeu azi (per produs)
        cur.execute("""
            SELECT sgl.nume_produs, SUM(sgl.cantitate)
            FROM serviri_ghiseu_linii sgl
            JOIN serviri_ghiseu sg ON sg.id = sgl.servire_id
            WHERE sg.data_servire = %s
            GROUP BY sgl.nume_produs
        """, [azi])
        servit_map = {r[0]: r[1] for r in cur.fetchall()}

        # Livrat azi (per produs, comenzi cu status livrat)
        cur.execute("""
            SELECT cl.nume_produs, SUM(cl.cantitate)
            FROM comenzi_linii cl
            JOIN comenzi c ON c.id = cl.comanda_id
            WHERE c.data_comanda = %s AND c.status = 'livrat'
              AND c.client_id != 999
            GROUP BY cl.nume_produs
        """, [azi])
        livrat_map = {r[0]: r[1] for r in cur.fetchall()}

        # Nevândut deja declarat (pentru a pre-popula inputurile)
        cur.execute("""
            SELECT nume_produs, cantitate, pierderi
            FROM stoc_nevandut
            WHERE data = %s
        """, [azi])
        declarat_map = {r[0]: {'cantitate': r[1], 'pierderi': r[2]} for r in cur.fetchall()}

    stoc_nevandut = []
    for nume in sorted(gatit_map):
        gatit   = gatit_map[nume]
        servit  = servit_map.get(nume, 0)
        livrat  = livrat_map.get(nume, 0)
        ramas   = max(gatit - servit - livrat, 0)
        dec = declarat_map.get(nume)
        stoc_nevandut.append({
            'nume':      nume,
            'gatit':     gatit,
            'servit':    servit,
            'livrat':    livrat,
            'ramas':     ramas,
            'declarat':  dec['cantitate'] if dec else ramas,
            'pierderi':  dec['pierderi']  if dec else 0,
        })

    # ── Necesar ingrediente azi ──────────────────────────────────
    necesar_azi = list(
        NecesarZi.objects
        .filter(data_zi=azi)
        .select_related('ingredient')
        .order_by('ingredient__categorie', 'ingredient__nume')
    )
    # Grupăm pe categorii pentru afișare
    necesar_grouped = {}
    for n in necesar_azi:
        cat = n.ingredient.categorie or 'DIVERSE'
        cat_label = dict(Ingredient.CATEGORIE_CHOICES).get(cat, cat)
        if cat_label not in necesar_grouped:
            necesar_grouped[cat_label] = []
        necesar_grouped[cat_label].append(n)
    nr_necesar_total   = len(necesar_azi)
    nr_necesar_primit  = sum(1 for n in necesar_azi if n.primit)

    return render(request, 'bucatarie/index.html', {
        'azi':                 azi,
        'produse_lot':         produse_lot,
        'comenzi_ambalare':    comenzi_ambalare,
        'loturi_ev_ambalare':  loturi_ev_ambalare,
        'pachete_firme':       pachete_firme,
        'buffer':           buffer,
        'buffer_masa':      buffer_masa,
        'buffer_pachet':    buffer_pachet,
        'tip_plan':         tip_plan,
        'componente_def':   componente_def,
        'meniuri_def':      meniuri_def,
        'stoc_nevandut':    stoc_nevandut,
        'necesar_grouped':       necesar_grouped,
        'nr_necesar_total':      nr_necesar_total,
        'nr_necesar_primit':     nr_necesar_primit,
    })


@login_required
@require_POST
def gatit_batch(request):
    """Marchează toate liniile unui produs ca gătite (per produs, agregat)."""
    azi = timezone.localdate()
    nume_produs = request.POST.get('nume_produs', '').strip()
    if not nume_produs:
        return redirect('/staff/bucatarie/?tab=lot')
    now = timezone.now()
    ComandaLinie.objects.filter(
        comanda__data_comanda=azi,
        nume_produs=nume_produs,
        status='nou',
    ).exclude(comanda__status='anulat').update(status='gatit', gatit_la=now)
    return redirect('/staff/bucatarie/?tab=lot')


@login_required
@require_POST
def gatit_batch_reset(request):
    """Resetează toate liniile unui produs la status 'nou'."""
    azi = timezone.localdate()
    nume_produs = request.POST.get('nume_produs', '').strip()
    if not nume_produs:
        return redirect('/staff/bucatarie/?tab=lot')
    ComandaLinie.objects.filter(
        comanda__data_comanda=azi,
        nume_produs=nume_produs,
        status='gatit',
    ).exclude(comanda__status='anulat').update(status='nou', gatit_la=None)
    return redirect('/staff/bucatarie/?tab=lot')


@login_required
@require_POST
def comanda_gatit(request, pk):
    comanda = get_object_or_404(
        Comanda.objects.exclude(client_id=999).prefetch_related('linii'), pk=pk
    )
    now = timezone.now()
    ComandaLinie.objects.filter(comanda=comanda, status='nou').update(status='gatit', gatit_la=now)
    comanda.status = 'pregatit'
    if not comanda.pregatit_la:
        comanda.pregatit_la = now
    comanda.save(update_fields=['status', 'pregatit_la'])
    messages.success(request, f'Comanda #{pk} marcată ca gătită.')
    return redirect('/staff/bucatarie/?tab=lot')


@login_required
@require_POST
def linie_gatit(request, pk):
    linie = get_object_or_404(ComandaLinie, pk=pk)
    now = timezone.now()
    linie.status = 'gatit'
    linie.gatit_la = now
    linie.save(update_fields=['status', 'gatit_la'])
    comanda = linie.comanda
    if comanda.client_id != 999 and comanda.status == 'nou':
        if not comanda.linii.filter(status='nou').exists():
            comanda.status = 'pregatit'
            comanda.pregatit_la = now
            comanda.save(update_fields=['status', 'pregatit_la'])
    return redirect('/staff/bucatarie/?tab=lot')


@login_required
@require_POST
def impachetare_comanda(request, pk):
    """Marchează comanda/lotul ca pregătit/ambalat."""
    comanda = get_object_or_404(Comanda, pk=pk)
    now = timezone.now()
    comanda.status = 'pregatit'
    if not comanda.pregatit_la:
        comanda.pregatit_la = now
    comanda.save(update_fields=['status', 'pregatit_la'])
    messages.success(request, f'Comanda #{pk} ambalată.')
    return redirect('/staff/bucatarie/?tab=impachetare')


@login_required
@require_POST
def pachet_firma_ambalat(request, pk):
    """Marchează pachetul unui angajat firmă ca ambalat."""
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE serviri_ghiseu SET status_pachet = 'ambalat' WHERE id = %s AND status_pachet = 'astept'",
            [pk]
        )
    return redirect('/staff/bucatarie/?tab=impachetare')


@login_required
@require_POST
def buffer_add(request):
    """Bucătăria adaugă porții în buffer_componente (per componentă + tip servire)."""
    azi = timezone.localdate()
    componenta  = request.POST.get('componenta', '').strip()
    tip_servire = request.POST.get('tip_servire', '').strip()
    try:
        cantitate = int(request.POST.get('cantitate', 0))
    except (ValueError, TypeError):
        cantitate = 0

    COMPONENTE_VALIDE = ('f1', 'f2v1', 'f2v2', 'sal', 'v1', 'v2', 'solo_f1', 'solo_f2v1', 'solo_f2v2')
    TIP_VALIDE = ('masa', 'pachet')

    if componenta not in COMPONENTE_VALIDE or tip_servire not in TIP_VALIDE or cantitate <= 0:
        return redirect('/staff/bucatarie/?tab=buffer')

    # Verifică că produsele necesare sunt gătite
    tip_plan = request.session.get('tip_plan', 'pranz')
    plan_zi = list(
        PlanificareZi.objects.filter(data_zi=azi, tip_plan=tip_plan).select_related('produs')
    )
    f1     = next((r.produs for r in plan_zi if r.produs.categorie == 'felul_1'), None)
    f2list = [r.produs for r in plan_zi if r.produs.categorie == 'felul_2']
    f2v1   = f2list[0] if len(f2list) >= 1 else None
    f2v2   = f2list[1] if len(f2list) >= 2 else None
    sal    = next((r.produs for r in plan_zi if r.produs.categorie == 'salate'), None)

    # Harta componentă → produsele planificate necesare
    comp_produse = {
        'f1':        [f1],
        'f2v1':      [f2v1],
        'f2v2':      [f2v2],
        'sal':       [sal],
        'v1':        [f1, f2v1, sal],
        'v2':        [f1, f2v2, sal],
        'solo_f1':   [f1],
        'solo_f2v1': [f2v1, sal],
        'solo_f2v2': [f2v2, sal],
    }
    produse_necesare = [p for p in comp_produse.get(componenta, []) if p]

    if not produse_necesare:
        messages.error(request, 'Componenta nu există în planul zilei.')
        return redirect('/staff/bucatarie/?tab=buffer')

    # Cantitate gătită per produs și deja în buffer pentru această componentă
    with connection.cursor() as cur:
        cur.execute("""
            SELECT cl.nume_produs, SUM(cl.cantitate)
            FROM comenzi_linii cl
            JOIN comenzi c ON c.id = cl.comanda_id
            WHERE c.data_comanda = %s AND cl.status = 'gatit'
              AND c.status != 'anulat'
              AND cl.nume_produs = ANY(%s)
            GROUP BY cl.nume_produs
        """, [azi, [p.nume for p in produse_necesare]])
        gatit_map = {r[0]: r[1] for r in cur.fetchall()}

        cur.execute("""
            SELECT COALESCE(SUM(cantitate), 0)
            FROM buffer_componente
            WHERE data_zi = %s AND componenta = %s AND tip_plan = %s
        """, [azi, componenta, tip_plan])
        deja_buffer = cur.fetchone()[0] or 0

    negate = [p.nume for p in produse_necesare if p.nume not in gatit_map]
    if negate:
        messages.error(request, f'Nu s-a putut adăuga — produs(e) negătite: {", ".join(negate)}.')
        return redirect('/staff/bucatarie/?tab=buffer')

    maxim = min(gatit_map.get(p.nume, 0) for p in produse_necesare) - deja_buffer
    if cantitate > maxim:
        messages.error(request, f'Cantitate prea mare — maxim disponibil pentru adăugare: {max(maxim, 0)} porții.')
        return redirect('/staff/bucatarie/?tab=buffer')

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO buffer_componente (data_zi, componenta, tip_servire, tip_plan, cantitate, distribuit)
            VALUES (%s, %s, %s, %s, %s, 0)
            ON CONFLICT (data_zi, componenta, tip_servire, tip_plan)
            DO UPDATE SET cantitate = buffer_componente.cantitate + EXCLUDED.cantitate
        """, [azi, componenta, tip_servire, tip_plan, cantitate])
    return redirect('/staff/bucatarie/?tab=buffer')


@login_required
def necesar_export(request):
    azi = timezone.localdate()
    necesar = list(
        NecesarZi.objects
        .filter(data_zi=azi)
        .select_related('ingredient')
        .order_by('ingredient__categorie', 'ingredient__nume')
    )

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = wb.add_worksheet('Necesar')

    # Formate — alb-negru, font Calibri
    FONT = 'Calibri'
    base = {'font_name': FONT, 'valign': 'vcenter', 'align': 'center'}

    title_fmt = wb.add_format({**base, 'bold': True, 'font_size': 14})
    date_fmt  = wb.add_format({**base, 'italic': True, 'font_size': 10, 'font_color': '#555555'})
    hdr_fmt   = wb.add_format({**base, 'bold': True, 'font_size': 11,
                                'bg_color': '#333333', 'font_color': '#FFFFFF', 'border': 1})
    cat_fmt   = wb.add_format({**base, 'bold': True, 'italic': True, 'font_size': 10,
                                'bg_color': '#CCCCCC', 'font_color': '#000000', 'border': 1})
    cell_fmt  = wb.add_format({**base, 'font_name': FONT, 'border': 1, 'font_size': 11})
    qty_fmt   = wb.add_format({**base, 'font_name': FONT, 'border': 1, 'bold': True, 'font_size': 11})
    check_fmt = wb.add_format({**base, 'font_name': FONT, 'border': 1, 'font_size': 13, 'bold': True})

    ws.set_column(0, 0, 42)   # Ingredient
    ws.set_column(1, 1, 22)   # Cantitate
    ws.set_column(2, 2, 12)   # Unitate
    ws.set_column(3, 3, 14)   # Primit
    ws.set_row(0, 32)
    ws.set_row(1, 16)
    ws.set_row(2, 22)

    # Titlu
    ws.merge_range('A1:D1', f'Listă Necesar Ingrediente', title_fmt)
    ws.merge_range('A2:D2', azi.strftime('%A, %d %B %Y').capitalize(), date_fmt)

    # Header
    row = 2
    for col, label in enumerate(['Ingredient', 'Cantitate necesară', 'U.M.', 'Primit ✓']):
        ws.write(row, col, label, hdr_fmt)

    row = 3
    cat_curent = None
    cat_labels = dict(Ingredient.CATEGORIE_CHOICES)

    for n in necesar:
        cat = n.ingredient.categorie or 'DIVERSE'
        if cat != cat_curent:
            cat_curent = cat
            ws.merge_range(row, 0, row, 3, cat_labels.get(cat, cat), cat_fmt)
            row += 1

        # Cantitate formatată
        u = n.ingredient.unitate
        cant = float(n.cantitate_necesara)
        if u == 'kg' and cant < 1:
            cant_str = f'{cant * 1000:.0f} g'
            um_str = 'g'
        elif u == 'l' and cant < 1:
            cant_str = f'{cant * 1000:.0f} ml'
            um_str = 'ml'
        else:
            cant_str = f'{cant:.3f}'.rstrip('0').rstrip('.')
            um_str = u

        ws.write(row, 0, n.ingredient.nume, cell_fmt)
        ws.write(row, 1, cant_str, qty_fmt)
        ws.write(row, 2, um_str, cell_fmt)
        ws.write(row, 3, '✓' if n.primit else '', check_fmt)
        ws.set_row(row, 20)
        row += 1

    # Print setup
    ws.set_portrait()
    ws.set_paper(9)   # A4
    ws.fit_to_pages(1, 0)
    ws.center_horizontally()
    ws.set_margins(left=0.3, right=0.3, top=0.5, bottom=0.5)
    ws.set_header(f'&C&B&11 Listă Necesar Ingrediente — {azi.strftime("%d.%m.%Y")}',
                  {'margin': 0.2})
    ws.set_footer('&C&8Pagina &P din &N', {'margin': 0.2})
    ws.repeat_rows(2)   # header tabel repetat pe fiecare pagină

    wb.close()
    output.seek(0)

    filename = f'Necesar_{azi.strftime("%d_%m_%Y")}.xlsx'
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def necesar_primit(request, pk):
    """Marchează un ingredient din necesar ca primit (sau anulează bifarea)."""
    azi = timezone.localdate()
    nec = get_object_or_404(NecesarZi, pk=pk, data_zi=azi)
    nec.primit = not nec.primit
    nec.primit_la = timezone.now() if nec.primit else None
    nec.save(update_fields=['primit', 'primit_la'])
    return redirect('/staff/bucatarie/?tab=necesar')


@login_required
@require_POST
def stoc_declara(request):
    azi = timezone.localdate()
    saved = 0
    produse = set()
    for key in request.POST:
        if key.startswith('stoc_'):
            produse.add(key[5:])
        elif key.startswith('pierderi_'):
            produse.add(key[9:])

    with connection.cursor() as cur:
        for nume_produs in produse:
            try:
                cantitate = int(request.POST.get(f'stoc_{nume_produs}', 0))
                pierderi  = int(request.POST.get(f'pierderi_{nume_produs}', 0))
                if cantitate >= 0 and pierderi >= 0:
                    cur.execute("""
                        INSERT INTO stoc_nevandut
                            (data, nume_produs, cantitate, cantitate_servita, pierderi, declarat_la)
                        VALUES (%s, %s, %s, 0, %s, NOW())
                        ON CONFLICT (data, nume_produs)
                        DO UPDATE SET cantitate    = EXCLUDED.cantitate,
                                      pierderi     = EXCLUDED.pierderi,
                                      declarat_la  = NOW()
                    """, [azi, nume_produs, cantitate, pierderi])
                    saved += 1
            except (ValueError, TypeError):
                pass
    messages.success(request, f'Stoc nevândut salvat ({saved} produse).')
    return redirect('/staff/bucatarie/?tab=stoc')
