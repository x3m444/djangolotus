import io

import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import Comanda, Livrator, Utilizator

FURNIZOR = {
    'denumire': 'LOTUS GRIGCONS SRL',
    'reg_com':  'J2013000122364',
    'cif':      '31417980',
    'sediu':    'Str. Ing. Dumitru Ivanov 16, Bl. P3, Sc. A, Tulcea',
    'judet':    'Tulcea',
}


def _get_livrator(request):
    try:
        util = Utilizator.objects.get(username=request.user.username)
        if util.livrator_id:
            return Livrator.objects.get(pk=util.livrator_id)
    except (Utilizator.DoesNotExist, Livrator.DoesNotExist):
        pass
    return None


@login_required
def index(request):
    azi = timezone.localdate()
    livrator = _get_livrator(request)

    # Admin poate previzualiza orice livrator via ?sofer=Nume
    if not livrator and request.user.is_staff:
        sofer_preview = request.GET.get('sofer', '').strip()
        if sofer_preview:
            try:
                livrator = Livrator.objects.get(nume=sofer_preview)
            except Livrator.DoesNotExist:
                pass

    if livrator:
        comenzi_qs = (
            Comanda.objects
            .exclude(client_id=999)
            .filter(data_comanda=azi, sofer=livrator.nume)
            .select_related('client')
            .prefetch_related('linii')
            .order_by('ora_livrare_estimata', 'id')
        )
        toate = list(comenzi_qs)
        de_preluat = [c for c in toate if c.status == 'pregatit']
        pe_drum    = [c for c in toate if c.status == 'pedrum']
        livrate    = [c for c in toate if c.status == 'livrat']

        cash_total = sum(
            c.total_plata for c in de_preluat + pe_drum
            if c.metoda_plata == 'cash' and c.total_plata
        )
        sumar = {
            'de_preluat': len(de_preluat),
            'pe_drum':    len(pe_drum),
            'livrate':    len(livrate),
            'cash_total': cash_total,
        }
    else:
        de_preluat = pe_drum = livrate = []
        sumar = {'de_preluat': 0, 'pe_drum': 0, 'livrate': 0, 'cash_total': 0}

    return render(request, 'livrare/index.html', {
        'azi':        azi,
        'livrator':   livrator,
        'de_preluat': de_preluat,
        'pe_drum':    pe_drum,
        'livrate':    livrate,
        'sumar':      sumar,
    })


def _back(request):
    return request.META.get('HTTP_REFERER') or redirect('livrare:index')


@login_required
@require_POST
def pedrum(request, pk):
    comanda = get_object_or_404(Comanda.objects.exclude(client_id=999), pk=pk)
    if comanda.status not in ('nou', 'pregatit'):
        messages.warning(request, f'Comanda #{pk} nu poate fi marcată "pe drum".')
    else:
        now = timezone.now()
        comanda.status = 'pedrum'
        if not comanda.pedrum_la:
            comanda.pedrum_la = now
        comanda.save(update_fields=['status', 'pedrum_la'])
    return redirect(_back(request))


@login_required
@require_POST
def livrat(request, pk):
    comanda = get_object_or_404(Comanda.objects.exclude(client_id=999), pk=pk)
    if comanda.status == 'anulat':
        messages.warning(request, f'Comanda #{pk} este anulată.')
    else:
        now = timezone.now()
        comanda.status = 'livrat'
        if not comanda.livrat_la:
            comanda.livrat_la = now
        comanda.save(update_fields=['status', 'livrat_la'])
    return redirect(_back(request))


@login_required
@require_POST
def problema(request, pk):
    comanda = get_object_or_404(Comanda.objects.exclude(client_id=999), pk=pk)
    obs = request.POST.get('observatii', '').strip()
    nota = f'[Problemă livrare] {obs}' if obs else '[Problemă livrare]'
    comanda.observatii = f'{comanda.observatii or ""}\n{nota}'.strip()
    comanda.status = 'nou'
    comanda.save(update_fields=['status', 'observatii'])
    messages.warning(request, f'Comanda #{pk} — problemă raportată.')
    return redirect(_back(request))


