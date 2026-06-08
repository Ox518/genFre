#!/usr/bin/env bash
# GitMine TTY — VPS first-run setup (Ubuntu 22.04 / Debian 12)
# Run as root: bash scripts/vps-setup.sh
set -euo pipefail

DATABASE_URL="${DATABASE_URL:-}"
if [[ -z "$DATABASE_URL" ]]; then
  echo "ERROR: set DATABASE_URL before running this script"
  exit 1
fi

echo "==> Updating system"
apt-get update -qq && apt-get upgrade -y -qq

echo "==> Creating gitmine user"
useradd --system --shell /bin/false --home /opt/gitmine --create-home gitmine 2>/dev/null || true

echo "==> Creating directories"
mkdir -p /opt/gitmine/config
mkdir -p /etc/gitmine
chown -R gitmine:gitmine /opt/gitmine

echo "==> Writing environment file"
cat > /etc/gitmine/env <<EOF
DATABASE_URL=${DATABASE_URL}
RUST_LOG=info
# Uncomment and fill in when daemons are running:
# FNNC_RPC_URL=http://127.0.0.1:8545
# FNNC_RPC_PASS=yourpassword
# TTY_RPC_URL=http://127.0.0.1:8546
# TTY_RPC_PASS=yourpassword
# FNNC_POOL_ADDRESS=your_fnnc_address
# TTY_POOL_ADDRESS=your_tty_address
EOF
chmod 600 /etc/gitmine/env

echo "==> Installing systemd service"
cp /opt/gitmine/deploy/gitmine-pool.service /etc/systemd/system/gitmine-pool.service 2>/dev/null || \
  curl -sL https://raw.githubusercontent.com/5mil/gitmine-tty/main/deploy/gitmine-pool.service \
    -o /etc/systemd/system/gitmine-pool.service

systemctl daemon-reload
systemctl enable gitmine-pool

echo "==> Opening firewall port 3333 (miners)"
ufw allow 3333/tcp comment 'GitMine Stratum' 2>/dev/null || true
ufw allow 22/tcp comment 'SSH' 2>/dev/null || true
ufw --force enable 2>/dev/null || true

echo ""
echo "=========================================="
echo " Setup complete."
echo " Next steps:"
echo "   1. Copy gitmine-pool binary to /opt/gitmine/gitmine-pool"
echo "   2. sudo systemctl start gitmine-pool"
echo "   3. sudo journalctl -u gitmine-pool -f"
echo "=========================================="
