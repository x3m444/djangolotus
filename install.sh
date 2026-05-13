#!/bin/bash
# =============================================================================
#  install.sh — Script instalare / actualizare DjangoLotus
#  Rulează pe serverul Oracle (Ubuntu) ca utilizator cu acces Docker.
#  Prima rulare: clonează repo și pornește aplicația.
#  Rulările ulterioare: face pull și rebuild.
# =============================================================================

set -e

REPO_URL="https://github.com/x3m444/djangolotus.git"
APP_DIR="$HOME/djangolotus"
ENV_FILE="$APP_DIR/.env"
CONTAINER_NAME="lotus_app"

# ─── Culori pentru output ────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log()    { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1"; }
ok()     { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓ $1${NC}"; }
warn()   { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠  $1${NC}"; }
error()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗ $1${NC}"; exit 1; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        DjangoLotus — Install / Update        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ─── 1. Verificăm că Docker este instalat și rulează ─────────────────────────
log "Verific dacă Docker este disponibil..."
if ! command -v docker &>/dev/null; then
    error "Docker nu este instalat. Instalează Docker înainte de a continua."
fi
if ! docker info &>/dev/null; then
    error "Docker daemon nu rulează sau nu ai permisiuni. Încearcă: sudo usermod -aG docker \$USER"
fi
ok "Docker disponibil: $(docker --version)"

# ─── 2. Verificăm că rețeaua Traefik există ───────────────────────────────────
log "Verific rețeaua Docker 'traefik'..."
if ! docker network ls --format '{{.Name}}' | grep -q '^traefik$'; then
    error "Rețeaua Docker 'traefik' nu există. Traefik trebuie să fie pornit primul."
fi
ok "Rețeaua 'traefik' există."

# ─── 3. Clone sau pull repo ───────────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    log "Directorul $APP_DIR există — fac git pull..."
    cd "$APP_DIR"
    git fetch origin
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)
    if [ "$LOCAL" = "$REMOTE" ]; then
        ok "Codul este deja la zi (commit: ${LOCAL:0:8})."
    else
        git pull origin main
        ok "Cod actualizat: ${LOCAL:0:8} → ${REMOTE:0:8}"
    fi
else
    log "Prima instalare — clonez repository-ul..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
    ok "Repository clonat în $APP_DIR"
fi

# ─── 4. Verificăm fișierul .env ───────────────────────────────────────────────
log "Verific fișierul .env..."
if [ ! -f "$ENV_FILE" ]; then
    warn "Fișierul .env nu există!"
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$ENV_FILE"
        warn "Am copiat .env.example → .env"
        warn "OBLIGATORIU: editează $ENV_FILE cu credențialele reale înainte de a continua."
        warn "  nano $ENV_FILE"
        echo ""
        warn "Variabile necesare:"
        echo "  SECRET_KEY     — cheie secretă Django (generează cu: python -c \"import secrets; print(secrets.token_hex(50))\")"
        echo "  DB_HOST        — host PostgreSQL"
        echo "  DB_PORT        — port (default 5432)"
        echo "  DB_NAME        — numele bazei de date"
        echo "  DB_USER        — utilizator DB"
        echo "  DB_PASS        — parola DB"
        echo "  ALLOWED_HOSTS  — domenii permise (ex: lotus.incercari.duckdns.org)"
        echo "  DEBUG          — False în producție"
        echo "  AUTH_ENABLED   — True"
        echo ""
        read -rp "Ai editat .env și ești gata să continui? (da/nu): " CONFIRM
        if [ "$CONFIRM" != "da" ]; then
            warn "Oprire. Rulează scriptul din nou după ce editezi .env."
            exit 0
        fi
    else
        error ".env.example nu există. Creează manual $ENV_FILE cu variabilele necesare."
    fi
else
    ok "Fișierul .env există."
    # Verificăm că variabilele critice sunt completate
    for VAR in SECRET_KEY DB_HOST DB_NAME DB_USER DB_PASS; do
        VAL=$(grep "^${VAR}=" "$ENV_FILE" | cut -d= -f2- | tr -d ' ')
        if [ -z "$VAL" ] || echo "$VAL" | grep -qE '^(your_|CHANGE_ME|xxx|changeme)'; then
            warn "Variabila $VAR din .env pare necompletată sau implicită."
        fi
    done
fi

# Verificăm ALLOWED_HOSTS
ALLOWED=$(grep "^ALLOWED_HOSTS=" "$ENV_FILE" | cut -d= -f2-)
if ! echo "$ALLOWED" | grep -q "lotus.incercari.duckdns.org"; then
    warn "ALLOWED_HOSTS nu conține 'lotus.incercari.duckdns.org'."
    warn "Adaugă domeniul: ALLOWED_HOSTS=127.0.0.1,localhost,lotus.incercari.duckdns.org"
fi

# ─── 5. Oprire container existent (dacă rulează) ─────────────────────────────
log "Verific dacă există container $CONTAINER_NAME rulând..."
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Opresc containerul existent $CONTAINER_NAME..."
    docker compose down
    ok "Container oprit."
else
    ok "Niciun container activ cu numele $CONTAINER_NAME."
fi

# ─── 6. Build și pornire ──────────────────────────────────────────────────────
log "Construiesc imaginea Docker și pornesc aplicația..."
log "(Primul build durează ~3-5 minute; rebuild-urile ulterioare sunt mai rapide)"
echo ""

docker compose up --build -d

echo ""
ok "Container pornit cu succes!"

# ─── 7. Verificare health ────────────────────────────────────────────────────
log "Aștept 5 secunde pentru pornirea aplicației..."
sleep 5

log "Verific starea containerului..."
STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "absent")
if [ "$STATUS" = "running" ]; then
    ok "Containerul $CONTAINER_NAME rulează (status: $STATUS)."
else
    error "Containerul $CONTAINER_NAME NU rulează (status: $STATUS). Verifică logurile: docker logs $CONTAINER_NAME"
fi

# ─── 8. Primele 20 rânduri de log ────────────────────────────────────────────
echo ""
log "Ultimele linii din log (docker logs $CONTAINER_NAME):"
echo "────────────────────────────────────────────────────"
docker logs --tail 20 "$CONTAINER_NAME" 2>&1
echo "────────────────────────────────────────────────────"

# ─── 9. Sumar final ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Deploy finalizat! ✓             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "  Aplicație: https://lotus.incercari.duckdns.org"
echo "  Logs live: docker logs -f $CONTAINER_NAME"
echo "  Oprire:    docker compose down"
echo "  Restart:   docker compose restart"
echo ""
