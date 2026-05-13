import io
import json
from datetime import date, timedelta

import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from apps.core.models import (
    AngajatFirma, Comanda, ComandaLinie, Firma,
    Ingredient, Livrator, NecesarZi, PlanificareZi,
    Produs, RetetaLinie, ServireGhiseuLinie, Utilizator,
)

CATEGORII = [
    ('felul_1',  '🥣 Felul 1'),
    ('felul_2',  '🍖 Felul 2'),
    ('salate',   '🥗 Salate'),
    ('sandwich', '🥪 Sandwich'),
    ('special',  '✨ Speciale'),
    ('desert',   '🍮 Desert'),
]
CATEGORII_VALIDE = [c[0] for c in CATEGORII]

ZILE_RO = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']


def get_saptamana(data):
    luni = data - timedelta(days=data.weekday())
    return [luni + timedelta(days=i) for i in range(7)]


@login_required
def index(request):
    return redirect('manager:lansare')


# ── Nomenclator ──────────────────────────────────────────────

@login_required
def nomenclator(request):
    produse = cache.get('nomenclator_produse')
    if produse is None:
        produse = list(Produs.objects.prefetch_related('reteta').order_by('categorie', 'nume'))
        cache.set('nomenclator_produse', produse, 300)  # 5 minute

    grouped = {cod: [] for cod, _ in CATEGORII}
    for p in produse:
        if p.categorie in grouped:
            grouped[p.categorie].append(p)

    return render(request, 'admin_manager/nomenclator.html', {
        'grouped': [(cod, label, grouped[cod]) for cod, label in CATEGORII],
        'categorii': CATEGORII,
        'categorii_valide': CATEGORII_VALIDE,
    })


@login_required
@require_POST
def produs_add(request):
    nume = request.POST.get('nume', '').strip()
    categorie = request.POST.get('categorie', '').strip()
    pret_raw = request.POST.get('pret_standard', '').strip()

    errors = []
    if not nume:
        errors.append('Denumirea este obligatorie.')
    if categorie not in CATEGORII_VALIDE:
        errors.append('Categoria selectată este invalidă.')
    pret = None
    if pret_raw:
        try:
            pret = float(pret_raw.replace(',', '.'))
            if pret < 0:
                errors.append('Prețul nu poate fi negativ.')
        except ValueError:
            errors.append('Prețul introdus nu este valid.')

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect('manager:nomenclator')

    Produs.objects.create(nume=nume, categorie=categorie, pret_standard=pret)
    cache.delete('nomenclator_produse')
    messages.success(request, f'Produs „{nume}" adăugat.')
    return redirect('manager:nomenclator')


@login_required
@require_http_methods(['GET', 'POST'])
def produs_edit(request, pk):
    produs = get_object_or_404(Produs, pk=pk)

    if request.method == 'GET':
        return render(request, 'admin_manager/partials/produs_edit_row.html', {
            'produs': produs,
            'categorii': CATEGORII,
        })

    nume = request.POST.get('nume', '').strip()
    categorie = request.POST.get('categorie', '').strip()
    pret_raw = request.POST.get('pret_standard', '').strip()

    if not nume or categorie not in CATEGORII_VALIDE:
        messages.error(request, 'Date invalide.')
        return redirect('manager:nomenclator')

    produs.nume = nume
    produs.categorie = categorie
    produs.pret_standard = float(pret_raw.replace(',', '.')) if pret_raw else None
    produs.save()
    cache.delete('nomenclator_produse')

    return render(request, 'admin_manager/partials/produs_row.html', {
        'produs': produs,
        'categorii': CATEGORII,
    })


@login_required
@require_POST
def produs_delete(request, pk):
    produs = get_object_or_404(Produs, pk=pk)
    produs.delete()
    cache.delete('nomenclator_produse')
    return HttpResponse('')


@login_required
def produs_export(request):
    produse = Produs.objects.all().order_by('categorie', 'nume')

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = workbook.add_worksheet('Nomenclator')

    hdr = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center'})
    cell = workbook.add_format({'border': 1})
    money = workbook.add_format({'border': 1, 'num_format': '#,##0.00 "LEI"'})

    ws.set_column(0, 0, 5)
    ws.set_column(1, 1, 35)
    ws.set_column(2, 2, 18)
    ws.set_column(3, 3, 15)

    for col, title in enumerate(['#', 'Denumire', 'Categorie', 'Preț (RON)']):
        ws.write(0, col, title, hdr)

    for i, p in enumerate(produse, 1):
        ws.write(i, 0, i, cell)
        ws.write(i, 1, p.nume, cell)
        ws.write(i, 2, p.categorie_display, cell)
        ws.write(i, 3, float(p.pret_standard) if p.pret_standard else '', money)

    workbook.close()
    output.seek(0)

    filename = f"Nomenclator_{date.today().strftime('%d_%m_%Y')}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Planificare ───────────────────────────────────────────────

@login_required
def planificare(request):
    # Ziua selectată (default azi)
    data_str = request.GET.get('data')
    try:
        data_sel = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        data_sel = date.today()

    zile = get_saptamana(data_sel)
    saptamana_prev = (zile[0] - timedelta(days=7)).isoformat()
    saptamana_next = (zile[0] + timedelta(days=7)).isoformat()

    # Planificarea existentă pentru săptămână
    plan_rows = PlanificareZi.objects.filter(
        data_zi__range=(zile[0], zile[-1])
    ).select_related('produs')

    # Organizăm: plan[data][tip_plan] = [produs, ...]
    plan = {}
    for row in plan_rows:
        d = row.data_zi
        t = row.tip_plan
        plan.setdefault(d, {}).setdefault(t, []).append(row.produs)

    # Produse disponibile per categorie
    toate = cache.get('nomenclator_produse')
    if toate is None:
        toate = list(Produs.objects.prefetch_related('reteta').order_by('categorie', 'nume'))
        cache.set('nomenclator_produse', toate, 300)
    felul_1  = [p for p in toate if p.categorie == 'felul_1']
    felul_2  = [p for p in toate if p.categorie == 'felul_2']
    salate   = [p for p in toate if p.categorie == 'salate']
    sandwich = [p for p in toate if p.categorie == 'sandwich']

    # Ziua selectată pentru formulare
    zi_idx = data_sel.weekday()
    zi_plan = plan.get(data_sel, {})

    # Tabel săptămânal: listă de rânduri gata de iterat în template
    tipuri_masa = [
        ('pranz',    '🥣 Prânz'),
        ('cina',     '🌙 Cină'),
        ('sandwich', '🥪 Sandwich'),
    ]
    tabel = []
    for tip_cod, tip_label in tipuri_masa:
        rand = {'label': tip_label, 'zile': []}
        for zi in zile:
            produse = plan.get(zi, {}).get(tip_cod, [])
            rand['zile'].append({'zi': zi, 'produse': produse, 'selectat': zi == data_sel})
        tabel.append(rand)

    return render(request, 'admin_manager/planificare.html', {
        'data_sel':       data_sel,
        'zi_nume':        ZILE_RO[zi_idx],
        'zile':           list(zip(zile, [ZILE_RO[i] for i in range(7)])),
        'saptamana_prev': saptamana_prev,
        'saptamana_next': saptamana_next,
        'zi_plan':        zi_plan,
        'tabel':          tabel,
        'felul_1':        felul_1,
        'felul_2':        felul_2,
        'salate':         salate,
        'sandwich':       sandwich,
    })


@login_required
@require_POST
def planificare_salveaza(request):
    data_str = request.POST.get('data')
    tip_plan = request.POST.get('tip_plan')

    try:
        data_zi = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        messages.error(request, 'Dată invalidă.')
        return redirect('manager:planificare')

    if tip_plan == 'pranz':
        ids = [
            request.POST.get('f1'),
            request.POST.get('f2a'),
            request.POST.get('f2b'),
            request.POST.get('acc'),
        ]
        if not all(ids):
            messages.error(request, 'Selectează toate componentele prânzului.')
            return redirect(f"{request.META.get('HTTP_REFERER', '/staff/manager/planificare/')}#{tip_plan}")

    elif tip_plan == 'cina':
        ids = [request.POST.get('f2c'), request.POST.get('salc')]
        if not all(ids):
            messages.error(request, 'Selectează felul principal și salata pentru cină.')
            return redirect(f"{request.META.get('HTTP_REFERER', '/staff/manager/planificare/')}#{tip_plan}")

    elif tip_plan == 'sandwich':
        ids = request.POST.getlist('sw')
        if not ids:
            messages.error(request, 'Selectează cel puțin un sandwich.')
            return redirect(f"{request.META.get('HTTP_REFERER', '/staff/manager/planificare/')}#{tip_plan}")

    else:
        messages.error(request, 'Tip plan invalid.')
        return redirect('manager:planificare')

    # Șterge planificarea existentă pentru ziua și tipul respectiv
    PlanificareZi.objects.filter(data_zi=data_zi, tip_plan=tip_plan).delete()

    # Inserează noile înregistrări
    for pid in ids:
        try:
            produs = Produs.objects.get(pk=int(pid))
            PlanificareZi.objects.create(data_zi=data_zi, produs=produs, tip_plan=tip_plan)
        except (Produs.DoesNotExist, ValueError):
            pass

    tip_label = {'pranz': 'Prânz', 'cina': 'Cină', 'sandwich': 'Sandwich'}.get(tip_plan, tip_plan)
    messages.success(request, f'{tip_label} planificat pentru {ZILE_RO[data_zi.weekday()]}, {data_zi.strftime("%d.%m.%Y")}.')
    return redirect(f'/staff/manager/planificare/?data={data_str}')


