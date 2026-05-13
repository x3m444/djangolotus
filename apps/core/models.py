from django.db import models


class Produs(models.Model):
    nume = models.CharField(max_length=200)
    categorie = models.CharField(max_length=50)
    pret_standard = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'produse'

    @property
    def categorie_display(self):
        return self.categorie.replace('_', ' ').title()

    def __str__(self):
        return self.nume


class Livrator(models.Model):
    nume = models.CharField(max_length=100)
    activ = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'livratori'

    def __str__(self):
        return self.nume


class PlanificareZi(models.Model):
    data_zi = models.DateField()
    produs = models.ForeignKey(Produs, on_delete=models.CASCADE, db_column='produs_id')
    tip_plan = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'planificare_meniu'


class Client(models.Model):
    nume_client = models.CharField(max_length=200)
    telefon = models.CharField(max_length=20, unique=True)
    adresa_principala = models.TextField(null=True, blank=True)
    observatii_client = models.TextField(null=True, blank=True)
    puncte_fidelitate = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = 'clienti'

    def __str__(self):
        return f"{self.nume_client} | {self.telefon}"


class Firma(models.Model):
    nume_firma = models.CharField(max_length=200)
    tip_contract = models.CharField(max_length=50)
    activ = models.BooleanField(default=True)
    tip_firma = models.CharField(max_length=50)
    cantitate_default = models.IntegerField(null=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, db_column='client_id')

    class Meta:
        managed = False
        db_table = 'firme'

    def __str__(self):
        return self.nume_firma


class AngajatFirma(models.Model):
    firma = models.ForeignKey(Firma, on_delete=models.CASCADE, related_name='angajati', db_column='firma_id')
    nume_angajat = models.CharField(max_length=200)
    activ = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = 'angajati_firme'

    def __str__(self):
        return self.nume_angajat


class RezervareFirema(models.Model):
    firma = models.ForeignKey(Firma, on_delete=models.CASCADE, db_column='firma_id')
    data_rez = models.DateField()
    cantitate = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'rezervari_firme'


class Comanda(models.Model):
    STATUS_CHOICES = [
        ('nou', 'Nou'),
        ('pregatit', 'Pregătit'),
        ('pedrum', 'Pe drum'),
        ('livrat', 'Livrat'),
        ('anulat', 'Anulat'),
    ]
    TIP_CHOICES = [
        ('livrare',   'Livrare'),
        ('pranz',     'Prânz'),
        ('cina',      'Cină'),
        ('special',   'Special'),
        ('eveniment', 'Eveniment'),
        ('sandwich',  'Sandwich'),
    ]
    PLATA_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('factura', 'Factură'),
        ('cantina', 'Cantină'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_column='client_id')
    data_comanda = models.DateField()
    ora_livrare_estimata = models.TimeField(default='12:00')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='nou')
    metoda_plata = models.CharField(max_length=20, choices=PLATA_CHOICES, null=True, blank=True)
    total_plata = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sofer = models.CharField(max_length=100, null=True, blank=True)
    observatii = models.TextField(null=True, blank=True)
    detalii_comanda = models.TextField(null=True, blank=True)
    tip_comanda = models.CharField(max_length=20, choices=TIP_CHOICES, default='pranz')
    tip_ridicare = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    gatit_la = models.DateTimeField(null=True, blank=True)
    pregatit_la = models.DateTimeField(null=True, blank=True)
    pedrum_la = models.DateTimeField(null=True, blank=True)
    livrat_la = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'comenzi'
        ordering = ['-data_comanda', '-id']

    def __str__(self):
        return f"#{self.id} {self.client} — {self.status}"


class ComandaLinie(models.Model):
    STATUS_CHOICES = [('nou', 'Nou'), ('gatit', 'Gătit')]
    TIP_CHOICES = [('standard', 'Standard'), ('special', 'Special')]

    comanda = models.ForeignKey(Comanda, on_delete=models.CASCADE, related_name='linii', db_column='comanda_id')
    nume_produs = models.CharField(max_length=200)
    cantitate = models.IntegerField(default=1)
    pret_unitar = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='nou')
    tip_linie = models.CharField(max_length=20, choices=TIP_CHOICES, default='standard')
    gatit_la = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'comenzi_linii'


class ServireGhiseu(models.Model):
    TIP_CHOICES = [('bon_casa', 'Bon casă'), ('firma', 'Firmă'), ('eveniment', 'Eveniment')]
    STATUS_PACHET = [('astept', 'Așteaptă'), ('ambalat', 'Ambalat'), ('ridicat', 'Ridicat')]

    data_servire = models.DateField()
    ora_servire = models.TimeField(null=True, blank=True)
    tip_servire = models.CharField(max_length=20, choices=TIP_CHOICES)
    firma = models.ForeignKey(Firma, on_delete=models.SET_NULL, null=True, blank=True, db_column='firma_id')
    angajat = models.ForeignKey(AngajatFirma, on_delete=models.SET_NULL, null=True, blank=True, db_column='angajat_id')
    comanda_ref = models.ForeignKey(Comanda, on_delete=models.SET_NULL, null=True, blank=True, db_column='comanda_ref_id')
    tip_ridicare = models.CharField(max_length=20, null=True, blank=True)
    status_pachet = models.CharField(max_length=20, choices=STATUS_PACHET, null=True, blank=True)
    din_buffer = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'serviri_ghiseu'


