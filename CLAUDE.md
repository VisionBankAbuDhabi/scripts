# Repo rules

1. **Single `BASE_URL` key.** Every script that calls an API holds its target in exactly one
   module-level constant named `BASE_URL` (scheme + host + port, e.g. `"http://localhost:8080"`),
   near the top of the script. No separate port, no `--base-url` flag, no env var for it.
2. **Confirm before running.** Before any API call, print the base URL and ask
   `Are you sure you want to run the script on this base url? [y/N]`. Anything but y/yes aborts with a
   message telling the user to update the key `BASE_URL` in the script. Always ask, including on `--dry-run`.
   Reference implementation: `confirm_base_url()` in `notification-service/upload_templates.py`.