@login_required
def planificare_export(request):
    data_str = request.GET.get('data')
    try:
        data_sel = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        data_sel = date.today()

    # Luni–Sâmbătă (6 zile, ca în Streamlit)
    zile = get_saptamana(data_sel)[:6]

    plan_rows = PlanificareZi.objects.filter(
        data_zi__range=(zile[0], zile[-1])
    ).select_related('produs')

    plan = {}
    for row in plan_rows:
        plan.setdefault(row.data_zi, {}).setdefault(row.tip_plan, []).append(row.produs)

    FONT = 'Segoe UI'
    TEXT_ALERGENI = '\n*Alergeni: gluten, ouă, lactate, țelină, muștar, nuci.'

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = wb.add_worksheet('Flyer_Meniu')

    # Configurare print
    ws.set_landscape()
    ws.set_margins(0.2, 0.2, 0.2, 0.2)
    ws.set_print_scale(95)
    ws.set_paper(9)  # A4

    # Formate — alb-negru prietenos
    fmt_titlu = wb.add_format({
        'bold': True, 'font_size': 28, 'align': 'right',
        'valign': 'vcenter', 'font_name': FONT,
    })
    fmt_contact = wb.add_format({
        'bold': True, 'font_size': 11, 'align': 'right',
        'valign': 'vcenter', 'font_name': FONT, 'text_wrap': True,
    })
    fmt_subtitlu = wb.add_format({
        'italic': True, 'font_size': 11, 'align': 'left',
        'valign': 'top', 'font_name': FONT,
    })
    fmt_header = wb.add_format({
        'bold': True, 'bg_color': '#F2F2F2', 'border': 1,
        'align': 'center', 'valign': 'vcenter',
        'font_size': 11, 'font_name': FONT,
    })
    fmt_celula = wb.add_format({
        'text_wrap': True, 'valign': 'vcenter', 'align': 'left',
        'indent': 1, 'border': 1, 'font_size': 10, 'font_name': FONT,
    })
    fmt_alergeni = wb.add_format({
        'font_size': 7.5, 'italic': True,
        'font_color': '#666666', 'font_name': FONT,
    })
    fmt_footer_titlu = wb.add_format({
        'bold': True, 'font_size': 12,
        'bottom': 1, 'font_name': FONT,
    })
    fmt_footer_text = wb.add_format({
        'text_wrap': True, 'font_size': 9.5,
        'font_name': FONT, 'valign': 'top',
    })

    # Lățimi coloane
    ws.set_column(0, 0, 20)
    ws.set_column(1, 1, 58)
    ws.set_column(2, 2, 58)

    # Rând 0 — titlu + contact
    ws.set_row(0, 45)
    ws.merge_range(0, 0, 0, 1, 'CANTINA LOTUS', fmt_titlu)
    ws.write(0, 2, '0746.358.018\n0743.090.212', fmt_contact)

    # Rând 1 — subtitlu
    ws.merge_range(1, 0, 1, 2,
        'Mâncare gătită zilnic cu ingrediente proaspete | Rezervări și Livrări',
        fmt_subtitlu)

    # Rând 2 — separator implicit (gol)

    # Rând 3 — header coloane
    for col, hdr in enumerate(['DATA / ZIUA', 'MENIU PRÂNZ', 'MENIU CINĂ']):
        ws.write(3, col, hdr, fmt_header)

    # Rânduri date — Luni-Sâmbătă
    for r_idx, zi in enumerate(zile):
        ws.set_row(4 + r_idx, 68)
        zi_label = f'{ZILE_RO[zi.weekday()]}\n{zi.strftime("%d.%m")}'
        ws.write(4 + r_idx, 0, zi_label, fmt_celula)

        for col, tip in enumerate(['pranz', 'cina'], 1):
            produse = plan.get(zi, {}).get(tip, [])
            if produse:
                text_meniu = '\n'.join(f'• {p.nume}' for p in produse)
                ws.write_rich_string(
                    4 + r_idx, col,
                    text_meniu, fmt_alergeni, TEXT_ALERGENI,
                    fmt_celula
                )
            else:
                ws.write(4 + r_idx, col, '—', fmt_celula)

    # Footer
    last_row = 4 + len(zile) + 2
    ws.merge_range(last_row, 0, last_row, 2, 'SERVICII ȘI PROGRAM', fmt_footer_titlu)
    info = (
        '• PROGRAM SERVIRE: Prânz (11:00–13:00) | Cină (16:00–18:00) '
        '• LIVRĂRI: Comenzi până la 10:30 '
        '• ADRESĂ: Str. Ing. Dumitru Ivanov, nr. 18, Tulcea\n'
        '• EVENIMENTE: Pomeni, parastase, majorate, aniversări și catering corporate.\n'
        '• NOTĂ: Toate preparatele sunt gătite proaspăt în ziua servirii.'
    )
    ws.merge_range(last_row + 1, 0, last_row + 2, 2, info, fmt_footer_text)
    ws.set_row(last_row, 16)
    ws.set_row(last_row + 1, 42)

    wb.close()
    output.seek(0)

    filename = f"Meniu_Lotus_{zile[0].strftime('%d_%m')}_{zile[-1].strftime('%d_%m')}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Lansare Producție ─────────────────────────────────────────

def _calc_stoc(data_zi):
    lansat_qs = (
        ComandaLinie.objects
        .filter(comanda__data_comanda=data_zi, comanda__client_id=999)
        .exclude(comanda__status='anulat')
        .values('nume_produs')
        .annotate(total=Sum('cantitate'))
    )
    stoc = {row['nume_produs']: {'lansat': row['total'], 'consumat': 0}
            for row in lansat_qs}
    if not stoc:
        return stoc

    # Comenzi livrare recepție (clienți reali, neAnulate)
    for row in (
        ComandaLinie.objects
        .filter(comanda__data_comanda=data_zi, comanda__tip_comanda='livrare')
        .exclude(comanda__client_id=999)
        .exclude(comanda__status='anulat')
        .values('nume_produs').annotate(total=Sum('cantitate'))
    ):
        if row['nume_produs'] in stoc:
            stoc[row['nume_produs']]['consumat'] += row['total']

    # Serviri ghișeu (bon casă + firme) — nu eveniment (are lot propriu)
    for row in (
        ServireGhiseuLinie.objects
        .filter(servire__data_servire=data_zi,
                servire__tip_servire__in=['bon_casa', 'firma'])
        .values('nume_produs').annotate(total=Sum('cantitate'))
    ):
        if row['nume_produs'] in stoc:
            stoc[row['nume_produs']]['consumat'] += row['total']

    for s in stoc.values():
        s['ramas'] = max(s['lansat'] - s['consumat'], 0)
    return stoc


