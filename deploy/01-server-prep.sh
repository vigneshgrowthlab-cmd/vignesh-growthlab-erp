#!/usr/bin/env bash
#
# Wholesale ERP — server system prerequisites (CloudPanel / Debian 13)
# Run ONCE as root. Installs system-wide packages only:
#   - WeasyPrint native libs (PDF generation)
#   - build toolchain + python dev headers
#   - Node.js 20 LTS (frontend build)
# Does NOT install Python 3.12 / uv / the app — those run as the site user later.
#
#   ssh root@server "bash ~/01-server-prep.sh"   (after scp'ing it)
#
set -euo pipefail

echo "== Updating apt index =="
apt update

echo "== Installing WeasyPrint libs + build toolchain =="
apt install -y \
  python3-venv python3-dev build-essential pkg-config \
  libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
  libffi-dev libharfbuzz0b fonts-dejavu \
  git curl ca-certificates

echo "== Installing Node.js 20 LTS (NodeSource) =="
if command -v node >/dev/null 2>&1 && [ "$(node -v | sed 's/^v//; s/\..*//')" -ge 18 ]; then
  echo "  node $(node -v) already present (>=18) — skipping"
else
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt install -y nodejs
fi

echo
echo "== Verification =="
printf "  node : %s\n" "$(node -v 2>/dev/null || echo MISSING)"
printf "  npm  : %s\n" "$(npm -v 2>/dev/null || echo MISSING)"
ldconfig -p | grep -q libpango-1.0 && echo "  Pango: OK" || echo "  Pango: STILL MISSING"
ldconfig -p | grep -q libharfbuzz && echo "  HarfBuzz: OK" || echo "  HarfBuzz: STILL MISSING"
echo
echo "System prerequisites done. Next: create the CloudPanel site, then install uv + Python 3.12 as the site user."
