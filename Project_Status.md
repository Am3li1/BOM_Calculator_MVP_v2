# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: July 2026 — Production deployment complete on Coolify/Docker/PostgreSQL, accessible via Tailscale HTTPS

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. **Deployed to production.**

**Overall Health:** Functional and deployed to production. All core workflows work end-to-end. All medium-priority bugs resolved. Role-based permissions and user management UI complete. PostgreSQL migration complete — live on Coolify-managed Postgres. App is reachable over Tailscale via HTTPS at `https://prod-node-01.tail7e0384.ts.net`.

---

## Completed Features

### Module: Authentication (`apps.accounts`)
**Status: ✅ Complete**
- Login/logout, `@login_required` on all views, auto-redirect authenticated users
- **User Management UI** — list, create, edit, change password (admin only)
- No self-deactivation — checkbox disabled when editing own account
- Roles set via `is_staff` toggle in user edit form

---

### Module: Core / Dashboard (`apps.core`)
**Status: ✅ Complete**
- 6 clickable stat cards: products, resources, BOM items, dimensions, suppliers, portfolio cost
- Recent products and resources tables
- `admin_required` decorator in `apps/core/decorators.py`

---

### Module: Role-Based Permissions
**Status: ✅ Complete**
- Two roles: **Admin** (`is_staff=True`) and **Viewer** (`is_staff=False`)
- `@admin_required` decorator — raises 403 if not staff
- Viewer: lists, detail pages, cost sheets, BOM view, import history
- Admin: all mutations, imports, supplier linking, user management
- 403 page at `templates/403.html`
- **Testing note:** Use incognito window to test different users simultaneously

---

### Module: Products (`apps.products`)
**Status: ✅ Complete**
- List (viewer), create/edit/delete/clone (admin only)

---

### Module: Resources (`apps.resources`)
**Status: ✅ Complete**
- List + detail (viewer), create/edit/delete/toggle/override (admin only)
- Rate priority chain: override → preferred supplier → lowest supplier → master rate

---

### Module: Suppliers (`apps.suppliers`)
**Status: ✅ Complete**
- List + detail (viewer), all mutations (admin only)
- Supplier detail stays on page after toggle

---

### Module: BOM Management (`apps.bom`)
**Status: ✅ Complete**
- BOM list (viewer), add/edit/remove (admin only)

---

### Module: Cost Sheets (`apps.costing`)
**Status: ✅ Complete**
- Cost sheet list and full cost sheet (viewer access)
- Per-product and full workbook Excel export

---

### Module: Excel Import (`apps.imports`)
**Status: ✅ Complete**
- Upload and import (admin only), history and result (viewer access)
- ImportLog in Django admin as view/delete only

---

### Pagination
**Status: ✅ Complete**
- Products, Resources, Suppliers: 25/page. Import History: 20/page
- Filters preserved across pages

---

### Unit Tests (`apps/imports/tests.py`)
**Status: ✅ 6 tests passing**
- Run: `python manage.py test apps.imports.tests`

---

## Completed: PostgreSQL Migration + Production Deployment

### Module: Deployment (Coolify / Docker / Tailscale)
**Status: ✅ Complete**

Deployment target changed from the originally planned Hostinger VPS to a **physical Debian 12 server in the client's Coimbatore office** (`prod-node-01`), managed via **Coolify** and accessed exclusively over **Tailscale** (no public internet exposure).

#### Code changes
- `requirements.txt` — `psycopg2-binary==2.9.10`, `dj-database-url==2.2.0`
- `config/settings.py` — `DATABASES` reads `DATABASE_URL` env var; falls back to SQLite locally
- `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh` — reviewed and corrected for production use

#### Infrastructure
- **Server:** Debian 12, hostname `prod-node-01.tail7e0384.ts.net`, Tailscale IP `100.75.145.23`
- **Access:** SSH key auth, passwordless sudo for `santosh`; app reachable only to devices on the tailnet
- **Coolify:** v4.1.2, Docker-based orchestration, GitHub-integrated auto-build from `Am3li1/BOM_Calculator_MVP_v2` (branch `main`)
- **Database:** PostgreSQL 16-alpine, Coolify-managed Docker resource, persistent volume
- **Reverse proxy / TLS:** Traefik (Coolify-managed) for internal routing; **Tailscale Serve** terminates HTTPS with an auto-issued trusted cert for `prod-node-01.tail7e0384.ts.net`

#### Deployment phases — all complete
| Phase | Task | Status |
|---|---|---|
| 1 | Create PostgreSQL resource in Coolify | ✅ Done |
| 2 | Create Django application resource (GitHub source) | ✅ Done |
| 3 | Configure environment variables (`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`) | ✅ Done |
| 4 | Deploy application (Docker build + rolling update) | ✅ Done |
| 5 | Verify migrations, static files, login, admin | ✅ Done |
| 6 | Confirm final URL, review settings | ✅ Done |
| 7 | Clarify access model — Tailscale membership = access control | ✅ Done |
| 8 | Enable HTTPS via Tailscale Serve | ✅ Done |

