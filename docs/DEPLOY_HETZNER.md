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

Optional: **web search** on the Discover page runs a private SearXNG next to VROS (no keys, nothing exposed to the internet). Add `VROS_SEARCH_PROVIDER=searxng` to `.env` and add `--profile search` to the `docker compose` commands below (both `up` and updates).

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

## 7. Backups and disaster recovery

The `backup` service (`ops/backup/`) runs once a day:

1. **Database dump** (`pg_dump`, custom format) into the `verkies_backups` volume.
2. **Uploaded documents** archived next to it.
3. **Off-site copy:** both encrypted with [age](https://age-encryption.org) to *your* public key and uploaded with rclone. The server holds only the public key, so it cannot read its own off-site copies, and nothing is ever sent off the server unencrypted: without a key the upload is refused and recorded as failed.
4. **Restore test:** every Sunday (and on the very first run) the latest dump is restored into a scratch database, checked against the live schema (same tables, same migration), and dropped.

Local copies are kept 14 days (`VROS_BACKUP_KEEP_DAYS`) and off-site copies 30 days (`VROS_BACKUP_OFFSITE_KEEP_DAYS`). Each step's outcome shows under **Settings → System → Backups**, and with the observability profile (§7a) Prometheus alerts when no dump has succeeded for 26 hours, when a step fails, or when no restore test has passed for 8 days.

**Recovery objectives.** At most one day of data can be lost (one dump a day). Rebuilding on a new server from the off-site copy takes about an hour for a small database: a fresh server (§1-4), then the restore below.

### Setting up the off-site copy (once)

1. **Make a key pair on your own computer, not the server**, and keep the private key safe (a password manager, plus a printed copy): whoever holds it can read every backup, and without it no backup can be restored. From your copy of the repository:
   ```bash
   docker build -t vros-backup ops/backup
   docker run --rm -v "$PWD:/k" --entrypoint age-keygen vros-backup -o /k/vros-backup-key.txt
   ```
   It prints `Public key: age1...`. Only that public key goes to the server.
2. **Choose where copies go.** Any rclone backend works; the remote is always named `offsite`. Add to `.env`:
   - A **Hetzner Storage Box** (SFTP; enable SSH support on the box):
     ```bash
     VROS_BACKUP_AGE_RECIPIENT=age1...                 # the public key from step 1
     VROS_BACKUP_REMOTE_PATH=vros-backups              # a folder on the box
     RCLONE_CONFIG_OFFSITE_TYPE=sftp
     RCLONE_CONFIG_OFFSITE_HOST=uXXXXXX.your-storagebox.de
     RCLONE_CONFIG_OFFSITE_PORT=23
     RCLONE_CONFIG_OFFSITE_USER=uXXXXXX
     RCLONE_CONFIG_OFFSITE_PASS=...                    # obscured, see below
     ```
     rclone wants the password obscured: `docker run --rm --entrypoint rclone vros-backup obscure 'the-box-password'`.
   - **S3-compatible storage** (Hetzner Object Storage, Backblaze B2, AWS):
     ```bash
     VROS_BACKUP_AGE_RECIPIENT=age1...
     VROS_BACKUP_REMOTE_PATH=my-bucket/vros
     RCLONE_CONFIG_OFFSITE_TYPE=s3
     RCLONE_CONFIG_OFFSITE_PROVIDER=Other
     RCLONE_CONFIG_OFFSITE_ENDPOINT=https://fsn1.your-objectstorage.com
     RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID=...
     RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY=...
     ```
3. Apply it: `vc up -d --build backup`. The first cycle runs at once; check **Settings → System → Backups** a minute later.

### Restoring

**On the same server** (a bad change, deleted data), from a local dump:
```bash
vc stop api worker frontend
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U vros -d vros --clean --if-exists --no-owner < vros-2026-10-08T020000Z.dump
vc start api worker frontend
```
(The local dumps are in `/var/lib/docker/volumes/verkies_backups/_data/`.)

**On a new server** (the old one is gone):
1. Set up the server, `.env` and DNS as in §1-4, but before the first full `up`, build the images and start only the database: `vc build && vc up -d postgres`.
2. Copy the private key to `~/verkies/restore/vros-backup-key.txt` on the server, then fetch and decrypt the newest copy. The backup image has rclone and age, and `.env` already describes the remote:
   ```bash
   vc run --rm --no-deps -v "$PWD/restore:/restore" --entrypoint /bin/sh backup \
     /ops/fetch-offsite.sh /restore/vros-backup-key.txt /restore
   ```
   It writes `restore/restore.dump` and, if documents were backed up then, `restore/restore-documents.tar.gz`.
3. Restore, then start everything (migrations run and find the schema current):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
     pg_restore -U vros -d vros --no-owner < restore/restore.dump
   vc up -d
   ```
4. Documents, if there were any:
   ```bash
   docker run --rm -v verkies_storage:/data -v "$PWD/restore:/restore" alpine:3.20 \
     tar -xzf /restore/restore-documents.tar.gz -C /data
   ```
5. Delete the private key and the decrypted files from the server: `rm -rf restore`.

**Server snapshots:** Hetzner Backups (step 1.7) also keeps daily snapshots of the whole server. A snapshot is the quickest way back from a broken server; the off-site copy is the way back from a lost one.

## 7a. Metrics and dashboards (optional)

Prometheus and Grafana run with the `observability` profile. Set `VROS_GRAFANA_PASSWORD` in `.env` (Grafana will not start without it), then:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile observability up -d
```

Both listen on the server's 127.0.0.1 only. From your computer, open a tunnel and browse to http://localhost:3002 (user `admin`):

```bash
ssh -L 3002:127.0.0.1:3002 -L 9090:127.0.0.1:9090 vros@<server-ip>
```

The **VROS overview** dashboard shows whether the API is up, work in hand, request rate and response times, the slowest routes, worker failures and how long since each daily job last succeeded. Alerts (API down, a dependency down, errors over 5%, slow responses, a daily job late, repeated worker failures, a long queue) show on Prometheus's Alerts page (http://localhost:9090/alerts) and as a count on the dashboard; they are not emailed.

## 8. If something is wrong

| Symptom | Check |
| --- | --- |
| Deploy stops at once with "set VROS_…" | A required value in `.env` is empty |
| `api` keeps restarting | `vc logs api`: the API refuses insecure production settings and says which |
| Browser shows a certificate error | DNS does not point at the server yet, or ports 80/443 are blocked in the Hetzner firewall; `vc logs caddy` |
| Research runs stay queued | `vc ps worker` and `vc logs worker` |

The database, Redis and API are never exposed to the internet; only Caddy listens on 80/443.