@login_required
def lansare(request):
    data_str = request.GET.get('data')
    try:
        data_sel = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        data_sel = date.today()

    zile = get_saptamana(data_sel)
    saptamana_prev = (zile[0] - timedelta(days=7)).isoformat()
    saptamana_next = (zile[0] + timedelta(days=7)).isoformat()
    zi_idx = data_sel.weekday()

    _plan_all = list(
        PlanificareZi.objects.filter(data_zi=data_sel, tip_plan__in=['pranz', 'cina'])
        .select_related('produs').order_by('produs__categorie', 'produs__nume')
    )
    plan_pranz = [r for r in _plan_all if r.tip_plan == 'pranz']
    plan_cina  = [r for r in _plan_all if r.tip_plan == 'cina']

    loturi_qs = list(
        Comanda.objects
        .filter(data_comanda=data_sel, client_id=999)
        .exclude(status='anulat')
        .prefetch_related('linii')
        .order_by('ora_livrare_estimata')
    )
    loturi_pranz = [l for l in loturi_qs if l.tip_comanda == 'pranz']
    loturi_cina  = [l for l in loturi_qs if l.tip_comanda == 'cina']
    loturi_ev    = [l for l in loturi_qs if l.tip_comanda in ('eveniment', 'special')]

    stoc = _calc_stoc(data_sel)

    toate_produse = cache.get('nomenclator_produse')
    if toate_produse is None:
        toate_produse = list(Produs.objects.prefetch_related('reteta').order_by('categorie', 'nume'))
        cache.set('nomenclator_produse', toate_produse, 300)
    categorii_ev  = [(cod, label, [p for p in toate_produse if p.categorie == cod])
                     for cod, label in CATEGORII]

    def _categorii_din_plan(plan):
        produse = [r.produs for r in plan]
        return [(cod, label, [p for p in produse if p.categorie == cod])
                for cod, label in CATEGORII]

    def _plan_json(plan):
        return json.dumps([{
            'id': r.produs.pk, 'nume': r.produs.nume,
            'pret': float(r.produs.pret_standard or 0), 'qty': 0,
        } for r in plan])

    return render(request, 'admin_manager/lansare.html', {
        'data_sel':             data_sel,
        'zi_nume':              ZILE_RO[zi_idx],
        'zile':                 list(zip(zile, [ZILE_RO[i] for i in range(7)])),
        'saptamana_prev':       saptamana_prev,
        'saptamana_next':       saptamana_next,
        'plan_pranz':           plan_pranz,
        'plan_cina':            plan_cina,
        'plan_pranz_json':      _plan_json(plan_pranz),
        'plan_cina_json':       _plan_json(plan_cina),
        'categorii_plan_pranz': _categorii_din_plan(plan_pranz),
        'categorii_plan_cina':  _categorii_din_plan(plan_cina),
        'loturi_pranz':         loturi_pranz,
        'loturi_cina':          loturi_cina,
        'loturi_ev':            loturi_ev,
        'stoc':                 stoc,
        'categorii_ev':         categorii_ev,
    })


@login_required
@require_POST
def lansare_salveaza(request):
    data_str = request.POST.get('data')
    tip = request.POST.get('tip_plan', '')

    try:
        data_zi = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        messages.error(request, 'Dată invalidă.')
        return redirect('manager:lansare')

    if tip not in ('pranz', 'cina', 'eveniment'):
        messages.error(request, 'Tip plan invalid.')
        return redirect('manager:lansare')

    items = []
    for key in request.POST:
        if key.startswith('qty_'):
            try:
                pid = int(key[4:])
                qty = int(request.POST[key])
                if qty > 0:
                    produs = Produs.objects.get(pk=pid)
                    items.append({
                        'nume': produs.nume,
                        'qty':  qty,
                        'pret': float(produs.pret_standard or 0),
                    })
            except (ValueError, Produs.DoesNotExist):
                pass

    if not items:
        messages.error(request, 'Adaugă cel puțin un produs cu cantitate > 0.')
        return redirect(f'/staff/manager/lansare/?data={data_str}')

    descriere = request.POST.get('descriere', '').strip()
    if tip == 'eveniment' and not descriere:
        messages.error(request, 'Descrierea evenimentului este obligatorie.')
        return redirect(f'/staff/manager/lansare/?data={data_str}')

    tip_ridicare = request.POST.get('tip_ridicare', 'la_masa') if tip == 'eveniment' else None

    ora_map = {'pranz': '12:00', 'cina': '19:00', 'eveniment': '08:00'}
    obs_map = {
        'pranz':     'Lot Producție Prânz',
        'cina':      'Lot Producție Cină',
        'eveniment': descriere,
    }
    total = sum(item['pret'] * item['qty'] for item in items)

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO comenzi
                (client_id, data_comanda, ora_livrare_estimata,
                 status, metoda_plata, total_plata, sofer, observatii, tip_comanda, tip_ridicare, created_at)
            VALUES (%s, %s, %s, 'nou', 'cantina', %s, 'INTERN', %s, %s, %s, NOW())
            RETURNING id
        """, [999, data_zi, ora_map[tip], total, obs_map[tip], tip, tip_ridicare])
        comanda_id = cur.fetchone()[0]

        for item in items:
            cur.execute("""
                INSERT INTO comenzi_linii
                    (comanda_id, nume_produs, cantitate, pret_unitar, tip_linie, status)
                VALUES (%s, %s, %s, %s, 'standard', 'nou')
            """, [comanda_id, item['nume'], item['qty'], item['pret']])

        # ── Calculează necesarul de ingrediente și face UPSERT în necesar_zi ──
        values_parts = ', '.join(['(%s, %s::integer)'] * len(items))
        params_necesar = [data_zi]
        for item in items:
            params_necesar += [item['nume'], item['qty']]
        cur.execute(f"""
            INSERT INTO necesar_zi (data_zi, ingredient_id, cantitate_necesara)
            SELECT
                %s,
                rl.ingredient_id,
                SUM(rl.cantitate * v.qty)
            FROM (VALUES {values_parts}) AS v(pname, qty)
            JOIN produse p ON p.nume = v.pname
            JOIN reteta_linii rl ON rl.produs_id = p.id
            GROUP BY rl.ingredient_id
            ON CONFLICT (data_zi, ingredient_id) DO UPDATE
              SET cantitate_necesara = necesar_zi.cantitate_necesara + EXCLUDED.cantitate_necesara
        """, params_necesar)

    tip_label = {'pranz': 'Prânz', 'cina': 'Cină', 'eveniment': 'Eveniment'}.get(tip, tip)
    messages.success(request, f'Lot {tip_label} lansat cu succes pentru {data_zi.strftime("%d.%m.%Y")}.')
    return redirect(f'/staff/manager/lansare/?data={data_str}')


@login_required
@require_POST
def lansare_adauga(request, pk):
    """Adaugă produse la un lot existent (completare lot)."""
    data_str = request.POST.get('data', date.today().isoformat())
    comanda = get_object_or_404(Comanda, pk=pk, client_id=999)

    produse_map = {p.pk: p for p in Produs.objects.all()}
    adaugate = 0

    with connection.cursor() as cur:
        for key, val in request.POST.items():
            if not key.startswith('qty_'):
                continue
            try:
                pid = int(key[4:])
                qty = int(val)
            except (ValueError, TypeError):
                continue
            if qty <= 0:
                continue
            produs = produse_map.get(pid)
            if not produs:
                continue

            # Incrementează linia existentă sau creează una nouă
            cur.execute("""
                UPDATE comenzi_linii SET cantitate = cantitate + %s
                WHERE comanda_id = %s AND nume_produs = %s AND status = 'nou'
            """, [qty, comanda.pk, produs.nume])
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO comenzi_linii
                        (comanda_id, nume_produs, cantitate, pret_unitar, tip_linie, status)
                    VALUES (%s, %s, %s, %s, 'standard', 'nou')
                """, [comanda.pk, produs.nume, qty, float(produs.pret_standard or 0)])
            adaugate += 1

    if adaugate:
        messages.success(request, f'Lot #{pk} completat cu {adaugate} produs(e).')
    else:
        messages.warning(request, 'Niciun produs adăugat.')
    return redirect(f'/staff/manager/lansare/?data={data_str}')


@login_required
@require_POST
def lansare_sterge(request, pk):
    data_str = request.POST.get('data', date.today().isoformat())
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE comenzi SET status = 'anulat' WHERE id = %s AND client_id = 999",
            [pk]
        )
    messages.success(request, 'Lot anulat.')
    return redirect(f'/staff/manager/lansare/?data={data_str}')


# ── Firme ─────────────────────────────────────────────────────

TIPURI_CONTRACT = [
    ('pranz_cina', 'Prânz + Cină'),
    ('pranz',      'Doar Prânz'),
    ('cina',       'Doar Cină'),
]
TIPURI_CONTRACT_DICT = dict(TIPURI_CONTRACT)

TIP_FIRMA = [
    ('ghiseu',         'Ghișeu (nominal)'),
    ('ghiseu_livrare', 'Ghișeu + Livrare prânz'),
    ('livrare',        'Livrare fixă'),
    ('special',        'Meniu Special'),
]
TIP_FIRMA_DICT  = dict(TIP_FIRMA)
TIP_FIRMA_VALIDE = [t[0] for t in TIP_FIRMA]

