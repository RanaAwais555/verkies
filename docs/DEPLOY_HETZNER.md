# Deploying VROS on Hetzner Cloud

One small server runs everything: PostgreSQL, Redis, the API, the worker, the web app and Caddy (automatic HTTPS). About 30 minutes the first time. You need: a Hetzner Cloud account, a domain you control (e.g. `vros.verkies.co`), and an SSH key on your computer.

## 1. Create the server (Hetzner Cloud Console)

1. **Project → Add Server.**
2. **Location:** an EU location (Nuremberg, Falkenstein or Helsinki). Company research data stays in the EU.
3. **Image:** Ubuntu 24.04.
4. **Type:** shared vCPU, **CX22** (2 vCPU, 4 GB RAM) or larger. Check the current price on the page. Without local AI this is enough for a team.
5. **SSH key:** add your public key (`~/.ssh/id_ed25519.pub`; create one with `ssh-keygen -t ed25519` if you have none). Do not use password login.
6. **Firewall:** create one allowing inbound **TCP 22, TCP 80, TCP 443 and UDP 443** only, and attach it.
7. **Backups:** tick it. Hetzner then keeps daily server snapshots; VROS also makes its own nightly database dumps.
8. Create it and copy its **IPv4** (and IPv6) address.

## 2. Point your domain at it

At your DNS provider, add an **A** record: `vros` → the server's IPv4. Add an **AAAA** record → its IPv6 too, if you use IPv6. Wait until `ping vros.verkies.co` shows the server's address, which can take a few minutes. Caddy can only get the HTTPS certificate once DNS points here.

## 3. Prepare the server

```bash
ssh root@<server-ip>

# Updates and automatic security updates
apt update && apt -y upgrade && apt -y install unattended-upgrades git
dpkg-reconfigure -f noninteractive unattended-upgrades

# Docker Engine with Compose v2 (official script from docker.com)
curl -fsSL https://get.docker.com | sh
docker compose version        # must be v2.24 or newer

# A non-root user for running VROS
adduser --disabled-password --gecos "" vros
usermod -aG docker vros
mkdir -p /home/vros/.ssh && cp ~/.ssh/authorized_keys /home/vros/.ssh/ && chown -R vros:vros /home/vros/.ssh

# Then turn off root and password logins over SSH
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/; s/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
exit
```

Before closing this root session, check that `ssh vros@<server-ip>` works from a second terminal.

## 4. Install VROS

```bash
ssh vros@<server-ip>
git clone https://github.com/RanaAwais555/verkies.git
cd verkies
git checkout main          # or the branch you were asked to deploy

cp .env.example .env
nano .env
```

Fill in `.env`:

```bash
VROS_PUBLIC_URL=https://vros.verkies.co
VROS_SITE_ADDRESS=vros.verkies.co
VROS_SECRET_KEY=<output of: openssl rand -hex 32>
VROS_DB_PASSWORD=<output of: openssl rand -hex 24>
```

Optional but recommended: a free **Companies House API key** gives UK registry facts and directors. Register at https://developer.company-information.service.gov.uk, create an application, add a REST API key, and set `VROS_COMPANIES_HOUSE_API_KEY=<key>`. Without it, research works and Settings → System shows Companies House as "Needs setup".

Keep a copy of these secrets in your password manager. `chmod 600 .env` so only you can read it.

The repository is private, so `git clone` needs access. Either use a GitHub fine-grained token with read access to this repo (`git clone https://<token>@github.com/RanaAwais555/verkies.git`, then `git remote set-url origin https://github.com/RanaAwais555/verkies.git` so the token is not stored), or add a read-only **deploy key** (Repo → Settings → Deploy keys) and clone over SSH.

## 5. Start it

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

The first build takes several minutes. When `api` shows `healthy`, check:

```bash
curl https://vros.verkies.co/api/v1/health/ready      # "status":"ok"
```

Create the first admin (asks for a password, 12+ characters):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  python -m app.cli create-admin --email you@verkies.co --name "Your Name"
```

Open `https://vros.verkies.co`, sign in, and invite the team under **Settings → Team**. Each invite is a one-time link valid for 7 days.

Tip: `alias vc='docker compose -f docker-compose.yml -f docker-compose.prod.yml'` saves typing (`vc ps`, `vc logs -f api`).

## 6. Update to a new version

```bash
cd ~/verkies && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Database migrations run automatically (`migrate` service) before the API starts.

## 7. Backups

- **Nightly database dumps:** the `backup` service writes them to the `verkies_backups` Docker volume and keeps 14 days (`VROS_BACKUP_KEEP_DAYS`). Copy them off the server regularly (a backup on the same disk does not survive losing the disk), for example from your computer:
  ```bash
  scp 'root@<server-ip>:/var/lib/docker/volumes/verkies_backups/_data/*' ./vros-backups/
  ```
  (or allow the `vros` user to read that folder.)
- **Server snapshots:** Hetzner Backups (step 1.7) keeps daily snapshots of the whole server.
- **Restoring a dump** (files are `vros-<UTC time>.dump`, PostgreSQL custom format). Stop the app first, then:
  ```bash
  vc stop api worker frontend
  docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
    pg_restore -U vros -d vros --clean --if-exists --no-owner < vros-2026-10-08T020000Z.dump
  vc start api worker frontend
  ```
  Try a restore once on a spare server before you ever need it.

## 8. If something is wrong

| Symptom | Check |
| --- | --- |
| Deploy stops at once with "set VROS_…" | A required value in `.env` is empty |
| `api` keeps restarting | `vc logs api`: the API refuses insecure production settings and says which |
| Browser shows a certificate error | DNS does not point at the server yet, or ports 80/443 are blocked in the Hetzner firewall; `vc logs caddy` |
| Research runs stay queued | `vc ps worker` and `vc logs worker` |

The database, Redis and API are never exposed to the internet; only Caddy listens on 80/443.
