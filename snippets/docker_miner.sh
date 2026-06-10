#!/bin/bash
set -e
DIR="/opt/gitmine"
apt-get update -qq && apt-get install -y git python3-pip python3-venv -qq
git clone https://github.com/Ox518/genFre "$DIR"
cd "$DIR" && python3 -m venv venv
./venv/bin/pip install -r requirements.txt -q
cat > /etc/systemd/system/gitmine.service <<'EOF'
[Unit]
Description=GitMine Harvest Miner
After=network.target
[Service]
Type=simple
WorkingDirectory=/opt/gitmine
EnvironmentFile=/opt/gitmine/.env
ExecStart=/opt/gitmine/venv/bin/python miner/git-mine-tty.py --rig-id ${RIG_ID} --algo auto --pool-repo Ox518/genFre
Restart=on-failure
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable gitmine && systemctl start gitmine