TIP_FIRMA_DESC = {
    'ghiseu':         'Angajații vin la ghișeu. Servire nominală per persoană.',
    'ghiseu_livrare': 'Prânzul se livrează. Cina se ridică la ghișeu. Tabel nominal.',
    'livrare':        'Cantitate fixă livrată zilnic (sandwich, meniu fix).',
    'special':        'Meniu construit manual, independent de planificarea zilei.',
}


def _sync_rezervare(firma_pk):
    """Upsert today's reservation to match active employee count for the firm."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM angajati_firme WHERE firma_id = %s AND activ = true",
            [firma_pk]
        )
        count = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO rezervari_firme (firma_id, data_rez, cantitate)
            VALUES (%s, %s, %s)
            ON CONFLICT (firma_id, data_rez) DO UPDATE SET cantitate = EXCLUDED.cantitate
        """, [firma_pk, date.today(), count])


def _ensure_client_firma(firma):
    if firma.client_id:
        return firma.client_id
    with connection.cursor() as cur:
        cur.execute(
            "INSERT INTO clienti (nume_client, telefon) VALUES (%s, %s) RETURNING id",
            [firma.nume_firma, f'firma_{firma.pk}']
        )
        client_id = cur.fetchone()[0]
        cur.execute("UPDATE firme SET client_id = %s WHERE id = %s", [client_id, firma.pk])
    firma.client_id = client_id
    return client_id


def _get_raport_serviri(data_zi):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT f.id AS firma_id, f.nume_firma,
                   ag.nume_angajat, sg.tip_ridicare,
                   sg.ora_servire,
                   string_agg(sgl.nume_produs, ', ' ORDER BY sgl.id) AS produse
            FROM serviri_ghiseu sg
            JOIN firme f ON sg.firma_id = f.id
            JOIN angajati_firme ag ON sg.angajat_id = ag.id
            JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
            WHERE sg.data_servire = %s AND sg.tip_servire = 'firma'
            GROUP BY f.id, f.nume_firma, ag.nume_angajat, sg.id, sg.tip_ridicare, sg.ora_servire
            ORDER BY f.nume_firma, ag.nume_angajat
        """, [data_zi])
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    raport = {}
    for row in rows:
        fid = row['firma_id']
        if fid not in raport:
            raport[fid] = {'nume_firma': row['nume_firma'], 'angajati': []}
        raport[fid]['angajati'].append(row)
    return list(raport.values())


@login_required
def firme(request):
    tab = request.GET.get('tab', 'gestiune')

    data_str = request.GET.get('data')
    try:
        data_sel = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        data_sel = date.today()

    raport_data_str = request.GET.get('raport_data')
    try:
        raport_data = date.fromisoformat(raport_data_str)
    except (TypeError, ValueError):
        raport_data = date.today()

    # Gestiune
    toate_firme = list(
        Firma.objects.prefetch_related('angajati')
        .select_related('client')
        .order_by('tip_firma', 'nume_firma')
    )
    firme_grouped = [
        (cod, label, [f for f in toate_firme if f.tip_firma == cod])
        for cod, label in TIP_FIRMA
    ]

    # Lansare
    _plan_all = list(
        PlanificareZi.objects.filter(data_zi=data_sel, tip_plan__in=['pranz', 'sandwich'])
        .select_related('produs')
    )
    plan_pranz    = [r for r in _plan_all if r.tip_plan == 'pranz']
    plan_sandwich = [r for r in _plan_all if r.tip_plan == 'sandwich']
    felul_1      = [r.produs for r in plan_pranz if r.produs.categorie == 'felul_1']
    felul_2      = [r.produs for r in plan_pranz if r.produs.categorie == 'felul_2']
    salate_plan  = [r.produs for r in plan_pranz if r.produs.categorie == 'salate']
    sandwich_plan = [r.produs for r in plan_sandwich]
    livratori    = list(Livrator.objects.filter(activ=True).order_by('nume'))

    firme_livrare = [f for f in toate_firme
                     if f.tip_firma in ('ghiseu_livrare', 'livrare', 'special') and f.activ]
    client_to_firma = {f.client_id: f.pk for f in toate_firme if f.client_id}

    comenzi_firme = list(
        Comanda.objects
        .filter(data_comanda=data_sel, tip_comanda__in=['livrare', 'special'])
        .exclude(status='anulat')
        .prefetch_related('linii')
    )
    lansate = {}
    for c in comenzi_firme:
        fid = client_to_firma.get(c.client_id)
        if fid:
            lansate[fid] = {
                'comanda_id': c.pk,
                'sofer':  c.sofer or '',
                'ora':    str(c.ora_livrare_estimata)[:5] if c.ora_livrare_estimata else '',
                'total':  float(c.total_plata or 0),
                'linii':  list(c.linii.all()),
            }

    # Prezență
    firme_ghiseu = [f for f in toate_firme
                    if f.tip_firma in ('ghiseu', 'ghiseu_livrare') and f.activ]
    with connection.cursor() as cur:
        cur.execute(
            "SELECT firma_id, cantitate FROM rezervari_firme WHERE data_rez = %s",
            [date.today()]
        )
        rezervari = {row[0]: row[1] for row in cur.fetchall()}

    # Auto-init: first visit of the day — create missing reservations from active employees
    lipsesc = [f.pk for f in firme_ghiseu if f.pk not in rezervari]
    if lipsesc:
        for firma_pk in lipsesc:
            _sync_rezervare(firma_pk)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT firma_id, cantitate FROM rezervari_firme WHERE data_rez = %s",
                [date.today()]
            )
            rezervari = {row[0]: row[1] for row in cur.fetchall()}

    total_rez = sum(rezervari.values())

    # Raport
    raport = _get_raport_serviri(raport_data)

    toate_produse = cache.get('nomenclator_produse')
    if toate_produse is None:
        toate_produse = list(Produs.objects.prefetch_related('reteta').order_by('categorie', 'nume'))
        cache.set('nomenclator_produse', toate_produse, 300)
    categorii_produse = [
        (cod, label, [p for p in toate_produse if p.categorie == cod])
        for cod, label in CATEGORII
    ]

    return render(request, 'admin_manager/firme.html', {
        'tab':                  tab,
        'data_sel':             data_sel,
        'raport_data':          raport_data,
        'firme_grouped':        firme_grouped,
        'TIPURI_CONTRACT':      TIPURI_CONTRACT,
        'TIPURI_CONTRACT_DICT': TIPURI_CONTRACT_DICT,
        'TIP_FIRMA':            TIP_FIRMA,
        'TIP_FIRMA_DICT':       TIP_FIRMA_DICT,
        'TIP_FIRMA_DESC':       TIP_FIRMA_DESC,
        'firme_livrare':        firme_livrare,
        'livratori':            livratori,
        'lansate':              lansate,
        'felul_1':              felul_1,
        'felul_2':              felul_2,
        'salate_plan':          salate_plan,
        'sandwich_plan':        sandwich_plan,
        'firme_ghiseu':         firme_ghiseu,
        'rezervari':            rezervari,
        'total_rez':            total_rez,
        'raport':               raport,
        'toate_produse':        toate_produse,
        'CATEGORII':            CATEGORII,
        'CATEGORII_PRODUSE':    categorii_produse,
    })


@login_required
@require_POST
def firma_add(request):
    nume = request.POST.get('nume', '').strip()
    tip_contract = request.POST.get('tip_contract', 'pranz_cina')
    tip_firma    = request.POST.get('tip_firma', 'ghiseu')
    try:
        cant = int(request.POST.get('cantitate_default', 0) or 0)
    except ValueError:
        cant = 0

    if not nume:
        messages.error(request, 'Numele firmei este obligatoriu.')
    elif tip_firma not in TIP_FIRMA_VALIDE:
        messages.error(request, 'Tip firmă invalid.')
    else:
        Firma.objects.create(
            nume_firma=nume, tip_contract=tip_contract,
            tip_firma=tip_firma, cantitate_default=cant, activ=True,
        )
        messages.success(request, f'Firmă „{nume}" adăugată.')
    return redirect('/staff/manager/firme/?tab=gestiune')


@login_required
@require_POST
def firma_save(request, pk):
    firma = get_object_or_404(Firma, pk=pk)
    firma.nume_firma    = request.POST.get('nume', firma.nume_firma).strip()
    firma.tip_contract  = request.POST.get('tip_contract', firma.tip_contract)
    firma.tip_firma     = request.POST.get('tip_firma', firma.tip_firma)
    try:
        firma.cantitate_default = int(request.POST.get('cantitate_default', 0) or 0)
    except ValueError:
        pass
    firma.save()

    telefon = request.POST.get('telefon', '').strip()
    adresa  = request.POST.get('adresa', '').strip()
    if firma.client and (telefon or adresa):
        if telefon:
            firma.client.telefon = telefon
        if adresa:
            firma.client.adresa_principala = adresa
        firma.client.save()

    messages.success(request, f'Firma „{firma.nume_firma}" salvată.')
    return redirect('/staff/manager/firme/?tab=gestiune')


@login_required
@require_POST
def firma_toggle(request, pk):
    firma = get_object_or_404(Firma, pk=pk)
    firma.activ = not firma.activ
    firma.save()
    stare = 'activată' if firma.activ else 'dezactivată'
    messages.success(request, f'Firma „{firma.nume_firma}" {stare}.')
    return redirect('/staff/manager/firme/?tab=gestiune')


@login_required
@require_POST
def angajat_add(request, firma_pk):
    firma = get_object_or_404(Firma, pk=firma_pk)
    nume  = request.POST.get('nume', '').strip()
    if not nume:
        messages.error(request, 'Numele angajatului este obligatoriu.')
    else:
        AngajatFirma.objects.create(firma=firma, nume_angajat=nume, activ=True)
        _sync_rezervare(firma_pk)
        messages.success(request, f'Angajat „{nume}" adăugat. Rezervare actualizată.')
    return redirect('/staff/manager/firme/?tab=gestiune')


@login_required
@require_POST
def angajat_toggle(request, pk):
    angajat = get_object_or_404(AngajatFirma, pk=pk)
    angajat.activ = not angajat.activ
    angajat.save()
    _sync_rezervare(angajat.firma_id)
    return redirect('/staff/manager/firme/?tab=gestiune')


@login_required
@require_POST
def firme_lansare_salveaza(request):
    data_str  = request.POST.get('data', date.today().isoformat())
    firma_id  = request.POST.get('firma_id')
    tip       = request.POST.get('tip_livrare', 'livrare')
    livrator  = request.POST.get('livrator', 'INTERN')
    ora       = (request.POST.get('ora', '12:00') or '12:00')[:5]

    try:
        data_zi  = date.fromisoformat(data_str)
        firma    = get_object_or_404(Firma, pk=int(firma_id))
    except (ValueError, TypeError):
        messages.error(request, 'Date invalide.')
        return redirect(f'/staff/manager/firme/?tab=lansare&data={data_str}')

    items = []
    for key in request.POST:
        if key.startswith('qty_'):
            try:
                pid = int(key[4:])
                qty = int(request.POST[key])
                if qty > 0:
                    p = Produs.objects.get(pk=pid)
                    items.append({'nume': p.nume, 'qty': qty, 'pret': float(p.pret_standard or 0)})
            except (ValueError, Produs.DoesNotExist):
                pass

    if not items:
        messages.error(request, 'Niciun produs cu cantitate > 0.')
        return redirect(f'/staff/manager/firme/?tab=lansare&data={data_str}')

    client_id = _ensure_client_firma(firma)
    total     = sum(i['pret'] * i['qty'] for i in items)

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO comenzi
                (client_id, data_comanda, ora_livrare_estimata,
                 status, metoda_plata, total_plata, sofer, observatii, tip_comanda, created_at)
            VALUES (%s, %s, %s, 'nou', 'factura', %s, %s, %s, %s, NOW())
            RETURNING id
        """, [client_id, data_zi, ora, total, livrator, f'Contract: {firma.nume_firma}', tip])
        comanda_id = cur.fetchone()[0]
        for i in items:
            cur.execute("""
                INSERT INTO comenzi_linii
                    (comanda_id, nume_produs, cantitate, pret_unitar, tip_linie, status)
                VALUES (%s, %s, %s, %s, 'standard', 'nou')
            """, [comanda_id, i['nume'], i['qty'], i['pret']])

    messages.success(request, f'Comandă lansată pentru {firma.nume_firma}.')
    return redirect(f'/staff/manager/firme/?tab=lansare&data={data_str}')


