# Deploying the GitMine Pool Server

## One-time VPS setup

```bash
# On your VPS as root:
export DATABASE_URL='postgresql://postgres:PASSWORD@db.wfabhxfpzqrdhlkidkcl.supabase.co:5432/postgres'
curl -sL https://raw.githubusercontent.com/5mil/gitmine-tty/main/scripts/vps-setup.sh | bash
```

## GitHub Actions secrets required

Add these in **Settings → Secrets → Actions**:

| Secret | Value |
|---|---|
| `DATABASE_URL` | Your Supabase Postgres URI ✅ already set |
| `DEPLOY_HOST` | VPS IP or hostname (e.g. `123.45.67.89`) |
| `DEPLOY_USER` | SSH user (e.g. `root` or `gitmine`) |
| `DEPLOY_KEY` | Private SSH key (contents of `~/.ssh/id_ed25519`) |

## Generate a deploy SSH key

```bash
# On your local machine:
ssh-keygen -t ed25519 -C 'gitmine-deploy' -f ~/.ssh/gitmine_deploy -N ''

# Copy public key to VPS:
ssh-copy-id -i ~/.ssh/gitmine_deploy.pub root@YOUR_VPS_IP

# Copy private key contents into GitHub secret DEPLOY_KEY:
cat ~/.ssh/gitmine_deploy
```

## Manual first deploy (before CI is wired)

```bash
# Build locally or on the VPS:
git clone https://github.com/5mil/gitmine-tty
cd gitmine-tty/pool-server

# Install Rust if needed:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Build:
cargo build --release

# Copy binary and start:
cp target/release/gitmine-pool /opt/gitmine/gitmine-pool
sudo systemctl start gitmine-pool
sudo journalctl -u gitmine-pool -f
```

## Verify miners can connect

```bash
# From any machine:
telnet YOUR_VPS_IP 3333
# You should get a connection. Send:
{"id":1,"method":"mining.subscribe","params":[]}
# Expected response:
# {"id":1,"result":[[["mining.notify","XXXXXXXX"]],"XXXXXXXX",4],"error":null}
```
