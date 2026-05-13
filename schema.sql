-- =============================================================================
--  schema.sql — Schema bază de date DjangoLotus
--  PostgreSQL 14+
--
--  Utilizare:
--    psql -h HOST -U USER -d DBNAME -f schema.sql
--
--  ATENȚIE: Scriptul folosește CREATE TABLE IF NOT EXISTS — sigur de rulat
--  pe o bază de date existentă (nu suprascrie date).
-- =============================================================================

-- ─── Extensii ─────────────────────────────────────────────────────────────────
-- (opțional, pentru compatibilitate cu Supabase)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
--  TABELE APLICAȚIE LOTUS
-- =============================================================================

-- ─── livratori ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS livratori (
    id    SERIAL PRIMARY KEY,
    nume  TEXT NOT NULL,
    activ BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT livratori_nume_key UNIQUE (nume)
);

-- ─── clienti ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clienti (
    id                   SERIAL PRIMARY KEY,
    nume_client          TEXT NOT NULL,
    telefon              TEXT,
    adresa_principala    TEXT,
    adresa_livrare       TEXT,
    zona_livrare         TEXT,
    observatii_client    TEXT,
    puncte_fidelitate    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT unique_telefon      UNIQUE (telefon),
    CONSTRAINT unique_nume_client  UNIQUE (nume_client)
);
CREATE INDEX IF NOT EXISTS idx_clienti_telefon ON clienti (telefon);
CREATE INDEX IF NOT EXISTS idx_clienti_nume    ON clienti (nume_client);

-- Client intern loturi producție (client_id=999)
INSERT INTO clienti (id, nume_client, telefon)
VALUES (999, 'INTERN — Loturi Producție', 'intern_999')
ON CONFLICT DO NOTHING;

-- Client intern comenzi speciale ghișeu (client_id=998)
INSERT INTO clienti (id, nume_client, telefon)
VALUES (998, 'GHIȘEU — Comenzi Speciale', 'intern_998')
ON CONFLICT DO NOTHING;