#### Issues encountered and resolved during deployment
1. **Permission denied writing Coolify-managed directories** (`/data/coolify/databases/...`, `/data/coolify/applications/...`) — root cause: `/data/coolify` and its subdirs are owned by uid `9999` with mode `700`, blocking traversal for the `santosh` SSH user Coolify automation runs as. Fixed with targeted `setfacl` (traverse-only on parents) and `chown` (ownership on the specific resource dirs — `9999`/uid `70` for Postgres-owned paths, `santosh` for app `.env` writes).
2. **`santosh` missing from `docker` group** — caused `permission denied` on direct `docker` CLI use and likely contributed to inconsistent automation behavior. Fixed with `usermod -aG docker santosh`.
3. **App unreachable externally on port 8000** — Coolify doesn't map container ports to the host directly; traffic routes through Traefik by hostname. Resolved by using Coolify's auto-assigned `sslip.io` domain and adding it to `ALLOWED_HOSTS`.
4. **`400 Bad Request` (DisallowedHost)** — `ALLOWED_HOSTS` didn't include the sslip.io domain; fixed by updating the env var and redeploying (env var changes require an explicit redeploy to regenerate `.env`).
5. **App unreachable from devices outside the tailnet** — expected behavior, not a bug; confirmed the access model (Tailscale membership required) and documented it as the intended security boundary.
6. **HTTPS via `tailscale serve` initially failed ("Serve is not enabled on your tailnet")** — root cause: the Tailscale Serve enablement link was opened while logged into the wrong Tailscale account (`Am3li1@github` instead of `visanty@`, the account that owns `prod-node-01`). Fixed by re-enabling Serve while logged into the correct account.
7. **`403 CSRF verification failed` after enabling HTTPS** — `CSRF_TRUSTED_ORIGINS` only had `http://` entries; added the `https://prod-node-01.tail7e0384.ts.net` origin and redeployed.

---

## Pending Features

| Priority | Feature                             | File / Location                             | Notes                                                                                                                                                                                                                                 |
| -------- | ----------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🔴 HIGH  | **Parts Module & BOM Integration**  | `apps/bom`, `apps/imports`, `apps/products` | Add support for the **Parts** sheet from the Excel workbook. Display product parts (e.g. Table Top, Leg 1–4, Side Panel) within the BOM and link Wood/Ply/MDF entries to their respective parts. No separate sidebar module required. |
| 🔴 HIGH  | **Modern UI Redesign (Dark Theme)** | Global templates & static assets            | Redesign the application with a modern dark theme, improved typography, spacing, cards, tables, forms, and responsive layout while preserving existing functionality.|
| 🟢 LOW   | **Password reset flow** | `apps/accounts/` | No self-service reset yet |
| 🟢 LOW   | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW   | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW   | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW   | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW   | **Bulk operations** | List views | Bulk activate/deactivate |

---
## Next Development Goal

### Phase 1 – Parts Integration

The original Excel workbook contains a **Parts** sheet.

Additionally, the **Wood** and **Ply MDF** sheets reference a **Part** column.

The application should support this workflow.

Requirements:

* Import the Parts sheet.
* Associate Wood/Ply/MDF records with a Part.
* Display Parts inside the BOM.
* Example:

Table

* Table Top
* Leg 1
* Leg 2
* Leg 3
* Leg 4

Each Wood/Ply/MDF item should clearly indicate which product part it belongs to.

No standalone "Parts" page or sidebar item is required.

Parts exist only to organize the BOM and improve manufacturing clarity.

---

### Phase 2 – UI Modernization

After the Parts feature is complete:

Redesign the entire application.

Goals:

* Modern dark theme
* Better spacing
* Improved typography
* Cleaner forms
* Better tables
* Better cards
* Consistent icons
* Professional dashboard
* Improved responsive layout

The redesign should preserve all existing functionality while significantly improving the user experience.

## Known Issues

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading
Uses join table PK, not Supplier PK. Display-only, low risk.

### ~~🟢 LOW: SQLite Still in Production~~ — Resolved
App now runs on Coolify-managed PostgreSQL in production; SQLite is local-dev fallback only.

### 🟢 LOW: No CSRF Audit on Quick-Action Forms
Inline POST forms should be audited for `{% csrf_token %}` before production.

### 🟢 LOW: WoodPart part_name Fallback Risk
If "Parts" column is empty, multiple cuts of same material overwrite each other on re-import.

---

## Technical Debt

