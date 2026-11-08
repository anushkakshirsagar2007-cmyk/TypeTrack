# TypeTrack

TypeTrack is a Flask application for managing institute inquiries, students, batches, attendance, fees, receipts and reports.

## Vercel deployment

The root `app.py` is the Flask entry point Vercel detects. Vercel serves `public/static/` assets from its CDN; keep this directory in sync with `static/` for local development. Student and institute records use Supabase PostgreSQL; institute logos use a private Supabase Storage bucket.

1. Create a private Supabase Storage bucket named `typetrack-uploads`.
2. In Supabase's **Connect** panel, copy the PostgreSQL **Transaction pooler** URI. Keep TLS enabled with `sslmode=require`; URL-encode special characters in the password.
3. Push the contents of this project folder to the root of a private GitHub repository. Do not upload `.env`, local databases or real institute data. `.gitignore` excludes local secrets and databases.
4. Import the repository in Vercel. Use the repository root as the project root. Vercel detects Flask from `app.py`; no start command is needed. The Python version is pinned in `.python-version`.
5. Add these private Production environment variables in Vercel:
   - `DATABASE_URL`: the Supabase Transaction pooler URI.
   - `SUPABASE_URL`: `https://<project-ref>.supabase.co`.
   - `SUPABASE_SERVICE_ROLE_KEY`: the private service-role key. Keep it server-side; never put it in browser code or Git.
   - `SUPABASE_STORAGE_BUCKET`: `typetrack-uploads`.
   - `SECRET_KEY`: a random secret of at least 32 characters.
   - `SESSION_COOKIE_SECURE`: `1`.
   - `OWNER_NAME`, `OWNER_USERNAME`, and a unique `OWNER_PASSWORD` of at least 12 characters.
   - Optional `INSTITUTE_*` values for the first database initialization.
6. Redeploy after saving the environment variables. Link the project folder with the Vercel CLI, then initialize the new database once:
   `vercel env run -e production -- python -m flask --app app init-db`
7. Test owner login, record creation, logo upload, and receipt PDF generation using the Vercel HTTPS URL. Enable Supabase backups and test restoring them before entering real records.

Never run the demo-data command on the live project. Vercel's local filesystem is temporary; the app uses Supabase Storage for logos. Back up the database and storage objects before application updates. TypeTrack does not yet include a database migration workflow.

## Development and tests

Install `requirements.txt`, then run:

```text
python tests/test_app.py
```

The tests use a temporary SQLite database and include demo records only in that test database. Do not run `seed-demo` on production.