@login_required
def aviz(request, pk):
    comanda = get_object_or_404(
        Comanda.objects.exclude(client_id=999).select_related('client').prefetch_related('linii'),
        pk=pk,
    )
    livrator = _get_livrator(request)
    sofer = livrator.nume if livrator else (comanda.sofer or '—')
    data = comanda.data_comanda

    produse = [
        {'nume': l.nume_produs, 'cantitate': l.cantitate, 'pret': float(l.pret_unitar or 0)}
        for l in comanda.linii.all()
    ]

    output = _genereaza_aviz(comanda, sofer, data, produse)

    filename = f"Aviz_{pk}_{data.strftime('%d%m%Y')}.xlsx"
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _genereaza_aviz(comanda, sofer, data, produse, tva_pct=11.0):
    FONT     = 'Segoe UI'
    coef     = tva_pct / 100.0
    data_str = data.strftime('%d.%m.%Y')
    data_gen = timezone.localtime().strftime('%d.%m.%Y %H:%M')
    nr_aviz  = f'AVZ-{comanda.pk:06d}'
    COL_W    = [5, 34, 8, 10, 16, 14, 14]
    NC       = len(COL_W)

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = wb.add_worksheet('Aviz')

    ws.set_landscape()
    ws.set_margins(0.5, 0.5, 0.5, 0.5)
    ws.set_print_scale(95)
    ws.center_horizontally()
    ws.repeat_rows(0, 8)
    for ci, w in enumerate(COL_W):
        ws.set_column(ci, ci, w)

    def fmt(**kw):
        base = {'font_name': FONT, 'font_size': 9}
        base.update(kw)
        return wb.add_format(base)

    f_bloc_hdr  = fmt(bold=True, fg_color='#E0E0E0', border=1, border_color='#999999', valign='vcenter')
    f_bloc_line = fmt(border=1, border_color='#CCCCCC', valign='vcenter', text_wrap=True)
    f_titlu     = fmt(font_size=14, bold=True, align='center', valign='vcenter')
    f_nr_lbl    = fmt(bold=True, align='right', valign='vcenter', border=1, border_color='#999999')
    f_nr_val    = fmt(valign='vcenter', border=1, border_color='#999999')
    f_col_hdr   = fmt(bold=True, fg_color='#3D3D3D', font_color='white',
                      align='center', valign='vcenter', border=1, border_color='#1A1A1A', text_wrap=True)
    f_cell      = fmt(border=1, border_color='#AAAAAA', valign='vcenter')
    f_cell_alt  = fmt(fg_color='#F0F0F0', border=1, border_color='#AAAAAA', valign='vcenter')
    f_num       = fmt(border=1, border_color='#AAAAAA', valign='vcenter', align='right', num_format='#,##0.00')
    f_num_alt   = fmt(fg_color='#F0F0F0', border=1, border_color='#AAAAAA', valign='vcenter',
                      align='right', num_format='#,##0.00')
    f_tot_lbl   = fmt(font_size=10, bold=True, fg_color='#D5D8DC', border=1, border_color='#3D3D3D',
                      align='center', valign='vcenter')
    f_tot_num   = fmt(font_size=10, bold=True, fg_color='#D5D8DC', border=1, border_color='#3D3D3D',
                      valign='vcenter', align='right', num_format='#,##0.00')
    f_sig       = fmt(bold=True, valign='vcenter')
    f_mentiune  = fmt(italic=True, valign='vcenter')
    f_footer    = fmt(font_size=7, italic=True, font_color='#888888',
                      align='center', valign='vcenter', fg_color='#F5F5F5')

    # Blocuri Furnizor / Cumpărător (rânduri 0–5)
    def write_bloc(col_s, col_e, titlu, linii):
        ws.set_row(0, 15)
        ws.merge_range(0, col_s, 0, col_e, titlu, f_bloc_hdr)
        for i, linie in enumerate(linii):
            ws.set_row(i + 1, 13)
            ws.merge_range(i + 1, col_s, i + 1, col_e, linie, f_bloc_line)

    client = comanda.client
    write_bloc(0, 2, 'FURNIZOR', [
        f"Denumire: {FURNIZOR['denumire']}",
        f"Nr. înmatriculare Reg. Com.: {FURNIZOR['reg_com']}",
        f"Cod identificare fiscală: {FURNIZOR['cif']}",
        f"Sediul: {FURNIZOR['sediu']}",
        f"Județul: {FURNIZOR['judet']}",
    ])
    write_bloc(3, 6, 'CUMPĂRĂTOR', [
        f"Denumire: {client.nume_client}",
        'Nr. înmatriculare Reg. Com.: —',
        'Cod identificare fiscală: —',
        f"Sediul: {client.adresa_principala or '—'}",
        f"Telefon: {client.telefon or '—'}",
    ])

    # Titlu + Nr/Data (rânduri 6–7)
    ws.set_row(6, 26)
    ws.merge_range(6, 0, 6, NC - 1, 'AVIZ DE ÎNSOȚIRE A MĂRFII', f_titlu)
    ws.set_row(7, 18)
    ws.merge_range(7, 0, 7, 1, 'Nr.',                         f_nr_lbl)
    ws.merge_range(7, 2, 7, 3, nr_aviz,                       f_nr_val)
    ws.merge_range(7, 4, 7, 5, 'Data (ziua, luna, anul):',    f_nr_lbl)
    ws.write      (7, 6,        data_str,                      f_nr_val)

    # Header tabel (rând 8–9)
    ws.set_row(8, 30)
    for ci, h in enumerate([
        'Nr.\ncrt.', 'Denumirea produselor,\nambalajelor etc.',
        'U.M.', 'Cantitatea',
        f'Prețul unitar\n(fără T.V.A.)\n— lei —',
        f'Valoarea\n— lei —\n(col.3 × col.4)',
        f'Valoarea\nT.V.A.\n— lei —',
    ]):
        ws.write(8, ci, h, f_col_hdr)
    ws.set_row(9, 12)
    for ci in range(NC):
        ws.write(9, ci, str(ci), f_col_hdr)

    # Rânduri produse
    DATA_R = 10
    total_fara_tva = total_tva = 0.0
    for ri, p in enumerate(produse or []):
        alt       = ri % 2 == 1
        fc, fn    = (f_cell_alt, f_num_alt) if alt else (f_cell, f_num)
        pret_cu   = float(p.get('pret', 0))
        cant      = float(p.get('cantitate', 1))
        pret_fara = pret_cu / (1 + coef)
        val_fara  = cant * pret_fara
        val_tva   = cant * pret_cu - val_fara
        total_fara_tva += val_fara
        total_tva      += val_tva
        ws.set_row(DATA_R + ri, 16)
        ws.write(DATA_R + ri, 0, ri + 1,                fc)
        ws.write(DATA_R + ri, 1, p.get('nume', ''),     fc)
        ws.write(DATA_R + ri, 2, 'porție',              fc)
        ws.write(DATA_R + ri, 3, int(cant),             fn)
        ws.write(DATA_R + ri, 4, pret_fara,             fn)
        ws.write(DATA_R + ri, 5, val_fara,              fn)
        ws.write(DATA_R + ri, 6, val_tva,               fn)

    # Total
    TR = DATA_R + len(produse or [])
    ws.set_row(TR,     18)
    ws.set_row(TR + 1, 18)
    ws.merge_range(TR,     0, TR,     4, 'TOTAL (col. 5 + col. 6)',           f_tot_lbl)
    ws.write      (TR,     5, total_fara_tva,                                 f_tot_num)
    ws.write      (TR,     6, total_tva,                                      f_tot_num)
    ws.merge_range(TR + 1, 0, TR + 1, 4, f'TOTAL CU T.V.A. {tva_pct:.0f}%', f_tot_lbl)
    ws.merge_range(TR + 1, 5, TR + 1, 6, total_fara_tva + total_tva,         f_tot_num)

    # Semnături
    SIG = TR + 3
    ws.set_row(TR + 2, 8)
    ws.set_row(SIG,     14)
    ws.set_row(SIG + 1, 36)
    ws.set_row(SIG + 2, 36)
    ws.merge_range(SIG,     0, SIG,     NC - 1,
                   'Fără factură  □     Urmează factura nr. _____________  □', f_mentiune)
    ws.merge_range(SIG + 1, 0, SIG + 1, 2,
                   'Semnătură expeditor și ștampilă:\n____________________', f_sig)
    ws.merge_range(SIG + 1, 3, SIG + 1, 4,
                   f'Delegat (șofer): {sofer}\nAuto: ___________', f_sig)
    ws.merge_range(SIG + 1, 5, SIG + 1, NC - 1,
                   'Semnătură primitor:\n____________________', f_sig)

    # Footer
    FR = SIG + 3
    ws.set_row(FR, 14)
    ws.merge_range(FR, 0, FR, NC - 1,
                   f"LOTUS GRIGCONS SRL  •  CIF 31417980  •  J2013000122364  •  "
                   f"Str. Ing. Dumitru Ivanov 16, Tulcea  •  Generat: {data_gen}",
                   f_footer)

    wb.close()
    output.seek(0)
    return output.read()