class ServireGhiseuLinie(models.Model):
    servire = models.ForeignKey(ServireGhiseu, on_delete=models.CASCADE, related_name='linii', db_column='servire_id')
    nume_produs = models.CharField(max_length=200)
    cantitate = models.IntegerField(default=1)
    din_nevandut = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = 'serviri_ghiseu_linii'


class StocNevandut(models.Model):
    data = models.DateField()
    nume_produs = models.CharField(max_length=200)
    cantitate = models.IntegerField(default=0)
    cantitate_servita = models.IntegerField(default=0)
    pierderi = models.IntegerField(default=0)
    declarat_la = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'stoc_nevandut'


class BufferAmbalare(models.Model):
    # Composite PK (data_zi, tip_meniu) — no id column in DB; use raw SQL for writes
    data_zi = models.DateField(primary_key=True)
    tip_meniu = models.CharField(max_length=30)
    cantitate = models.IntegerField(default=0)
    distribuit = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = 'buffer_ambalare'
        unique_together = [('data_zi', 'tip_meniu')]


class BufferComponente(models.Model):
    COMPONENTA_CHOICES = [
        ('f1',   'Felul 1'),
        ('f2v1', 'Felul 2 (v.1)'),
        ('f2v2', 'Felul 2 (v.2)'),
        ('sal',  'Salată'),
    ]
    TIP_SERVIRE_CHOICES = [
        ('masa',   'La masă'),
        ('pachet', 'La pachet'),
    ]

    data_zi     = models.DateField()
    componenta  = models.CharField(max_length=20, choices=COMPONENTA_CHOICES)
    tip_servire = models.CharField(max_length=10, choices=TIP_SERVIRE_CHOICES)
    cantitate   = models.IntegerField(default=0)
    distribuit  = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = 'buffer_componente'
        unique_together = [('data_zi', 'componenta', 'tip_servire')]

    @property
    def disponibil(self):
        return max(self.cantitate - self.distribuit, 0)


class Ingredient(models.Model):
    UNITATE_CHOICES = [
        ('kg',  'kg'),
        ('g',   'g'),
        ('l',   'l'),
        ('ml',  'ml'),
        ('buc', 'buc'),
    ]
    CATEGORIE_CHOICES = [
        ('CARNE SI AFUMATURI',    'Carne și Afumături'),
        ('LEGUME SI LEGUMINOASE', 'Legume și Leguminoase'),
        ('VERDETURI',             'Verdețuri'),
        ('LACTATE SI OUA',        'Lactate și Ouă'),
        ('BACANIE',               'Băcănie'),
        ('CONDIMENTE SI ACREALA', 'Condimente și Acreală'),
        ('ULEIURI SI GRASIMI',    'Uleiuri și Grăsimi'),
        ('FRUCTE',                'Fructe'),
        ('CONGELATE',             'Produse Congelate'),
        ('DIVERSE',               'Diverse'),
    ]

    nume      = models.CharField(max_length=200, unique=True)
    unitate   = models.CharField(max_length=20, choices=UNITATE_CHOICES, default='kg')
    categorie = models.CharField(max_length=50, choices=CATEGORIE_CHOICES, null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'ingrediente'
        ordering = ['categorie', 'nume']

    def __str__(self):
        return f"{self.nume} ({self.unitate})"


class RetetaLinie(models.Model):
    produs     = models.ForeignKey('Produs', on_delete=models.CASCADE,
                                   related_name='reteta', db_column='produs_id')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE,
                                   related_name='retete', db_column='ingredient_id')
    cantitate  = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        managed = False
        db_table = 'reteta_linii'
        unique_together = [('produs', 'ingredient')]

    def __str__(self):
        return f"{self.cantitate} {self.ingredient.unitate} {self.ingredient.nume}"


class NecesarZi(models.Model):
    data_zi            = models.DateField()
    ingredient         = models.ForeignKey(Ingredient, on_delete=models.CASCADE,
                                           db_column='ingredient_id')
    cantitate_necesara = models.DecimalField(max_digits=10, decimal_places=4)
    primit             = models.BooleanField(default=False)
    primit_la          = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'necesar_zi'
        unique_together = [('data_zi', 'ingredient')]

class Utilizator(models.Model):
    ROL_CHOICES = [
        ('admin', 'Admin'),
        ('receptie', 'Recepție'),
        ('bucatarie', 'Bucătărie'),
        ('ghiseu', 'Ghișeu'),
        ('livrator', 'Livrator'),
    ]

    username = models.CharField(max_length=100, unique=True)
    password_hash = models.CharField(max_length=200)
    rol = models.CharField(max_length=20, choices=ROL_CHOICES)
    activ = models.BooleanField(default=True)
    livrator = models.ForeignKey(Livrator, on_delete=models.SET_NULL, null=True, blank=True, db_column='livrator_id')

    class Meta:
        managed = False
        db_table = 'utilizatori'

    def __str__(self):
        return f"{self.username} ({self.rol})"
