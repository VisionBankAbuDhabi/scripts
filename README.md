# scripts

Operational helper scripts for Vision Bank services. Python 3.9+, standard library only.

## Setup

```bash
./setup.sh
source .venv/bin/activate
cp .env.example .env   # optional; API target is set via BASE_URL in each script
```

## Repo rules

- API scripts keep their target in one `BASE_URL` key (with port) and ask for confirmation before running (see `CLAUDE.md`).

## notification-service/upload_templates.py

Bulk-creates email templates through `POST /api/v1/templates` from a CSV shaped like the
`email_templates` table. Shows progress per template and writes run and failure logs to `./logs/`.

Template data lives in `notification-service/sourceData/email_templates_final.csv` and is read from there by default
(override with `--csv`). To change a template, edit that file and re-run; do not hand-edit the `{{variables}}`.

```bash
# validate the CSV only
python3 notification-service/upload_templates.py --dry-run

# upload
python3 notification-service/upload_templates.py --header "Authorization: Bearer <token>"
```

- Target is the `BASE_URL` key at the top of the script; it is printed and you must confirm. To change it, edit the key.
- 201 = created, 409 = already exists (skipped), anything else = failed. Safe to re-run.
- The CSV `id` column is ignored; the service generates the UUID.
- Exit code is 1 if any template failed.