1. **`WoodPart.calculated_quantity` imports `SystemConfig` inside the property** — should be module-level.
2. **Float/Decimal mixing in WoodPart views** — precision risk.
3. **`bom_item.cost` summed in Python, not SQL** — will degrade with large BOMs.
4. **No `select_related` on BOM list for supplier links** — potential N+1 queries.
5. **`_make_product_code` collision risk** — "TEAK WOOD" and "TEAK-WOOD" both produce "TEAK-WOOD".
6. **`category` on Resource is a plain CharField** — can create categories not in `ResourceCategory`.
7. **Portfolio cost on dashboard** summed in Python — acceptable for MVP.

---

## Recent Changes Log

| Jul 2026 | Roadmap updated for Version 2 — Next priority is Parts Module and UI/UX redesign after successful production deployment | PROJECT_STATUS.md |
| Jul 2026 | **Production deployment completed** — Coolify + Docker + PostgreSQL on Debian 12 (`prod-node-01`), accessed via Tailscale HTTPS (`tailscale serve`) | `PROJECT_STATUS.md`, `CLAUDE.md`, Coolify env vars |
| Jul 2026 | **Deployment target changed again** — Hostinger VPS plan replaced by client's physical Debian 12 office server, managed via Coolify | `PROJECT_STATUS.md`, `CLAUDE.md` |
| Jun 2026 | **Deployment target changed** — Oracle Cloud dropped; Hostinger VPS KVM 4 (Ubuntu 24.04) adopted *(superseded — see above)* | `PROJECT_STATUS.md`, `CLAUDE.md` |

| Date | Change | Files |
|---|---|---|
| Jun 2026 | **PostgreSQL deps added** — `psycopg2-binary`, `dj-database-url` | `requirements.txt` |
| Jun 2026 | **Settings updated for PostgreSQL** — reads `DATABASE_URL`, SQLite fallback for local dev | `config/settings.py` |
| Jun 2026 | **User Management UI** — list, create, edit, change password; sidebar link | `apps/accounts/views.py`, `apps/accounts/urls.py`, 3 new templates, `base.html` |
| Jun 2026 | **Fixed self-deactivation check** — moved inside `if request.method == 'POST'` | `apps/accounts/views.py` |
| Jun 2026 | **Role-based permissions** — `@admin_required` decorator; 403 template | `apps/core/decorators.py`, all `views.py` files, `templates/403.html` |
| Jun 2026 | **Dashboard enhancements** — supplier count, portfolio cost, clickable cards | `apps/core/views.py`, `templates/core/dashboard.html` |
| Jun 2026 | **Pagination** — 25/page lists, 20/page import history | 4 views, 4 templates, `partials/pagination.html` |
| Jun 2026 | **Supplier detail stay-on-page after toggle** | `apps/suppliers/views.py`, `templates/suppliers/supplier_detail.html` |
| Jun 2026 | **ImportLog admin registration** | `apps/imports/admin.py` |
| Jun 2026 | **Fixed WoodPart re-import duplication** | `apps/imports/services.py` |
| Jun 2026 | Supplier Detail Page, redirect bug fix, Excel Export | Various |

---

## Deployment Notes

### Production (live)
- **Platform:** Physical Debian 12 server, client's Coimbatore office (`prod-node-01`), managed via Coolify v4.1.2
- **Stack:** Tailscale Serve (HTTPS) → Traefik (Coolify) → Gunicorn → Django → PostgreSQL 16-alpine (Docker, Coolify-managed)
- **SSL:** Tailscale Serve auto-issued cert (tailnet-only trust, no public CA needed)
- **Database:** PostgreSQL, persistent Docker volume, no data loss on redeploy
- **URLs:** `https://prod-node-01.tail7e0384.ts.net` (primary), `http://otiwlmrwnyx3j1r42w7qe23r.100.75.145.23.sslip.io` (fallback)
- **Access control:** Tailscale tailnet membership — devices without Tailscale cannot reach the server at all, regardless of physical network

### Render (retired)
- Previously used for early MVP hosting on SQLite (free tier, data reset every deploy). Fully replaced by the Coolify deployment above.

### Hostinger VPS (superseded, never provisioned)
- Was the planned target before the client's on-prem Debian server + Coolify became the actual deployment path. No infrastructure was purchased under this plan.

### Current environment
- **Default credentials:** superuser created manually post-deploy — change immediately
- **Timezone:** Asia/Kolkata (IST)
- **Env vars required (Coolify):** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`
- **User roles:** Set via User Management UI or Django admin → `is_staff` checkbox
- **Multi-user testing:** Use incognito window for second user

---

## Testing Notes

- **Run:** `python manage.py test apps.imports.tests`
- **Shell queries on Windows:** Use semicolons, not commas at top level:
  `python manage.py shell -c "from django.contrib.auth.models import User; u = User.objects.get(username='rose'); print(u.is_staff)"`
- **Multi-user testing:** Always use incognito/private window for the second account