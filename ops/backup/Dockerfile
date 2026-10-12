# The backup service (slice 7.2): PostgreSQL client tools from the same image as the database,
# plus age (encrypts off-site copies to a public key) and rclone (uploads them).
FROM pgvector/pgvector:pg16

RUN apt-get update \
    && apt-get install -y --no-install-recommends age rclone ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backup.sh restore-drill.sh fetch-offsite.sh /ops/
ENTRYPOINT ["/bin/sh", "/ops/backup.sh"]
