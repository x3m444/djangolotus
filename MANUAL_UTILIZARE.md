# Manual de Utilizare — Cantina Lotus (Django)

> Aplicație web de gestiune cantină: planificare meniu, lansare producție, comenzi clienți,
> buffer pre-ambalare, servire ghișeu și livrări cu aviz de însoțire.

---

## Cuprins

1. [Flux general al aplicației](#1-flux-general)
2. [Autentificare și roluri](#2-autentificare-și-roluri)
3. [Admin — Planificare și gestiune](#3-admin)
4. [Recepție — Preluare comenzi livrare](#4-recepție)
5. [Bucătărie — Producție, buffer și ambalare](#5-bucătărie)
6. [Ghișeu — Servire directă](#6-ghișeu)
7. [Livrator — Distribuție comenzi](#7-livrator)
8. [Stoc — cum se calculează](#8-stoc)
9. [Scenarii complete pas cu pas](#9-scenarii-complete)

---

## 1. Flux general

```
ADMIN
  └─ Planifică meniu săptămânal (produse per zi)
  └─ Lansează loturi de producție (cantități per lot: prânz / cină / eveniment)
  └─ Lansează comenzi pentru firmele cu contract

RECEPȚIE
  └─ Preia comenzi livrare de la clienți individuali
  └─ Selectează livrator + oră + metodă plată

BUCĂTĂRIE
  └─ Tab Gătire: vede tot ce trebuie gătit azi și marchează ✅ Gata
  └─ Tab Buffer: pre-ambalează porții pentru ghișeu (masă și pachet)
  └─ Tab Împachetare: ambalează comenzile recepției + pachete firme + loturi eveniment
  └─ Tab Stoc Nevândut: declară ce a rămas la finalul zilei
  └─ Tab Necesar: lista ingredientelor necesare (export Excel)

GHIȘEU
  └─ Tab Bon Casă: servire clienți direct, din buffer
  └─ Tab Firme: servire nominală angajați cu contract
  └─ Tab Special: comenzi speciale trimise la bucătărie (ex: cozonac la pachet)
  └─ Tab Raport: situația zilei

LIVRATOR
  └─ Vede comenzile ambalate alocate lui
  └─ Marchează „Pe drum" și „Livrat"
  └─ Generează aviz de însoțire (Excel)
  └─ Raportează probleme la livrare
```

---

## 2. Autentificare și roluri

Aplicația este disponibilă la adresa **`https://lotus.incercari.duckdns.org`**.

Accesul necesită autentificare cu **username + parolă**. Nu există selecție manuală de rol.
Fiecare utilizator are un singur rol; meniurile și paginile accesibile se adaptează automat.

| Rol | Acces |
|-----|-------|
| **admin** | Toate modulele: Admin, Recepție, Bucătărie, Ghișeu, Livrare |
| **receptie** | Recepție (creare comenzi, căutare clienți, lista comenzi) |
| **bucatarie** | Bucătărie (gătire, buffer, împachetare, stoc, necesar) |
| **ghiseu** | Ghișeu (bon casă, firme, special, raport) |
| **livrator** | Livrare (propria rută, avize) |

**Creare utilizatori** — doar Admin, din modulul Admin → Utilizatori.

---

## 3. Admin

Modulul Admin conține 6 secțiuni: **Lansare**, **Planificare**, **Firme**, **Nomenclator**,
**Ingrediente**, **Utilizatori** și **Rapoarte**.

---

### 3.1 Planificare Săptămânală

**Scop:** Stabilești ce produse apar în meniu în fiecare zi.

**Tipuri de plan:**

| Tip | Componente obligatorii |
|-----|----------------------|
| **Prânz** | Felul 1 + Felul 2 Varianta A + Felul 2 Varianta B + Salată/Accesoriu |
| **Cină** | Felul 2 (principal) + Salată |
| **Sandwich** | Unul sau mai mulți sandwichs din nomenclator |

**Cum planifici:**
1. Navighezi la săptămâna dorită cu butoanele `← Săpt. anterioară / Săpt. următoare →`
2. Dai click pe ziua din calendar
3. Completezi câmpurile pentru **Prânz**, **Cină** sau **Sandwich**
4. Apeși **Salvează**

> Tabelul săptămânal de sub formular arată planificarea pe 7 zile dintr-o privire.

**Export flyer meniu (Excel):**
- Butonul **📥 Export Flyer Meniu** generează un fișier Excel formatat pentru tipărire A4,
  cu meniu prânz + cină pe zilele Luni–Sâmbătă, datele de contact și nota de alergeni.

---

### 3.2 Lansare Producție

**Scop:** Spui bucătăriei câte porții să pregătească.

**Tipuri de loturi:**

| Tip | Când se folosește |
|-----|-----------------|
| **Lot Prânz** | Meniu zilnic de prânz (porțiile planificate) |
| **Lot Cină** | Meniu de seară |
| **Lot Eveniment** | Catering, protocol, pomeni — produse libere din nomenclator |

**Cum lansezi Lot Prânz:**
1. Selectezi data cu navigatorul săptămânal
2. În secțiunea **Lot Prânz** introduci cantitățile în dreptul fiecărui produs din planul zilei
3. Apeși **🚀 Lansează Lot Prânz**

> Produsele din plan apar automat — nu trebuie selectate manual. Cantitățile sunt cele pe
> care bucătăria trebuie să le gătească.

**Lot Eveniment:**
1. Selectezi produsele din nomenclator (orice categorie) și cantitățile
2. Completezi **Descrierea evenimentului** (obligatorie — ex: „Parastas Popescu")
3. Alegi tipul de ridicare: **La masă** sau **La pachet**
4. Apeși **🚀 Lansează Lot Eveniment**

**Completare lot existent:**
- Dacă ai lansat deja un lot și trebuie să adaugi produse extra → butonul **➕ Completează**
  de lângă lotul respectiv.

**Anulare lot:**
- Butonul **🗑️ Anulează** marchează lotul ca anulat. Nu mai apare în bucătărie și nu
  mai contează la calcul stoc.

**Tabelul Stoc Zilnic:**
- Afișează per produs: `Lansat | Consumat | Rămas`
- **Lansat** = total din lotul intern (client_id=999)
- **Consumat** = comenzi recepție livrare + serviri ghișeu bon casă / firme
- **Rămas** = Lansat − Consumat

---

### 3.3 Firme cu Contract

Modulul Firme are 4 taburi: **Gestiune**, **Lansare**, **Prezență**, **Raport**.

#### Tab Gestiune

**Tipuri de firmă:**

| Tip | Descriere |
|-----|-----------|
| **Ghișeu (nominal)** | Angajații vin la ghișeu; servire nominală per persoană |
| **Ghișeu + Livrare** | Prânzul se livrează; cina se ridică la ghișeu |
| **Livrare fixă** | Cantitate fixă livrată zilnic (sandwich, meniu fix) |
| **Meniu Special** | Meniu construit manual, independent de planificarea zilei |

**Adaugă firmă nouă:**
1. Completezi Nume firmă, Tip contract (Prânz+Cină / Doar Prânz / Doar Cină), Tip firmă
2. Apeși **Adaugă**

**Editare firmă:** formular inline cu câmpuri Nume, Tip contract, Tip firmă, Telefon, Adresă.

**Activare/dezactivare firmă:** butonul **Activează/Dezactivează** din cardul firmei.

**Gestionare angajați:**
- **Adaugă angajat** — câmpul de text din cardul firmei → **➕ Adaugă**
- **Concediu/inactiv** — butonul 🔴 din dreptul angajatului → trece în lista Inactivi
- **Reactivare** — din secțiunea Inactivi, butonul 🟢 readuce angajatul în lista activilor
- La orice modificare a angajaților activi, **rezervarea zilnică se actualizează automat**

#### Tab Lansare

**Scop:** Lansezi comanda de livrare pentru firmele cu tip `Ghișeu+Livrare`, `Livrare fixă`,
sau `Meniu Special`.

**Cum lansezi:**
1. Selectezi data (implicit azi)
2. Alegi firma din dropdown
3. Selectezi produsele și cantitățile (din planul zilei sau orice produs pentru meniu special)
4. Alegi livratorl + ora
5. Apeși **Lansează**

#### Tab Prezență

**Scop:** Confirmați câți angajați vin azi (pentru firmele ghișeu).

- Rezervarea se auto-inițializează din numărul angajaților activi
- Poți corecta manual cantitatea per firmă și apăsezi **Salvează**
- Total porții rezervate apare în sumar

#### Tab Raport

Afișează per firmă, per zi selectată: angajat, produse servite, tip servire, oră.

**Export Excel** — generează un fișier cu câte un sheet per firmă.

---

### 3.4 Nomenclator

**Scop:** Gestionezi lista de produse disponibile.

**Categorii:**

| Cod | Etichetă | Utilizare |
|-----|----------|-----------|
| `felul_1` | 🥣 Felul 1 | Planificare prânz/cină |
| `felul_2` | 🍖 Felul 2 | Planificare prânz/cină |
| `salate` | 🥗 Salate | Planificare prânz/cină |
| `sandwich` | 🥪 Sandwich | Planificare sandwich |
| `special` | ✨ Speciale | Comenzi speciale ghișeu |
| `desert` | 🍮 Desert | Comenzi extra |

**Operații:**
- **Adaugă** — introduci Nume, Categorie, Preț (RON) → **Adaugă produs**
- **Editează** — click pe rândul produsului → modifici inline → **Salvează**
- **Șterge** — butonul 🗑️ din dreptul produsului
- **Export Excel** — lista completă cu prețuri pentru arhivă

---

### 3.5 Ingrediente și Rețete

**Ingrediente:**
- Catalog ingrediente cu Nume, Unitate de măsură (kg/l/buc/g/ml), Categorie
- Adaugă ingredient nou din formular sau direct din pagina de rețetă a unui produs

**Rețete per produs:**
- Din Nomenclator → click pe denumirea produsului → **Rețetă**
- Adaugi linie: selectezi ingredientul din catalog (sau creezi unul nou), introduci cantitatea
- **Conversie automată**: introduci în g sau ml, se salvează în kg sau l
- La **Lansare Producție**, cantitățile necesare de ingrediente se calculează automat
  (porții × cantitate per rețetă) și se înregistrează în tabelul **Necesar Zi**
- Bucătăria le vede în Tab Necesar și poate bifa ce a primit

---

### 3.6 Utilizatori

**Creare utilizator:**
1. Introduci Username, Parolă, Rol (admin / recepție / bucătărie / ghișeu / livrator)
2. Opțional pentru rol **livrator**: asociezi un livrator din lista Livratori
3. Apeși **Crează utilizator**

**Operații pe utilizatori existenți:**
- **Activare/dezactivare** — toggle per utilizator
- **Resetare parolă** — butonul din dreptul utilizatorului
- **Schimbă livratorul asociat** — pentru utilizatorii cu rol livrator

> **Important:** Utilizatorii cu rol `livrator` trebuie asociați cu un livrator din sistem.
> Altfel, ecranul de livrare va apărea gol.

---

### 3.7 Rapoarte

Modulul Rapoarte are 5 taburi:

#### Tab Comenzi
- Interval de date selectabil
- **Rezumat pe zile**: nr. comenzi, anulate, total lei, câte cash / factură / evenimente
- **Detaliu per comandă**: client, status, sofer, metodă plată, produse, timestamp-uri

#### Tab Producție
- Zi selectabilă
- Per produs: Lot intern / Lot eveniment / Lot firme / Lot recepție / **Total lansat**
- Gătit (cantitate + ora finalizare), Servit la masă, Livrat, Pierderi, **Rămas**

#### Tab Firme
- Interval de date
- Per firmă: porții ghișeu (masă + pachet), porții livrare, total lei
- Detaliu expandabil: fiecare servire / comandă cu produse și timestamps
- Export Excel per firmă

#### Tab Livratori
- Interval de date
- Per șofer: nr. comenzi livrate, total cash încasat

#### Tab Pierderi
- Interval de date
- Per produs: zile cu pierderi, total pierderi declarate, total nevândut, risipă totală
- Detaliu expandabil pe zile

---

## 4. Recepție

### 4.1 Comandă Nouă

**Scop:** Înregistrezi comenzile clienților care solicită livrare.

> Toate comenzile din recepție sunt de tip **livrare** — câmpul tip comandă este setat
> automat, nu poate fi schimbat.

**Pași:**

**1. Client:**
- Cauți din lista derulantă (după nume sau telefon) **sau**
- Completezi direct Nume + Telefon + Adresă pentru client nou → se creează automat

**2. Produse — 3 taburi de selecție:**

| Tab | Conținut |
|-----|----------|
| **Meniu Rapid** | Butoane rapide V1 și V2 cu câmpuri de cantitate (cel mai frecvent) |
| **Plan Zi** | Produsele planificate azi, grupate pe categorii |
| **Toate Produsele** | Întreg nomenclatorul (sandwich, speciale, orice) |

- Adăugând cantitățile, produsele apar în **Coșul Comenzii** (sticky, mereu vizibil)
- Poți modifica/elimina produse din coș înainte de trimitere

**3. Detalii livrare:**
- **Livrator** *(obligatoriu)* — selectezi din lista șoferilor activi
- **Ora livrare** — interval orar 09:00–14:00 (câte 30 min) sau ⚡ URGENT (08:00)
- **Adresă livrare** — adresa exactă de livrare
- **Metodă plată** — Cash / Card / Cantină / Factură
- **Observații** — instrucțiuni speciale (etaj, interfon etc.)

**4. Confirmare:**
- Apeși **✅ Plasează Comanda** → comanda intră cu status `nou`
- Ești redirecționat la pagina de detaliu a comenzii

**Exemplu:**
```
Client: Popescu Ion — 0741 123 456
Adresă: Str. Florilor nr. 5, et. 2, ap. 12
Produse: Meniu V1 × 2, Solo Ciorbă × 1
Total: 75 lei
Livrator: Mihai  |  Ora: 12:30  |  Plată: Cash
```

---

### 4.2 Lista Comenzi (Index Recepție)

Afișează comenzile din ziua curentă, cu filtru pe status.

**Statusuri posibile:**
```
nou → pregatit → pedrum → livrat
              ↓
           anulat
```

**Operații din detaliu comandă:**
- **Schimbă status** — formular cu selectare status valid următor
- **Anulează** — disponibil dacă comanda nu este deja livrată

---

### 4.3 Căutare Clienți

Pagina `/staff/receptie/clienti/` permite:
- Căutare după nume sau telefon
- Adăugare client nou (Nume + Telefon obligatorii, Adresă opțională)

---

## 5. Bucătărie

### 5.1 Tab Gătire

**Scop:** Bucătarul urmărește ce trebuie gătit și marchează progresul.

**Ce apare în lista de gătire:**
- **Loturi lansate de admin** (prânz + cină + eveniment)
- **Orice produs din comenzile recepției care NU este în planul zilei**
  (sandwich, speciale, produse custom adăugate din tab „Toate Produsele")

> Produsele din planul zilei comandate prin recepție NU apar separat — sunt acoperite
> de lotul lansat de admin. Bucătăria gătește o singură dată în bulk.

**Per produs:**
- Cantitate `de gătit` și cantitate `gată`
- Bara de progres vizuală
- Buton **✅ Tot Gata** → toate liniile aferente acelui produs devin `gatit`
- Buton **Reset** → revin la `nou` dacă ai greșit

**Gătire per linie individuală:**
- Din tab Împachetare poți marca o singură linie ca gătită

---

### 5.2 Tab Buffer Pre-ambalare

**Scop:** Bucătăria pre-ambalează porții generice pe care ghișeul le distribuie rapid.

**Tipuri de buffer:**

| Cheie | Conținut | Tip servire |
|-------|----------|-------------|
| `f1` | Felul 1 (solo) | Masă |
| `f2v1` | Felul 2 Varianta 1 (solo) | Masă |
| `f2v2` | Felul 2 Varianta 2 (solo) | Masă |
| `sal` | Salată (solo) | Masă |
| `v1` | F1 + F2v1 + Salată (meniu complet) | Pachet |
| `v2` | F1 + F2v2 + Salată (meniu complet) | Pachet |
| `solo_f1` | Doar Felul 1 | Pachet |
| `solo_f2v1` | F2v1 + Salată | Pachet |
| `solo_f2v2` | F2v2 + Salată | Pachet |

**Cum adaugi în buffer:**
1. Selectezi **Prânz** sau **Cină** (toggle sus)
2. Introduci cantitatea lângă componenta dorită → **➕ Adaugă**

**Protecții automate:**
- Nu poți adăuga mai mult decât cantitatea gătită
- Dacă componentele necesare nu sunt marcate `gatit`, primești eroare

**Metrici afișate per componentă:** `Cantitate | Distribuit | Disponibil`

> **Buffer Masă** = componente individuale (ghișeul le ia pe bucăți)
> **Buffer Pachet** = meniuri compuse ambalate fizic (se distribuie ca un singur colet)

---

### 5.3 Tab Împachetare

**Scop:** Bucătarul ambalează comenzile individuale (recepție, pachete firme, loturi eveniment).

**Secțiunea Comenzi Recepție:**
- Apar comenzile cu status `nou` din ziua curentă
- Indicator `nr. produse gătite / nr. total produse` per comandă
- Dacă toate produsele sunt gata → buton **📦 Ambalat** → comanda devine `pregatit`
  și apare la livrator
- Dacă nu se poate onora → **❌ Anulează**

**Secțiunea Pachete Firme:**
- Angajații firmelor pentru care ghișeul a ales „La pachet"
- Status: `astept` → buton **📦 Ambalat** → devine `ambalat` → apare la ghișeu ca „Gata de ridicat"

**Secțiunea Loturi Eveniment:**
- Loturi lansate de admin cu tip `eveniment` sau `special`
- Marchezi **📦 Pregătit** când ai ambalat lotul → apare la ghișeu pentru distribuție

---

### 5.4 Tab Stoc Nevândut

**Scop:** La finalul zilei declari ce a rămas.

**Calcul automat afișat per produs:**
- `Gătit` — total marcat `gatit` azi
- `Servit` — servit la ghișeu (bon casă + firme)
- `Livrat` — comenzi cu status `livrat`
- `Rămas` = Gătit − Servit − Livrat (pre-completat automat)

**Cum declari:**
1. Ajustezi câmpul `Nevândut` (câte porții rămân efectiv)
2. Opțional completezi `Pierderi` (produse degradate, accidente)
3. Apeși **💾 Salvează Stoc Nevândut**

> Declarația poate fi refăcută oricând în aceeași zi (se suprascrie).

---

### 5.5 Tab Necesar Ingrediente

**Scop:** Lista ingredientelor necesare pentru loturile lansate azi.

- Se calculează automat la lansarea fiecărui lot (cantitate porții × rețetă)
- Bifezi **✓ Primit** pentru fiecare ingredient sosit de la furnizor
- **Export Excel** — listă formatată pentru tipărire A4 (cu categorii, cantități și coloana „Primit")

---

## 6. Ghișeu

### 6.1 Tab Bon Casă

**Scop:** Clientul a plătit la casă — ghișeul confirmă ce a cumpărat și scade din buffer.

**Selectare plan (Prânz / Cină):**
- Toggle sus: selectezi dacă servești din planul de prânz sau de cină

**Construirea bonului:**
- Alegi meniurile și cantitățile (V1, V2, Solo F1, Solo F2v1, Solo F2v2)
- Disponibilul din buffer apare lângă fiecare opțiune
- Selectezi tipul de ridicare: **La masă** sau **La pachet**

**Confirmare:**
- **✅ Servește** → servirea se salvează, buffer-ul scade

**Istoric bon casă:**
- Ultimele 30 serviri din ziua curentă apar mai jos cu produsele și totalul calculat

---

### 6.2 Tab Firme

**Scop:** Servești angajații firmelor cu contract zilnic.

**Structura ecranului:**
- Fiecare firmă apare ca un card: `SC Exemplu SRL — 3 / 8 serviți`
- Cardurile firmelor cu angajați neserviți sunt evidențiate

**Pentru fiecare angajat neservit:**
1. **Selectează meniu** (dropdown cu opțiunile din planul zilei: V1, V2, Solo F1 etc.)
2. **Tip ridicare:**
   - **🍽️ La masă** → angajatul mănâncă pe loc; buffer-ul de masă scade
   - **📦 La pachet** → merge la bucătărie pentru ambalare; buffer-ul de pachet scade
3. Apeși **Servește**

**Status pachete:**
```
Ghișeu selectează La pachet
  → Bucătărie: status_pachet = 'astept' → buton 📦 Ambalat
  → Ghișeu: apare "📦 Gata de ridicat" → angajatul ridică
```

**Adaugă angajat direct din ghișeu:**
- Câmpul „Nume angajat nou" din cardul firmei → **➕**
- Angajatul apare imediat în lista activilor

**Marchează concediu:**
- Butonul 🔴 → angajatul trece la Inactivi (nu mai apare a doua zi)
- Butonul 🟢 din lista Inactivi → reactivare

---

### 6.3 Tab Special

**Scop:** Ghișeul trimite comenzi pentru produse speciale (din categoria `special` în nomenclator)
direct la bucătărie.

**Exemplu de utilizare:** client cere un cozonac / produs special care nu e în planul zilei.

**Flux:**
1. Selectezi produsele speciale și cantitățile
2. Alegi tipul de ridicare: La masă sau La pachet
3. Apeși **Trimite la bucătărie** → comanda apare în Tab Împachetare la bucătărie
4. Bucătăria o marchează `pregătit`
5. Înapoi la ghișeu: apare ca `Gata` → buton **✅ Servit**

---

### 6.4 Tab Raport

Situația zilei curentă:
- Serviri bon casă (număr + rezumat produse + total lei)
- Serviri firme (număr + rezumat produse per firmă)
- Loturi eveniment distribuite (total lei)
- Comenzi speciale servite

---

## 7. Livrator

**Scop:** Șoferul vede și gestionează propria rută de livrare.

> Livratorii se autentifică cu propriul cont. Ecranul filtrează automat comenzile alocate
> numelui lor. Admin-ul poate previzualiza orice rută din `?sofer=NumeLivrator`.

**Secțiunea „De preluat"** (status `pregatit`):
- Comenzile ambalate de bucătărie, gata de ridicat
- Per comandă: Oră livrare, Client, Adresă, Telefon, Produse, Sumă + metodă plată
- Buton **🚚 Pe drum** → status devine `pedrum`
- Buton **📄 Aviz** → descarcă avizul de însoțire (Excel) pentru acea comandă

**Secțiunea „Pe drum"** (status `pedrum`):
- Comenzile în curs de livrare
- Buton **✅ Livrat** → status devine `livrat` (dispare din lista activă)
- Buton **⚠️ Problemă** → revine la `nou`, adaugă notă la observații (ex: „absent la domiciliu")

**Sumar rapid (afișat în bara de sus):**
- De preluat / Pe drum / Livrate / **Total cash de încasat**

**Aviz de însoțire:**
- Generat în Excel, conform formularului legal
- Include: Furnizor (LOTUS GRIGCONS SRL), Cumpărător (client), produse cu prețuri fără/cu TVA,
  număr aviz unic (`AVZ-000001`), semnătură șofer, dată
- TVA aplicat: 11%

---

## 8. Stoc — cum se calculează

Stocul zilnic se calculează în timp real pentru fiecare produs:

```
LANSAT  = cantitățile din lotul intern (client_id=999, tip=pranz/cina, neAnulate)

CONSUMAT = comenzi recepție livrare (tip_comanda='livrare', client real, neAnulate)
         + serviri ghișeu bon casă (tip_servire='bon_casa')
         + serviri ghișeu firme   (tip_servire='firma')

RĂMAS = max(LANSAT - CONSUMAT, 0)
```

> Loturile de eveniment au stoc propriu și **nu intră** în calculul CONSUMAT al lotului de prânz.
> Ele se gestionează separat la ghișeu → Tab Raport (distribuit = livrat).

**De ce este important:**
- Comenzile de la recepție și servirile de la ghișeu trag din același lot lansat
- Dacă nu s-a lansat nicio producție, stocul este 0 chiar dacă există comenzi

---

## 9. Scenarii complete

### Scenariul A — Zi normală de prânz

```
08:00 ADMIN
  → Planificare (deja făcută săptămânal)
  → Lansare Lot Prânz: Ciorbă×40, Mușchi×25, Fasole×15, Murături×40
    (bucătăria vede imediat în Tab Gătire)

09:00 RECEPȚIE
  → Client: Popescu Ion
    Meniu V1 ×2, livrare 12:30, Livrator: Mihai, Cash 50 lei
  → Client: Ionescu Maria
    Solo Ciorbă ×1, livrare 13:00, Livrator: Mihai, Card 18 lei

10:00 BUCĂTĂRIE — Tab Gătire
  → Ciorbă ×40 → ✅ Tot Gata
  → Mușchi ×25 → ✅ Tot Gata
  → Fasole ×15 → ✅ Tot Gata
  → Murături ×40 → ✅ Tot Gata

10:30 BUCĂTĂRIE — Tab Buffer
  → V1 (Ciorbă+Mușchi+Murături) pachet ×15 → Adaugă
  → V2 (Ciorbă+Fasole+Murături) pachet ×10 → Adaugă
  → f1 (Ciorbă) masă ×20 → Adaugă

10:45 BUCĂTĂRIE — Tab Împachetare
  → Comanda Popescu Ion: 2/2 gata → 📦 Ambalat → status pregatit
  → Comanda Ionescu Maria: 1/1 gata → 📦 Ambalat → status pregatit

11:00 GHIȘEU — Tab Firme
  → SC Exemplu SRL:
    Ion Popescu → V1 → La masă ✓
    Maria Ionescu → V2 → La pachet → status astept

11:05 BUCĂTĂRIE — Tab Împachetare
  → Pachet Maria Ionescu (firmă): 📦 Ambalat → status ambalat

11:10 GHIȘEU — Tab Firme
  → Maria Ionescu: "📦 Gata" → angajata ridică pachetul

12:00 GHIȘEU — Tab Bon Casă
  → Clienți directi: V1 ×3 → La masă → Servește

12:30 LIVRATOR (Mihai)
  → De preluat: Popescu Ion → 🚚 Pe drum
  → Pe drum: Popescu Ion → ✅ Livrat
  → De preluat: Ionescu Maria → 🚚 Pe drum → ✅ Livrat

14:30 BUCĂTĂRIE — Tab Stoc Nevândut
  → Fasole: gătit=15, servit=5, livrat=2 → rămas=8 → declară 8 nevândut, 0 pierderi

15:00 ADMIN — Rapoarte → Tab Producție (data azi)
  → Situația completă per produs
```

---

### Scenariul B — Lot Eveniment (protocol, pomană)

```
08:00 ADMIN — Lansare → Lot Eveniment
  → Produs: Sarmale ×50, Cozonac ×20
  → Descriere: "Parastas Marinescu 15 mai"
  → Tip ridicare: La pachet
  → Lansează

10:00 BUCĂTĂRIE — Tab Gătire
  → Sarmale ×50 → ✅ Tot Gata
  → Cozonac ×20 → ✅ Tot Gata

10:30 BUCĂTĂRIE — Tab Împachetare → Secțiunea Loturi Eveniment
  → Parastas Marinescu: 2/2 gata → 📦 Pregătit

11:00 GHIȘEU — Tab Firme sau Raport
  → Lotul "Parastas Marinescu" apare ca pregătit
  → Buton Distribuit → status livrat
```

---

### Scenariul C — Client nou la recepție

```
1. Recepție → Comandă Nouă
2. Câmpul Client → scrii "Gheorghe" → nu apare în bază
3. Completezi: Nume = Gheorghe Vasile / Tel = 0741 999 888 / Adresă = Str. Trandafirilor 3
4. Clientul se creează automat la plasarea comenzii
5. Adaugi produse → Coș → Plasează Comanda
```

---

### Scenariul D — Comandă specială ghișeu

```
Client cere la ghișeu un produs care nu e în planul zilei (ex: Plăcintă):

1. Ghișeu → Tab Special
2. Selectezi "Plăcintă" (categorie special în nomenclator) → cantitate 1
3. Tip: La masă
4. Trimite la bucătărie

5. Bucătărie → Tab Împachetare → Secțiunea Comenzi Speciale Ghișeu
   → Comanda specială #X → 📦 Gata

6. Ghișeu → Tab Special → "Gata!" apare lângă comanda X
   → Buton ✅ Servit
```

---

### Scenariul E — Problemă la livrare

```
1. Livrator → Pe drum → comanda Popescu Ion
2. Nu răspunde nimeni → buton ⚠️ Problemă → adaugi "absent la domiciliu"
3. Comanda revine la status nou cu nota adăugată
4. Recepția vede nota în detaliu comandă și poate contacta clientul
5. Dacă se rezolvă: recepția schimbă statusul înapoi la pregatit
```

---

## Note Operaționale

**Ordinea obligatorie a operațiunilor:**
1. Admin lansează lotul → bucătăria îl vede
2. Bucătăria marchează `gatit` → ghișeul poate servi din buffer
3. Bucătăria marchează `ambalat` → livratorii preiau comenzile

**Stocul se calculează automat și în timp real** — nu necesită intervenție manuală.

**Buffer vs Stoc Nevândut:**
- **Buffer** = porții pre-ambalate azi, gata de distribuit azi
- **Nevândut** = porții rămase la finalul zilei, declarate de bucătărie

**Loturile de producție se pot lansa cu o zi înainte** (sau cu oricâte zile înainte).
Sistemul nu restricționează data — selectezi data dorită din navigatorul de săptămână.

**Dacă nu s-a lansat lotul**, stocul este 0. Comenzile recepției există în sistem, dar
calculul de stoc va arăta „0 lansat, 0 rămas". Bucătăria vede totuși comenzile individuale
non-plan în Tab Gătire.

---

*Versiune: Mai 2026 — DjangoLotus / Cantina Lotus*