@login_required
@require_POST
def firme_lansare_sterge(request, pk):
    data_str = request.POST.get('data', date.today().isoformat())
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE comenzi SET status = 'anulat' WHERE id = %s AND status != 'livrat'", [pk]
        )
    messages.success(request, 'Comandă anulată.')
    return redirect(f'/staff/manager/firme/?tab=lansare&data={data_str}')


@login_required
def firme_raport_export(request):
    data_str = request.GET.get('data', date.today().isoformat())
    try:
        data_zi = date.fromisoformat(data_str)
    except (TypeError, ValueError):
        data_zi = date.today()

    raport = _get_raport_serviri(data_zi)

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})

    hdr_fmt = wb.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center'})
    cell_fmt = wb.add_format({'border': 1})
    time_fmt = wb.add_format({'border': 1, 'align': 'center'})

    for firma_data in raport:
        ws_name = firma_data['nume_firma'][:31]
        ws = wb.add_worksheet(ws_name)
        ws.set_column(0, 0, 28)
        ws.set_column(1, 1, 40)
        ws.set_column(2, 2, 14)
        ws.set_column(3, 3, 10)

        ws.write(0, 0, f"{firma_data['nume_firma']} — {data_zi.strftime('%d.%m.%Y')}",
                 wb.add_format({'bold': True, 'font_size': 12}))

        for col, title in enumerate(['Angajat', 'Produse', 'Tip', 'Ora']):
            ws.write(2, col, title, hdr_fmt)

        for r_idx, ang in enumerate(firma_data['angajati'], 3):
            tip = 'La masă' if ang.get('tip_ridicare') == 'la_masa' else 'Pachet'
            ora_str = str(ang.get('ora_servire', '') or '')[:5]
            ws.write(r_idx, 0, ang.get('nume_angajat', ''), cell_fmt)
            ws.write(r_idx, 1, ang.get('produse', ''), cell_fmt)
            ws.write(r_idx, 2, tip, time_fmt)
            ws.write(r_idx, 3, ora_str, time_fmt)

    if not raport:
        ws = wb.add_worksheet('Fără date')
        ws.write(0, 0, f'Nu există serviri pentru {data_zi.strftime("%d.%m.%Y")}.')

    wb.close()
    output.seek(0)

    filename = f"Raport_Firme_{data_zi.strftime('%d_%m_%Y')}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_POST
def firme_rezervare_salveaza(request):
    firma_id = request.POST.get('firma_id')
    try:
        firma_id  = int(firma_id)
        cantitate = int(request.POST.get('cantitate', 0))
    except (ValueError, TypeError):
        messages.error(request, 'Date invalide.')
        return redirect('/staff/manager/firme/?tab=prezenta')

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO rezervari_firme (firma_id, data_rez, cantitate)
            VALUES (%s, %s, %s)
            ON CONFLICT (firma_id, data_rez) DO UPDATE SET cantitate = EXCLUDED.cantitate
        """, [firma_id, date.today(), cantitate])

    firma = get_object_or_404(Firma, pk=firma_id)
    messages.success(request, f'{firma.nume_firma} — {cantitate} porții confirmate.')
    return redirect('/staff/manager/firme/?tab=prezenta')


# ── Utilizatori ───────────────────────────────────────────────

import bcrypt as _bcrypt

ROL_CHOICES = [
    ('admin',     'Admin'),
    ('receptie',  'Recepție'),
    ('bucatarie', 'Bucătărie'),
    ('ghiseu',    'Ghișeu'),
    ('livrator',  'Livrator'),
]
ROL_DICT = dict(ROL_CHOICES)


@login_required
def utilizatori(request):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.id, u.username, u.rol, u.activ,
                   u.livrator_id, l.nume AS livrator_nume
            FROM utilizatori u
            LEFT JOIN livratori l ON l.id = u.livrator_id
            ORDER BY u.rol, u.username
        """)
        cols = [c[0] for c in cur.description]
        toti = [dict(zip(cols, r)) for r in cur.fetchall()]

    utilizatori_grouped = [
        (rol, label, [u for u in toti if u['rol'] == rol])
        for rol, label in ROL_CHOICES
    ]
    livratori = list(Livrator.objects.filter(activ=True).order_by('nume'))

    return render(request, 'admin_manager/utilizatori.html', {
        'utilizatori_grouped': utilizatori_grouped,
        'livratori':           livratori,
        'ROL_CHOICES':         ROL_CHOICES,
    })