-- ─── firme ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS firme (
    id                 SERIAL PRIMARY KEY,
    nume_firma         TEXT NOT NULL,
    tip_contract       TEXT NOT NULL DEFAULT 'pranz_cina',
    tip_firma          VARCHAR(50) NOT NULL DEFAULT 'ghiseu',
    cantitate_default  INTEGER NOT NULL DEFAULT 0,
    activ              BOOLEAN NOT NULL DEFAULT TRUE,
    client_id          INTEGER REFERENCES clienti(id),
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ─── angajati_firme ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS angajati_firme (
    id            SERIAL PRIMARY KEY,
    firma_id      INTEGER NOT NULL REFERENCES firme(id) ON DELETE CASCADE,
    nume_angajat  TEXT NOT NULL,
    activ         BOOLEAN NOT NULL DEFAULT TRUE
);

-- ─── rezervari_firme ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rezervari_firme (
    firma_id   INTEGER NOT NULL REFERENCES firme(id) ON DELETE CASCADE,
    data_rez   DATE    NOT NULL,
    cantitate  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (firma_id, data_rez)
);

-- ─── produse ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS produse (
    id             SERIAL PRIMARY KEY,
    nume           TEXT NOT NULL,
    categorie      TEXT NOT NULL,
    pret_standard  NUMERIC(8,2) DEFAULT 0
);

-- ─── ingrediente ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingrediente (
    id         SERIAL PRIMARY KEY,
    nume       VARCHAR(200) NOT NULL,
    unitate    VARCHAR(20)  NOT NULL DEFAULT 'kg',
    categorie  VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT ingrediente_nume_key UNIQUE (nume)
);

-- ─── reteta_linii ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reteta_linii (
    id             SERIAL PRIMARY KEY,
    produs_id      INTEGER NOT NULL REFERENCES produse(id)     ON DELETE CASCADE,
    ingredient_id  INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE CASCADE,
    cantitate      NUMERIC(10,4) NOT NULL,
    CONSTRAINT reteta_linii_produs_id_ingredient_id_key UNIQUE (produs_id, ingredient_id)
);

-- ─── planificare_meniu (folosit de Django) ────────────────────────────────────
-- Notă: tabelul Streamlit se numește planificare_zi cu coloane diferite.
-- Django folosește planificare_meniu cu produs_id și tip_plan.
CREATE TABLE IF NOT EXISTS planificare_meniu (
    id         SERIAL PRIMARY KEY,
    data_zi    DATE    NOT NULL,
    produs_id  INTEGER NOT NULL REFERENCES produse(id) ON DELETE CASCADE,
    tip_plan   VARCHAR(50) NOT NULL,
    CONSTRAINT planificare_meniu_data_zi_produs_id_key UNIQUE (data_zi, produs_id)
);
CREATE INDEX IF NOT EXISTS idx_planificare_meniu_data ON planificare_meniu (data_zi);

-- ─── comenzi ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS comenzi (
    id                    SERIAL PRIMARY KEY,
    client_id             INTEGER NOT NULL REFERENCES clienti(id),
    data_comanda          DATE    NOT NULL DEFAULT CURRENT_DATE,
    ora_livrare_estimata  TIME,
    status                TEXT    NOT NULL DEFAULT 'nou',
    metoda_plata          TEXT,
    total_plata           NUMERIC(8,2),
    sofer                 TEXT,
    observatii            TEXT,
    detalii_comanda       TEXT,
    adresa_livrare        TEXT,
    tip_comanda           VARCHAR(20),
    tip_ridicare          VARCHAR(20),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    gatit_la              TIMESTAMPTZ,
    pregatit_la           TIMESTAMPTZ,
    pedrum_la             TIMESTAMPTZ,
    livrat_la             TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_comenzi_data       ON comenzi (data_comanda);
CREATE INDEX IF NOT EXISTS idx_comenzi_client     ON comenzi (client_id);
CREATE INDEX IF NOT EXISTS idx_comenzi_status     ON comenzi (status);
CREATE INDEX IF NOT EXISTS idx_comenzi_tip        ON comenzi (tip_comanda);

-- ─── comenzi_linii ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS comenzi_linii (
    id          SERIAL PRIMARY KEY,
    comanda_id  INTEGER      NOT NULL REFERENCES comenzi(id) ON DELETE CASCADE,
    nume_produs TEXT         NOT NULL,
    cantitate   INTEGER      NOT NULL DEFAULT 1,
    pret_unitar NUMERIC(8,2),
    status      VARCHAR(20)  NOT NULL DEFAULT 'nou',
    tip_linie   VARCHAR(20)  NOT NULL DEFAULT 'standard',
    gatit_la    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_comenzi_linii_comanda ON comenzi_linii (comanda_id);
CREATE INDEX IF NOT EXISTS idx_comenzi_linii_status  ON comenzi_linii (status);

-- ─── necesar_zi ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS necesar_zi (
    id                 SERIAL PRIMARY KEY,
    data_zi            DATE    NOT NULL,
    ingredient_id      INTEGER NOT NULL REFERENCES ingrediente(id) ON DELETE CASCADE,
    cantitate_necesara NUMERIC(10,4) NOT NULL DEFAULT 0,
    primit             BOOLEAN NOT NULL DEFAULT FALSE,
    primit_la          TIMESTAMPTZ,
    CONSTRAINT necesar_zi_data_zi_ingredient_id_key UNIQUE (data_zi, ingredient_id)
);

-- ─── buffer_componente ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buffer_componente (
    id          SERIAL PRIMARY KEY,
    data_zi     DATE        NOT NULL,
    componenta  VARCHAR(20) NOT NULL,
    tip_servire VARCHAR(10) NOT NULL,
    tip_plan    VARCHAR(10) NOT NULL DEFAULT 'pranz',
    cantitate   INTEGER     NOT NULL DEFAULT 0,
    distribuit  INTEGER     NOT NULL DEFAULT 0,
    CONSTRAINT buffer_componente_unique UNIQUE (data_zi, componenta, tip_servire, tip_plan)
);

-- ─── serviri_ghiseu ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS serviri_ghiseu (
    id             SERIAL PRIMARY KEY,
    data_servire   DATE    NOT NULL DEFAULT CURRENT_DATE,
    ora_servire    TIME             DEFAULT CURRENT_TIME,
    tip_servire    TEXT    NOT NULL,
    firma_id       INTEGER REFERENCES firme(id),
    angajat_id     INTEGER REFERENCES angajati_firme(id),
    comanda_ref_id INTEGER REFERENCES comenzi(id),
    observatii     TEXT,
    tip_ridicare   TEXT    DEFAULT 'la_masa',
    status_pachet  TEXT,
    din_buffer     BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_serviri_ghiseu_data ON serviri_ghiseu (data_servire);
CREATE INDEX IF NOT EXISTS idx_serviri_ghiseu_tip  ON serviri_ghiseu (tip_servire);

-- ─── serviri_ghiseu_linii ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS serviri_ghiseu_linii (
    id           SERIAL PRIMARY KEY,
    servire_id   INTEGER NOT NULL REFERENCES serviri_ghiseu(id) ON DELETE CASCADE,
    nume_produs  TEXT    NOT NULL,
    cantitate    INTEGER NOT NULL DEFAULT 1,
    din_nevandut BOOLEAN NOT NULL DEFAULT FALSE
);

-- ─── stoc_nevandut ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stoc_nevandut (
    id                SERIAL PRIMARY KEY,
    data              DATE    NOT NULL,
    nume_produs       TEXT    NOT NULL,
    cantitate         INTEGER NOT NULL DEFAULT 0,
    cantitate_servita INTEGER NOT NULL DEFAULT 0,
    pierderi          INTEGER NOT NULL DEFAULT 0,
    declarat_la       TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT stoc_nevandut_data_nume_produs_key UNIQUE (data, nume_produs)
);

-- ─── utilizatori (autentificare proprie Lotus) ────────────────────────────────
CREATE TABLE IF NOT EXISTS utilizatori (
    id            SERIAL PRIMARY KEY,
    username      TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL,
    activ         BOOLEAN NOT NULL DEFAULT TRUE,
    livrator_id   INTEGER REFERENCES livratori(id),
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT utilizatori_username_key UNIQUE (username)
);

-- =============================================================================
--  TABELE DJANGO (sistem — gestionate automat de Django la prima rulare)
--  Le creăm manual pentru a putea rula migrate fără erori.
-- =============================================================================

CREATE TABLE IF NOT EXISTS django_content_type (
    id        SERIAL PRIMARY KEY,
    app_label VARCHAR(100) NOT NULL,
    model     VARCHAR(100) NOT NULL,
    UNIQUE (app_label, model)
);

CREATE TABLE IF NOT EXISTS auth_permission (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    content_type_id INTEGER NOT NULL REFERENCES django_content_type(id),
    codename        VARCHAR(100) NOT NULL,
    UNIQUE (content_type_id, codename)
);

CREATE TABLE IF NOT EXISTS auth_group (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS auth_group_permissions (
    id            BIGSERIAL PRIMARY KEY,
    group_id      INTEGER NOT NULL REFERENCES auth_group(id),
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id),
    UNIQUE (group_id, permission_id)
);

CREATE TABLE IF NOT EXISTS auth_user (
    id           SERIAL PRIMARY KEY,
    password     VARCHAR(128) NOT NULL,
    last_login   TIMESTAMPTZ,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    username     VARCHAR(150) NOT NULL UNIQUE,
    first_name   VARCHAR(150) NOT NULL DEFAULT '',
    last_name    VARCHAR(150) NOT NULL DEFAULT '',
    email        VARCHAR(254) NOT NULL DEFAULT '',
    is_staff     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_user_groups (
    id       BIGSERIAL PRIMARY KEY,
    user_id  INTEGER NOT NULL REFERENCES auth_user(id),
    group_id INTEGER NOT NULL REFERENCES auth_group(id),
    UNIQUE (user_id, group_id)
);

CREATE TABLE IF NOT EXISTS auth_user_user_permissions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES auth_user(id),
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id),
    UNIQUE (user_id, permission_id)
);

CREATE TABLE IF NOT EXISTS django_migrations (
    id      BIGSERIAL PRIMARY KEY,
    app     VARCHAR(255) NOT NULL,
    name    VARCHAR(255) NOT NULL,
    applied TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS django_session (
    session_key  VARCHAR(40) PRIMARY KEY,
    session_data TEXT        NOT NULL,
    expire_date  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_django_session_expire ON django_session (expire_date);

CREATE TABLE IF NOT EXISTS django_admin_log (
    id              SERIAL PRIMARY KEY,
    action_time     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    object_id       TEXT,
    object_repr     VARCHAR(200) NOT NULL,
    action_flag     SMALLINT     NOT NULL,
    change_message  TEXT         NOT NULL DEFAULT '',
    content_type_id INTEGER REFERENCES django_content_type(id),
    user_id         INTEGER NOT NULL REFERENCES auth_user(id)
);

-- =============================================================================
--  DATE INIȚIALE OBLIGATORII
-- =============================================================================

-- Grupuri Django pentru roluri (trebuie să existe înainte de a crea utilizatori)
INSERT INTO auth_group (name) VALUES
    ('admin'),
    ('receptie'),
    ('bucatarie'),
    ('ghiseu'),
    ('livrator')
ON CONFLICT (name) DO NOTHING;

-- Utilizator admin implicit — parolă: admin123
-- !! SCHIMBĂ PAROLA după prima autentificare din Admin → Utilizatori !!
INSERT INTO utilizatori (username, password_hash, rol, activ)
VALUES ('admin', '$2b$12$gfSMmq75XK8WNmTw6aIv5.UrlWQy.3gogvyQB1cIfQkUIK1MuR8Am', 'admin', TRUE)
ON CONFLICT (username) DO NOTHING;

-- =============================================================================
--  NOTE POST-INSTALARE
-- =============================================================================
-- 1. Rulează django migrate după acest script:
--      docker exec lotus_app python manage.py migrate --run-syncdb
--
-- 2. Creează primul utilizator admin Django (pentru /admin/):
--      docker exec -it lotus_app python manage.py createsuperuser
--
-- 3. Creează utilizatorii aplicației (rol admin/receptie/etc.) din
--    interfața Admin → Utilizatori după autentificarea cu Django superuser.
--
-- 4. Asociază utilizatorii cu grupurile de rol din Django Admin → Users.
-- =============================================================================
