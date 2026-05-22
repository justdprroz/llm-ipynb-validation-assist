# Backups and retention

Recommended defaults (basic retention, self-hosted):

| Store | Method | Hot retention | Cold / archive |
|-------|--------|---------------|----------------|
| MongoDB | `mongodump` hourly + daily full | 7 days local | 30 days off-host (rsync/S3) |
| MinIO | versioning + `mc mirror` / restic | 7 days | 30 days |
| Redis | AOF + periodic RDB (`redis-cli SAVE` cron) | 7 days | optional |

## Scripts

| Script | Purpose |
|--------|---------|
| [backup-mongo.sh](backup-mongo.sh) | `mongodump` to `./out/mongodb-YYYYMMDD-HHMM` |
| [backup-minio.sh](backup-minio.sh) | Mirror buckets via `mc mirror` (requires `mc` alias `gradelab`) |
| [backup-redis.sh](backup-redis.sh) | Trigger `BGSAVE` and copy `dump.rdb` from volume (see comments) |
| [restore-mongo.sh](restore-mongo.sh) | `mongorestore` from dump directory |

## Disaster recovery drills

- **Bi-weekly:** restore Mongo dump into empty container, spot-check collections counts vs production metrics.
- **Quarterly:** full stack restore (Mongo + MinIO + Redis) on isolated host using same Compose files.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` | `mongodb://root:changeme@mongodb:27017` | Root URI for dump/restore |
| `BACKUP_ROOT` | `/backup` | Host path for dumps (mount in Compose) |

Wire a cron container or host cron to run `backup-mongo.sh` daily.