@login_required
@require_POST
def utilizator_add(request):
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '').strip()
    rol      = request.POST.get('rol', 'receptie')
    liv_id   = request.POST.get('livrator_id') or None

    if not username or not password:
        messages.error(request, 'Username și parola sunt obligatorii.')
        return redirect('manager:utilizatori')

    pw_hash = _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    try:
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO utilizatori (username, password_hash, rol, livrator_id) VALUES (%s,%s,%s,%s)",
                [username, pw_hash, rol, liv_id]
            )
        messages.success(request, f'Utilizator „{username}" creat.')
    except Exception as e:
        if 'unique' in str(e).lower():
            messages.error(request, f'Username „{username}" există deja.')
        else:
            messages.error(request, f'Eroare: {e}')
    return redirect('manager:utilizatori')


@login_required
@require_POST
def utilizator_toggle(request, pk):
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE utilizatori SET activ = NOT activ WHERE id = %s RETURNING username, activ",
            [pk]
        )
        row = cur.fetchone()
    if row:
        stare = 'activat' if row[1] else 'dezactivat'
        messages.success(request, f'Utilizator „{row[0]}" {stare}.')
    return redirect('manager:utilizatori')


@login_required
@require_POST
def utilizator_reset_parola(request, pk):
    new_pass = request.POST.get('password', '').strip()
    if not new_pass:
        messages.error(request, 'Parola nouă nu poate fi goală.')
        return redirect('manager:utilizatori')
    pw_hash = _bcrypt.hashpw(new_pass.encode(), _bcrypt.gensalt()).decode()
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE utilizatori SET password_hash = %s WHERE id = %s RETURNING username",
            [pw_hash, pk]
        )
        row = cur.fetchone()
    if row:
        messages.success(request, f'Parolă resetată pentru „{row[0]}".')
    return redirect('manager:utilizatori')


@login_required
@require_POST
def utilizator_link_livrator(request, pk):
    liv_id = request.POST.get('livrator_id') or None
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE utilizatori SET livrator_id = %s WHERE id = %s",
            [liv_id, pk]
        )
    messages.success(request, 'Livrator actualizat.')
    return redirect('manager:utilizatori')


# ── Rapoarte ──────────────────────────────────────────────────

