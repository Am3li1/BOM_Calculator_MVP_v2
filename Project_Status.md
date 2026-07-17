# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: July 2026 — Dimension formula split (CFT/SFT by material type) and BOM UI fixes complete, on top of production deployment on Coolify/Docker/PostgreSQL, accessible via Tailscale HTTPS

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. **Deployed to production.**

**Overall Health:** Functional and deployed to production. All core workflows work end-to-end. All medium-priority bugs resolved. Role-based permissions and user management UI complete. PostgreSQL migration complete — live on Coolify-managed Postgres. App is reachable over Tailscale via HTTPS at `https://prod-node-01.tail7e0384.ts.net`. WoodPart costing now correctly distinguishes solid wood (CFT) from sheet goods (SFT) by material type, with full unit conversion and import-time validation.

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
- **Parts integration complete** — `Part` model organizes WoodPart entries per product (e.g. Table Top, Leg 1–4); BOM list groups dimension rows by part with item counts. Imported via the `Parts` sheet (`apps/imports/services.py: import_parts`) or created inline from the WoodPart add form.

---

### Module: Dimension Formula Split by Material Type (`apps.bom`, `apps.resources`, `apps.imports`)
**Status: ✅ Complete**

Previously, `WoodPart.calculated_quantity` used one formula for every material and ignored the per-dimension unit fields entirely (numbers were used as-is, no `in`/`ft`/`mm`/etc conversion). This has been replaced with a material-aware split:

- **`Resource.material_type`** — new field (`solid_wood` / `sheet` / `other`), since `Resource.category` alone can't distinguish them (e.g. "Carpentry Materials" holds both Teak and Plywood).
- **Solid wood → CFT:** `(Width_in × Breadth_in × Length_ft × Pieces) / wood_divisor`, with real unit conversion via new `apps/core/units.py` (`to_inches`/`to_feet`).
- **Sheet goods (Plywood/MDF/PLPB) → SFT:** `Width_ft × Breadth_ft × Pieces` — **no divisor, Length unused** (confirmed against real production data; Breadth drives the second dimension, not Length).
- **`'other'` (unclassified resources)** keep the old unit-naive formula unchanged, so reclassifying nothing doesn't silently change existing costs.
- **Import validation** (`validate_wood`) now rejects rows with missing/invalid `WU`/`BU`/`LU` unit cells — except it correctly skips the Length-unit check for `sheet` rows, since Length is legitimately unused there (real sheets in the reference workbook use `LU='no'` as a placeholder).
- **Resource form** (`apps/resources/forms.py`) now exposes `material_type` directly (previously only settable via Django admin/shell) and auto-suggests a Unit (`cft`/`sqft`) when it's changed.
- **Dimension add/edit forms** — Material field replaced with a type-to-filter, scrollable combobox (vanilla JS, no framework) that auto-defaults the Width/Breadth/Length unit dropdowns based on the selected resource's `material_type`, and greys out the Length field (readonly, with an explanatory hint) for sheet materials.
- **BOM list table bug fixed** — dimension rows had one more `<td>` than the table had `<th>` columns (a stray icon cell), silently shifting every value one column right (Width showing under Breadth, etc). Fixed by merging the icon into the Material cell.
- **Regression tests added:** `apps/bom/tests.py` (formula correctness, unit-conversion equivalence, sheet-ignores-Length), `apps/core/tests.py` (unit conversion utility), `apps/imports/tests.py` (unit validation, including the `LU='no'` sheet-goods edge case). 20 tests total, all passing.

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

### Unit Tests
**Status: ✅ 20 tests passing** (across `apps/bom`, `apps/core`, `apps/imports`)
- Run (Windows requires full dotted paths, not package names):
  `python manage.py test apps.bom.tests apps.core.tests apps.imports.tests`
- `apps/bom/tests.py` — CFT/SFT formula correctness, unit-conversion equivalence, sheet-goods ignoring Length, legacy `'other'` fallback (5 tests)
- `apps/core/tests.py` — `to_inches`/`to_feet` conversion utility, invalid-unit rejection (5 tests)
- `apps/imports/tests.py` — original 6 (effective rate chain, BOM cost, `_sheet_exists`) + 4 new (`validate_wood` unit checks, including the sheet-goods `LU='no'` edge case)

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
| 🔴 HIGH  | **Modern UI Redesign (Dark Theme)** | Global templates & static assets            | Redesign the application with a modern dark theme, improved typography, spacing, cards, tables, forms, and responsive layout while preserving existing functionality. Dimension add/edit forms and the BOM list table got targeted layout/sizing fixes this session — the broader global redesign is still pending.|
| 🟢 LOW   | **Password reset flow** | `apps/accounts/` | No self-service reset yet |
| 🟢 LOW   | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW   | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW   | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW   | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW   | **Bulk operations** | List views | Bulk activate/deactivate |

