# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: June 2026 — PostgreSQL migration in progress; Oracle Cloud provisioning pending

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. In active use/development.

**Overall Health:** Functional and deployed. All core workflows work end-to-end. All medium-priority bugs resolved. Role-based permissions and user management UI complete. PostgreSQL migration partially complete — code ready, VM provisioning pending.

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

## In Progress

### PostgreSQL Migration + Hostinger VPS Deployment
**Status: 🔄 In Progress**

#### Code changes — ✅ Done (local, not yet deployed)
- `requirements.txt` — added `psycopg2-binary==2.9.10` and `dj-database-url==2.2.0`
- `config/settings.py` — `DATABASES` now reads `DATABASE_URL` env var; falls back to SQLite locally

#### Infrastructure — ⏳ Next milestone: Purchase Hostinger VPS KVM 4
- Oracle Cloud Free Tier dropped — capacity issues made provisioning unreliable
- Target: Hostinger VPS KVM 4, Ubuntu 24.04 LTS

#### Deployment phases (Hostinger)
| Phase | Task | Status |
|---|---|---|
| 1 | Purchase Hostinger VPS KVM 4, select Ubuntu 24.04 LTS | ⏳ Pending |
| 2 | Secure VM — firewall, SSH hardening, OS updates | ⏳ Pending |
| 3 | Install PostgreSQL, create DB and user | ⏳ Pending |
| 4 | Install Python, clone repo, configure Django env vars | ⏳ Pending |
| 5 | Configure Gunicorn as systemd service | ⏳ Pending |
| 6 | Configure Nginx as reverse proxy | ⏳ Pending |
| 7 | Domain + SSL via Let's Encrypt | ⏳ Pending |
| 8 | Production smoke test | ⏳ Pending |

---

## Pending Features

| Priority | Feature | File / Location | Notes |
|---|---|---|---|
| 🟢 LOW | **Password reset flow** | `apps/accounts/` | No self-service reset yet |
| 🟢 LOW | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW | **Bulk operations** | List views | Bulk activate/deactivate |

---

## Known Issues

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading
Uses join table PK, not Supplier PK. Display-only, low risk.

### 🟢 LOW: SQLite Still in Production
PostgreSQL code is ready but not deployed — still on SQLite until Hostinger VPS is provisioned and configured.

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

| Jun 2026 | **Deployment target changed** — Oracle Cloud dropped; Hostinger VPS KVM 4 (Ubuntu 24.04) adopted | `PROJECT_STATUS.md`, `CLAUDE.md` |

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

### Current (Render — being phased out)
- **Platform:** Render (free tier)
- **Database:** SQLite — resets on every deploy
- **Build script:** `build.sh`

### Target (Hostinger VPS — in progress)
- **Platform:** Hostinger VPS KVM 4 — Ubuntu 24.04 LTS
- **Stack:** Nginx → Gunicorn → Django → PostgreSQL (same VM)
- **SSL:** Let's Encrypt
- **Database:** PostgreSQL (persistent, no data loss on redeploy)

### Both environments
- **Default credentials:** `admin` / `changeme123` — change immediately
- **Timezone:** Asia/Kolkata (IST)
- **Env vars required:** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `DATABASE_URL`
- **User roles:** Set via User Management UI or Django admin → `is_staff` checkbox
- **Multi-user testing:** Use incognito window for second user

---

## Testing Notes

- **Run:** `python manage.py test apps.imports.tests`
- **Shell queries on Windows:** Use semicolons, not commas at top level:
  `python manage.py shell -c "from django.contrib.auth.models import User; u = User.objects.get(username='rose'); print(u.is_staff)"`
- **Multi-user testing:** Always use incognito/private window for the second account