@login_required
def rapoarte(request):
    tab = request.GET.get('tab', 'comenzi')
    today = date.today()

    # interval date (comenzi / firme / livratori)
    default_start = today if tab == 'firme' else today.replace(day=1)
    try:
        data_start = date.fromisoformat(request.GET.get('start', ''))
    except (TypeError, ValueError):
        data_start = default_start
    try:
        data_end = date.fromisoformat(request.GET.get('end', ''))
    except (TypeError, ValueError):
        data_end = today

    # data singulară (productie)
    try:
        data_prod = date.fromisoformat(request.GET.get('data_prod', ''))
    except (TypeError, ValueError):
        data_prod = today

    comenzi_rows = []
    comenzi_totale = {}
    comenzi_detail = []
    productie_rows = []
    firme_rows = []
    firme_totale = {}
    livratori_rows = []
    pierderi_rows = []
    pierderi_totale = {}

    if tab == 'comenzi':
        FILTER_SQL = """
            (c.client_id != 999 AND c.client_id NOT IN (
                SELECT client_id FROM firme WHERE client_id IS NOT NULL
            ))
            OR (c.client_id = 999 AND c.tip_comanda = 'eveniment')
        """
        with connection.cursor() as cur:
            # Rezumat pe zile
            cur.execute(f"""
                SELECT c.data_comanda,
                       COUNT(*) FILTER (WHERE c.status != 'anulat')          AS nr,
                       COUNT(*) FILTER (WHERE c.status = 'anulat')           AS anulate,
                       COALESCE(SUM(c.total_plata)
                         FILTER (WHERE c.status != 'anulat'), 0)             AS total,
                       COUNT(*) FILTER (WHERE c.metoda_plata = 'cash'
                         AND c.status != 'anulat')                           AS cash,
                       COUNT(*) FILTER (WHERE c.metoda_plata = 'factura'
                         AND c.status != 'anulat')                           AS factura,
                       COUNT(*) FILTER (WHERE c.tip_comanda = 'eveniment'
                         AND c.status != 'anulat')                           AS evenimente
                FROM comenzi c
                WHERE c.data_comanda BETWEEN %s AND %s AND ({FILTER_SQL})
                GROUP BY c.data_comanda
                ORDER BY c.data_comanda DESC
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            comenzi_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Detaliu per comandă
            cur.execute(f"""
                SELECT c.id, c.data_comanda, cli.nume_client,
                       c.status, c.metoda_plata, c.tip_comanda,
                       COALESCE(c.sofer, '—')  AS sofer,
                       c.created_at, c.gatit_la, c.pregatit_la, c.pedrum_la, c.livrat_la,
                       COALESCE(c.total_plata, 0) AS total_plata,
                       c.observatii
                FROM comenzi c
                JOIN clienti cli ON cli.id = c.client_id
                WHERE c.data_comanda BETWEEN %s AND %s AND ({FILTER_SQL})
                ORDER BY c.data_comanda DESC, c.created_at, c.id
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            comenzi_detail = [dict(zip(cols, r)) for r in cur.fetchall()]

            if comenzi_detail:
                cmd_ids = [c['id'] for c in comenzi_detail]
                cur.execute("""
                    SELECT comanda_id, nume_produs, cantitate, status, gatit_la
                    FROM comenzi_linii
                    WHERE comanda_id = ANY(%s)
                    ORDER BY comanda_id, id
                """, [cmd_ids])
                linii_map = {}
                for r in cur.fetchall():
                    linii_map.setdefault(r[0], []).append({
                        'nume_produs': r[1], 'cantitate': r[2],
                        'status': r[3], 'gatit_la': r[4],
                    })
                for cmd in comenzi_detail:
                    cmd['linii'] = linii_map.get(cmd['id'], [])

        comenzi_totale = {
            'nr':     sum(r['nr']     for r in comenzi_rows),
            'anulate': sum(r['anulate'] for r in comenzi_rows),
            'total':  sum(r['total']  for r in comenzi_rows),
        }

    elif tab == 'productie':
        with connection.cursor() as cur:
            # Sursă 1: lot intern prânz + cină
            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.client_id = 999
                  AND c.tip_comanda IN ('pranz', 'cina')
                  AND c.status != 'anulat'
                GROUP BY cl.nume_produs
            """, [data_prod])
            lot_intern = {r[0]: r[1] for r in cur.fetchall()}

            # Sursă 2: lot eveniment / protocol
            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.client_id = 999
                  AND c.tip_comanda = 'eveniment'
                  AND c.status != 'anulat'
                GROUP BY cl.nume_produs
            """, [data_prod])
            lot_ev = {r[0]: r[1] for r in cur.fetchall()}

            # Sursă 3: firme cu meniu special (client_id este un client de firmă)
            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                JOIN firme f ON f.client_id = c.client_id
                WHERE c.data_comanda = %s AND c.status != 'anulat'
                GROUP BY cl.nume_produs
            """, [data_prod])
            lot_firme = {r[0]: r[1] for r in cur.fetchall()}

            # Sursă 4: comenzi recepție (clienți individuali)
            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.client_id != 999
                  AND c.status != 'anulat'
                  AND c.client_id NOT IN (
                      SELECT client_id FROM firme WHERE client_id IS NOT NULL
                  )
                GROUP BY cl.nume_produs
            """, [data_prod])
            lot_receptie = {r[0]: r[1] for r in cur.fetchall()}

            # Lansare la — prima apariție a produsului în orice sursă (lot intern, firme, recepție)
            cur.execute("""
                SELECT cl.nume_produs, MIN(c.created_at)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.status != 'anulat'
                GROUP BY cl.nume_produs
            """, [data_prod])
            lansare_la_map = {r[0]: r[1] for r in cur.fetchall()}

            # Gătit — toate sursele + timestamp când s-a terminat gătirea per produs
            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate), MAX(cl.gatit_la)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.status != 'anulat'
                  AND cl.status = 'gatit'
                GROUP BY cl.nume_produs
            """, [data_prod])
            gatite = {}
            gatit_la_map = {}
            for r in cur.fetchall():
                gatite[r[0]] = r[1]
                gatit_la_map[r[0]] = r[2]

            # Servit la masă (ghișeu, tip_ridicare='la_masa')
            cur.execute("""
                SELECT sgl.nume_produs, SUM(sgl.cantitate)
                FROM serviri_ghiseu_linii sgl
                JOIN serviri_ghiseu sg ON sg.id = sgl.servire_id
                WHERE sg.data_servire = %s AND sg.tip_ridicare = 'la_masa'
                GROUP BY sgl.nume_produs
            """, [data_prod])
            servit_masa = {r[0]: r[1] for r in cur.fetchall()}

            # Livrat — pachete ghișeu (tip_ridicare='pachet') + comenzi externe livrate
            cur.execute("""
                SELECT sgl.nume_produs, SUM(sgl.cantitate)
                FROM serviri_ghiseu_linii sgl
                JOIN serviri_ghiseu sg ON sg.id = sgl.servire_id
                WHERE sg.data_servire = %s AND sg.tip_ridicare = 'pachet'
                GROUP BY sgl.nume_produs
            """, [data_prod])
            servit_pachet = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("""
                SELECT cl.nume_produs, SUM(cl.cantitate)
                FROM comenzi_linii cl
                JOIN comenzi c ON c.id = cl.comanda_id
                WHERE c.data_comanda = %s AND c.client_id != 999
                  AND c.status = 'livrat'
                GROUP BY cl.nume_produs
            """, [data_prod])
            livrate = {r[0]: r[1] for r in cur.fetchall()}

            # Pierderi declarate de bucătărie (snapshot înghețat)
            cur.execute("""
                SELECT nume_produs, pierderi
                FROM stoc_nevandut
                WHERE data = %s
            """, [data_prod])
            pierderi_map = {r[0]: r[1] for r in cur.fetchall()}

        toate = sorted(set(
            list(lot_intern) + list(lot_ev) + list(lot_firme) + list(lot_receptie)
        ))
        productie_rows = []
        for p in toate:
            li = lot_intern.get(p, 0)
            le = lot_ev.get(p, 0)
            lf = lot_firme.get(p, 0)
            lr = lot_receptie.get(p, 0)
            g  = gatite.get(p, 0)
            ma = servit_masa.get(p, 0)
            lv = servit_pachet.get(p, 0) + livrate.get(p, 0)
            pi = pierderi_map.get(p, 0)
            productie_rows.append({
                'produs':       p,
                'lot_intern':   li,
                'lot_ev':       le,
                'lot_firme':    lf,
                'lot_receptie': lr,
                'total_lansat': li + le + lf + lr,
                'lansare_la':   lansare_la_map.get(p),
                'gatit':        g,
                'gatit_la':     gatit_la_map.get(p),
                'la_masa':      ma,
                'livrat':       lv,
                'pierderi':     pi,
                'ramas':        g - ma - lv - pi,
            })

    elif tab == 'firme':
        with connection.cursor() as cur:
            cur.execute("""
                SELECT
                    f.id,
                    f.nume_firma,
                    f.tip_firma,
                    COALESCE(gh.portii_ghiseu, 0)                        AS portii_ghiseu,
                    COALESCE(gh.portii_masa,   0)                        AS portii_masa,
                    COALESCE(gh.portii_pachet, 0)                        AS portii_pachet,
                    COALESCE(gh.total_ghiseu, 0)                         AS total_ghiseu,
                    COALESCE(lv.portii_livrare, 0)                       AS portii_livrare,
                    COALESCE(lv.comenzi_livrare, 0)                      AS comenzi_livrare,
                    COALESCE(lv.total_lei, 0)                            AS total_lei,
                    COALESCE(gh.total_ghiseu, 0) + COALESCE(lv.total_lei, 0) AS total_lei_combined,
                    COALESCE(rez.rezervate, 0)                           AS rezervate
                FROM firme f
                LEFT JOIN (
                    SELECT sg.firma_id,
                           COUNT(DISTINCT sg.id) AS portii_ghiseu,
                           COUNT(DISTINCT CASE WHEN sg.tip_ridicare = 'la_masa' THEN sg.id END) AS portii_masa,
                           COUNT(DISTINCT CASE WHEN sg.tip_ridicare = 'pachet'  THEN sg.id END) AS portii_pachet,
                           COALESCE(SUM(sgl.cantitate * COALESCE(p.pret_standard, 0)), 0) AS total_ghiseu
                    FROM serviri_ghiseu sg
                    JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
                    LEFT JOIN produse p ON p.nume = sgl.nume_produs
                    WHERE sg.data_servire BETWEEN %s AND %s
                      AND sg.tip_servire = 'firma'
                    GROUP BY sg.firma_id
                ) gh ON gh.firma_id = f.id
                LEFT JOIN (
                    SELECT f2.id AS firma_id,
                           COUNT(DISTINCT c.id) AS comenzi_livrare,
                           COALESCE(SUM(
                               (SELECT MAX(cl2.cantitate)
                                FROM comenzi_linii cl2
                                WHERE cl2.comanda_id = c.id)
                           ), 0) AS portii_livrare,
                           COALESCE(SUM(c.total_plata), 0) AS total_lei
                    FROM firme f2
                    JOIN comenzi c ON c.client_id = f2.client_id
                    WHERE c.data_comanda BETWEEN %s AND %s
                      AND c.status != 'anulat'
                    GROUP BY f2.id
                ) lv ON lv.firma_id = f.id
                LEFT JOIN (
                    SELECT firma_id, SUM(cantitate) AS rezervate
                    FROM rezervari_firme
                    WHERE data_rez BETWEEN %s AND %s
                    GROUP BY firma_id
                ) rez ON rez.firma_id = f.id
                WHERE gh.portii_ghiseu IS NOT NULL
                   OR lv.portii_livrare IS NOT NULL
                ORDER BY f.nume_firma
            """, [data_start, data_end, data_start, data_end, data_start, data_end])
            cols = [c[0] for c in cur.description]
            firme_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in firme_rows:
            r['tip_firma_label'] = TIP_FIRMA_DICT.get(r['tip_firma'], r['tip_firma'])
            r['portii_masa']   = r.get('portii_masa', 0) or 0
            r['portii_pachet'] = r.get('portii_pachet', 0) or 0
            r['total_portii']  = r['portii_ghiseu'] + r['portii_livrare']
        firme_totale = {
            'firme':          len(firme_rows),
            'portii_masa':    sum(r['portii_masa']        for r in firme_rows),
            'portii_pachet':  sum(r['portii_pachet']      for r in firme_rows),
            'portii_ghiseu':  sum(r['portii_ghiseu']      for r in firme_rows),
            'portii_livrare': sum(r['portii_livrare']     for r in firme_rows),
            'total_portii':   sum(r['total_portii']       for r in firme_rows),
            'total_lei':      sum(r['total_lei_combined'] for r in firme_rows),
        }

        # Detaliu ghișeu per firmă
        with connection.cursor() as cur:
            cur.execute("""
                SELECT sg.id, sg.data_servire, f.id AS firma_id,
                       COALESCE(ag.nume_angajat, '—') AS angajat,
                       sg.tip_ridicare,
                       sg.status_pachet,
                       sg.ora_servire,
                       STRING_AGG(sgl.nume_produs || ' x' || sgl.cantitate, ', '
                                  ORDER BY sgl.id) AS produse
                FROM serviri_ghiseu sg
                JOIN firme f ON f.id = sg.firma_id
                LEFT JOIN angajati_firme ag ON ag.id = sg.angajat_id
                JOIN serviri_ghiseu_linii sgl ON sgl.servire_id = sg.id
                WHERE sg.data_servire BETWEEN %s AND %s
                  AND sg.tip_servire = 'firma'
                GROUP BY sg.id, sg.data_servire, f.id, ag.nume_angajat,
                         sg.tip_ridicare, sg.status_pachet, sg.ora_servire
                ORDER BY f.id, sg.data_servire, sg.ora_servire
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            gh_detail_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Detaliu comenzi livrare per firmă
            cur.execute("""
                SELECT c.id, c.data_comanda, f.id AS firma_id,
                       c.status, COALESCE(c.sofer, '—') AS sofer,
                       c.created_at, c.gatit_la, c.pregatit_la, c.pedrum_la, c.livrat_la,
                       COALESCE(c.total_plata, 0) AS total_plata,
                       STRING_AGG(cl.nume_produs || ' x' || cl.cantitate, ', '
                                  ORDER BY cl.id) AS produse
                FROM comenzi c
                JOIN firme f ON f.client_id = c.client_id
                JOIN comenzi_linii cl ON cl.comanda_id = c.id
                WHERE c.data_comanda BETWEEN %s AND %s
                  AND c.status != 'anulat'
                GROUP BY c.id, c.data_comanda, f.id, c.status, c.sofer,
                         c.created_at, c.gatit_la, c.pregatit_la, c.pedrum_la, c.livrat_la, c.total_plata
                ORDER BY f.id, c.data_comanda, c.id
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            lv_detail_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

        # Grupăm detaliile per firma_id
        firme_detail = {}
        for r in gh_detail_rows:
            firme_detail.setdefault(r['firma_id'], {'ghiseu': [], 'livrare': []})['ghiseu'].append(r)
        for r in lv_detail_rows:
            firme_detail.setdefault(r['firma_id'], {'ghiseu': [], 'livrare': []})['livrare'].append(r)
        for r in firme_rows:
            r['detail'] = firme_detail.get(r['id'], {'ghiseu': [], 'livrare': []})

    elif tab == 'livratori':
        with connection.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(c.sofer, '— fără șofer —') AS sofer,
                       COUNT(*)                              AS comenzi,
                       COALESCE(SUM(c.total_plata), 0)      AS total
                FROM comenzi c
                WHERE c.data_comanda BETWEEN %s AND %s
                  AND c.status = 'livrat'
                  AND c.client_id != 999
                GROUP BY c.sofer
                ORDER BY comenzi DESC
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            livratori_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    elif tab == 'pierderi':
        with connection.cursor() as cur:
            cur.execute("""
                SELECT
                    sn.nume_produs,
                    COUNT(DISTINCT sn.data)          AS zile,
                    SUM(sn.pierderi)                 AS total_pierderi,
                    SUM(sn.cantitate)                AS total_nevandut,
                    SUM(sn.pierderi + sn.cantitate)  AS total_risipa,
                    ROUND(AVG(NULLIF(sn.pierderi,0)),1) AS medie_pierderi_zi,
                    MAX(sn.declarat_la)              AS ultima_declaratie
                FROM stoc_nevandut sn
                WHERE sn.data BETWEEN %s AND %s
                  AND (sn.pierderi > 0 OR sn.cantitate > 0)
                GROUP BY sn.nume_produs
                ORDER BY total_risipa DESC
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            pierderi_rows = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Detaliu pe zile per produs (pentru drill-down)
            cur.execute("""
                SELECT data, nume_produs, cantitate, pierderi, declarat_la
                FROM stoc_nevandut
                WHERE data BETWEEN %s AND %s
                  AND (pierderi > 0 OR cantitate > 0)
                ORDER BY data DESC, nume_produs
            """, [data_start, data_end])
            cols = [c[0] for c in cur.description]
            pierderi_detaliu = [dict(zip(cols, r)) for r in cur.fetchall()]

            # Grupăm detaliul per produs
            det_map = {}
            for r in pierderi_detaliu:
                det_map.setdefault(r['nume_produs'], []).append(r)
            for r in pierderi_rows:
                r['detaliu'] = det_map.get(r['nume_produs'], [])

        pierderi_totale = {
            'produse':       len(pierderi_rows),
            'total_pierderi': sum(r['total_pierderi'] for r in pierderi_rows),
            'total_nevandut': sum(r['total_nevandut'] for r in pierderi_rows),
            'total_risipa':   sum(r['total_risipa']   for r in pierderi_rows),
        }

    return render(request, 'admin_manager/rapoarte.html', {
        'tab':             tab,
        'data_start':      data_start,
        'data_end':        data_end,
        'data_prod':       data_prod,
        'comenzi_rows':    comenzi_rows,
        'comenzi_totale':  comenzi_totale,
        'comenzi_detail':  comenzi_detail,
        'productie_rows':  productie_rows,
        'firme_rows':      firme_rows,
        'firme_totale':    firme_totale,
        'livratori_rows':  livratori_rows,
        'pierderi_rows':   pierderi_rows,
        'pierderi_totale': pierderi_totale,
        'TIP_FIRMA_DICT':  TIP_FIRMA_DICT,
    })


# ─────────────────────────────────────────────────────────────
#  REȚETE & INGREDIENTE
# ─────────────────────────────────────────────────────────────

@login_required
def ingrediente(request):
    """Catalog ingrediente."""
    toate = Ingredient.objects.all().order_by('categorie', 'nume')
    grouped = {}
    for ing in toate:
        cat = ing.get_categorie_display() if ing.categorie else 'Fără categorie'
        grouped.setdefault(cat, []).append(ing)
    return render(request, 'admin_manager/ingrediente.html', {
        'grouped':   grouped,
        'unitate_choices':   Ingredient.UNITATE_CHOICES,
        'categorie_choices': Ingredient.CATEGORIE_CHOICES,
    })


@login_required
@require_POST
def ingredient_add(request):
    nume      = request.POST.get('nume', '').strip()
    unitate   = request.POST.get('unitate', 'kg').strip()
    categorie = request.POST.get('categorie', '').strip() or None
    if not nume:
        messages.error(request, 'Numele ingredientului este obligatoriu.')
        return redirect('manager:ingrediente')
    obj, created = Ingredient.objects.get_or_create(
        nume=nume,
        defaults={'unitate': unitate, 'categorie': categorie},
    )
    if created:
        messages.success(request, f'Ingredient „{nume}" adăugat în catalog.')
    else:
        messages.warning(request, f'Ingredientul „{nume}" există deja în catalog.')
    next_url = request.POST.get('next', '').strip()
    return redirect(next_url if next_url else 'manager:ingrediente')


@login_required
def produs_reteta(request, pk):
    """Pagina de gestiune rețetă per produs."""
    produs = get_object_or_404(Produs, pk=pk)
    linii  = (RetetaLinie.objects
              .filter(produs=produs)
              .select_related('ingredient')
              .order_by('ingredient__categorie', 'ingredient__nume'))

    # Grupează ingredientele pe categorie pentru selector
    toate_ing = Ingredient.objects.all().order_by('categorie', 'nume')
    ing_grouped = {}
    for ing in toate_ing:
        ing_grouped.setdefault(ing.categorie or 'DIVERSE', []).append(ing)

    # JSON pentru filtrare JS (categorie → lista ingrediente)
    import json
    ing_json = {
        cat: [{'id': i.pk, 'nume': i.nume, 'unitate': i.unitate} for i in lista]
        for cat, lista in ing_grouped.items()
    }

    return render(request, 'admin_manager/produs_reteta.html', {
        'produs':             produs,
        'linii':              linii,
        'ing_grouped':        ing_grouped,
        'ing_json':           json.dumps(ing_json, ensure_ascii=False),
        'categorie_choices':  Ingredient.CATEGORIE_CHOICES,
        'unitate_choices':    Ingredient.UNITATE_CHOICES,
    })


@login_required
@require_POST
def reteta_linie_add(request, pk):
    """Adaugă o linie în rețeta unui produs. Poate crea ingredient nou pe loc."""
    produs = get_object_or_404(Produs, pk=pk)

    # Ingredient nou inline sau din catalog
    ing_id   = request.POST.get('ingredient_id', '').strip()
    ing_nou  = request.POST.get('ingredient_nou', '').strip()
    unitate  = request.POST.get('unitate_nou', 'kg').strip()
    categorie = request.POST.get('categorie_nou', '').strip() or None

    try:
        cantitate_raw = float(request.POST.get('cantitate', '0').replace(',', '.'))
    except (ValueError, TypeError):
        cantitate_raw = 0

    if cantitate_raw <= 0:
        messages.error(request, 'Cantitatea trebuie să fie > 0.')
        return redirect('manager:produs_reteta', pk=pk)

    if ing_nou:
        ingredient, _ = Ingredient.objects.get_or_create(
            nume=ing_nou,
            defaults={'unitate': unitate, 'categorie': categorie},
        )
    elif ing_id:
        ingredient = get_object_or_404(Ingredient, pk=ing_id)
    else:
        messages.error(request, 'Selectează sau creează un ingredient.')
        return redirect('manager:produs_reteta', pk=pk)

    # Conversie automată: utilizatorul introduce în g/ml, salvăm în kg/l
    if ingredient.unitate == 'kg':
        cantitate = cantitate_raw / 1000
    elif ingredient.unitate == 'l':
        cantitate = cantitate_raw / 1000
    else:
        cantitate = cantitate_raw  # buc, g, ml native — fără conversie

    RetetaLinie.objects.update_or_create(
        produs=produs,
        ingredient=ingredient,
        defaults={'cantitate': cantitate},
    )
    messages.success(request, f'„{ingredient.nume}" adăugat în rețetă.')
    return redirect('manager:produs_reteta', pk=pk)


@login_required
@require_POST
def reteta_linie_delete(request, pk):
    """Șterge o linie din rețetă."""
    linie = get_object_or_404(RetetaLinie, pk=pk)
    produs_pk = linie.produs_id
    linie.delete()
    return redirect('manager:produs_reteta', pk=produs_pk)
