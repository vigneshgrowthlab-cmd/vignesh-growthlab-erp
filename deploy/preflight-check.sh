#!/usr/bin/env bash
#
# Wholesale ERP — server preflight check (CloudPanel / Debian 13)
# Read-only. Run as the site user or any user; does NOT modify anything.
#
#   scp this file to the server, then:
#     bash preflight-check.sh
#   or one-shot over SSH:
#     ssh user@server 'bash -s' < deploy/preflight-check.sh
#
set -u

GREEN=$'\e[32m'; RED=$'\e[31m'; YEL=$'\e[33m'; BLU=$'\e[36m'; NC=$'\e[0m'
ok()   { printf "  ${GREEN}[ OK ]${NC} %s\n" "$1"; }
warn() { printf "  ${YEL}[WARN]${NC} %s\n" "$1"; }
bad()  { printf "  ${RED}[MISS]${NC} %s\n" "$1"; }
hdr()  { printf "\n${BLU}== %s ==${NC}\n" "$1"; }

have() { command -v "$1" >/dev/null 2>&1; }

hdr "System"
printf "  Host        : %s\n" "$(hostname)"
if [ -r /etc/os-release ]; then . /etc/os-release; printf "  OS          : %s\n" "$PRETTY_NAME"; fi
printf "  Kernel/arch : %s / %s\n" "$(uname -r)" "$(uname -m)"
printf "  CPU cores   : %s\n" "$(nproc 2>/dev/null || echo '?')"
printf "  Memory      : %s\n" "$(free -h 2>/dev/null | awk '/Mem:/{print $2" total, "$7" available"}')"
printf "  Disk (/)    : %s\n" "$(df -h / 2>/dev/null | awk 'NR==2{print $4" free of "$2}')"

hdr "Python (backend runtime)"
if have python3; then
  PYV=$(python3 -V 2>&1 | awk '{print $2}')
  ok "python3 = $PYV"
  case "$PYV" in
    3.11.*|3.12.*) ok "version is in the well-tested range for the pinned deps" ;;
    3.13.*) warn "Python 3.13 — pinned pandas==2.2.2 / Pillow==10.3.0 / weasyprint==61.2 may lack 3.13 wheels; may need build-essential or a pyenv 3.12" ;;
    3.10.*) warn "3.10 works but 3.11/3.12 preferred" ;;
    *) warn "unexpected version — confirm pinned deps install" ;;
  esac
else bad "python3 not found"; fi
have python3 && python3 -m venv --help >/dev/null 2>&1 && ok "venv module available" || bad "python3-venv missing  ->  apt install python3-venv"
have pip3 && ok "pip3 = $(pip3 -V 2>&1 | awk '{print $2}')" || warn "pip3 not found (venv provides its own; ok)"
have python3 && python3 -c 'import ensurepip' 2>/dev/null && ok "ensurepip available" || warn "ensurepip missing -> may need python3-venv full"

hdr "Build toolchain (needed if any wheel compiles from source)"
have gcc && ok "gcc = $(gcc -dumpversion)" || warn "gcc missing -> apt install build-essential"
have make && ok "make present" || warn "make missing -> apt install build-essential"
( have pkg-config || have pkgconf ) && ok "pkg-config present" || warn "pkg-config missing -> apt install pkg-config"
[ -e /usr/include/python3*/Python.h ] 2>/dev/null && ok "python dev headers present" || warn "python3-dev headers missing -> apt install python3-dev (needed if wheels build from source)"
{ have mysql_config || have mariadb_config; } && ok "mysql/mariadb client headers present" || warn "libmariadb-dev not found (pymysql is pure-python, usually fine to ignore)"

hdr "WeasyPrint native libs (PDF generation — invoices/credit notes)"
check_lib() { if ldconfig -p 2>/dev/null | grep -q "$1"; then ok "$2 ($1)"; else bad "$2 MISSING ($1) -> PDF endpoints will crash"; fi; }
check_lib "libpango-1.0"     "Pango"
check_lib "libpangocairo"    "PangoCairo"
check_lib "libcairo"         "Cairo"
check_lib "libgdk_pixbuf"    "GDK-Pixbuf"
check_lib "libffi"           "libffi"
check_lib "libharfbuzz"      "HarfBuzz"
printf "  ${BLU}fix-all:${NC} apt install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev libharfbuzz0b fonts-dejavu\n"

hdr "Node / npm (frontend build)"
if have node; then
  NV=$(node -v); ok "node = $NV"
  MAJ=$(printf '%s' "$NV" | sed 's/^v//; s/\..*//')
  [ "${MAJ:-0}" -ge 18 ] && ok "node >= 18 (vite 5 / react 18 ok)" || bad "node < 18 — vite 5 needs Node 18+"
else bad "node not found -> install Node 18 or 20 LTS"; fi
have npm && ok "npm = $(npm -v)" || bad "npm not found"

hdr "Database (MariaDB / MySQL)"
if have mariadb || have mysql; then
  CLI=$(command -v mariadb || command -v mysql)
  ok "client: $("$CLI" --version 2>/dev/null)"
else warn "no mysql/mariadb CLIENT on PATH (CloudPanel may still run the server)"; fi
if have mysqld || have mariadbd || pgrep -x mariadbd >/dev/null 2>&1 || pgrep -x mysqld >/dev/null 2>&1; then
  ok "DB server process detected"
else warn "DB server process not detected as this user (CloudPanel runs it; verify via panel)"; fi
ss -ltnp 2>/dev/null | grep -q ':3306' && ok "something is listening on :3306" || warn ":3306 not listening (check DB service)"

hdr "Web server / reverse proxy"
have nginx && ok "nginx = $(nginx -v 2>&1 | sed 's#.*/##')" || warn "nginx not on PATH (CloudPanel bundles it under /home/clp or /usr/sbin)"
ss -ltn 2>/dev/null | grep -qE ':80|:443' && ok "ports 80/443 in use (CloudPanel nginx)" || warn "80/443 not listening yet"
ss -ltn 2>/dev/null | grep -q ':8000' && warn ":8000 already in use — pick another backend port" || ok ":8000 free for the FastAPI backend"

hdr "Tooling"
have git && ok "git = $(git --version | awk '{print $3}')" || bad "git missing -> apt install git"
have systemctl && ok "systemd present (for the backend service)" || bad "systemd not found — needed for the service unit"
have curl && ok "curl present" || warn "curl missing (handy for smoke tests)"

hdr "Summary"
printf "  Review ${RED}[MISS]${NC} lines first — those block deploy.\n"
printf "  ${YEL}[WARN]${NC} lines are usually fine / situational.\n"
printf "  Likely one-liner to satisfy WeasyPrint + build deps on Debian 13:\n"
printf "    ${BLU}sudo apt update && sudo apt install -y python3-venv python3-dev build-essential pkg-config \\\\${NC}\n"
printf "    ${BLU}  libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev libharfbuzz0b fonts-dejavu git${NC}\n"