---
## Next Development Goal

### ~~Phase 1 – Parts Integration~~ ✅ Complete

The `Part` model, Parts sheet import, WoodPart↔Part linking, and BOM-list grouping by part are all done — see the *Dimension Formula Split* and *BOM Management* sections above.

---

### Phase 2 – UI Modernization

Now that Parts integration and the dimension formula/UI work are complete:

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

1. ~~**`WoodPart.calculated_quantity` imports `SystemConfig` inside the property**~~ — unchanged in this session, still applies only to the `solid_wood` and `'other'` branches (which need the divisor); the `sheet` branch doesn't call `SystemConfig` at all since it has no divisor.
2. **Float/Decimal mixing in WoodPart views** — precision risk.
3. **`bom_item.cost` summed in Python, not SQL** — will degrade with large BOMs.
4. **No `select_related` on BOM list for supplier links** — potential N+1 queries.
5. **`_make_product_code` collision risk** — "TEAK WOOD" and "TEAK-WOOD" both produce "TEAK-WOOD".
6. **`category` on Resource is still a plain CharField** — can create categories not in `ResourceCategory`. Partially mitigated: material classification (CFT vs SFT vs other) now lives on `Resource.material_type` instead of depending on category, since a single category ("Carpentry Materials") holds both Teak and Plywood. The underlying free-text `category` field itself is unchanged.
7. **Portfolio cost on dashboard** summed in Python — acceptable for MVP.
8. **Resource combobox on WoodPart forms loads the full resource list client-side as JSON** — fine at current catalog size (~150 resources); would need server-side search/pagination if the resource count grows substantially.
9. **`validate_wood`'s material-type-aware unit checks only recognize resources already saved in the DB** — a resource being imported for the first time in the same workbook as its dimensions falls back to strict (solid-wood-style) validation, since its `material_type` isn't known yet at validation time. Not an issue if Resources are always imported before Wood/Dimensions, which is the existing workflow.

---

## Recent Changes Log

| Jul 2026 | **Dimension formula split by material type (CFT vs SFT)** — `Resource.material_type` field added; `WoodPart.calculated_quantity` branches solid_wood (unit-converted CFT) / sheet (Width×Breadth SFT, no divisor, Length unused) / other (legacy unit-naive formula preserved) | `apps/resources/models.py`, `apps/bom/models.py`, new `apps/core/units.py` |
| Jul 2026 | **Import validation extended** — `validate_wood` rejects invalid/missing `WU`/`BU`/`LU` unit cells, skipping the Length-unit check for sheet-material rows (Length is unused there); `import_wood` simplified to trust validated units instead of silently defaulting | `apps/imports/services.py` |
| Jul 2026 | **Resource form exposes `material_type`** — previously only settable via Django admin/shell; now a dropdown on the Resource create/edit form that auto-suggests a Unit (`cft`/`sqft`) | `apps/resources/forms.py`, `templates/resources/form.html` |
| Jul 2026 | **WoodPart add/edit forms redesigned** — Material `<select>` replaced with a type-to-filter, scrollable combobox (vanilla JS); Width/Breadth/Length units auto-default based on the selected resource's `material_type`; Length field greys out (readonly) for sheet materials; layout/font fixes (top-aligned dimension rows, larger/thinner fields); product code removed from page headers | `apps/bom/views.py`, `templates/bom/woodpart_add.html`, `templates/bom/woodpart_edit.html` |
| Jul 2026 | **Fixed BOM list dimensions table column-shift bug** — an extra `<td>` (arrow icon) with no matching `<th>` was silently shifting every value one column right (Width showing under Breadth, etc); merged into the Material cell | `templates/bom/list.html` |
| Jul 2026 | **Regression test suite added** — 20 tests total across formula correctness, unit conversion, and import unit validation | `apps/bom/tests.py`, `apps/core/tests.py`, `apps/imports/tests.py` |
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

- **Run:** `python manage.py test apps.bom.tests apps.core.tests apps.imports.tests`
- **Windows gotcha:** passing just the package name (e.g. `apps.bom` instead of `apps.bom.tests`) crashes with `TypeError: _getfullpathname: path should be string, bytes or os.PathLike, not NoneType` — always use the full dotted path down to the `tests` module.
- **Shell queries on Windows:** Use semicolons, not commas at top level:
  `python manage.py shell -c "from django.contrib.auth.models import User; u = User.objects.get(username='rose'); print(u.is_staff)"`
- **Multi-user testing:** Always use incognito/private window for the second account