# CLAUDE.md — BOM Costing System

> **Purpose:** Long-term project context for Claude Code sessions.
> Read this file first before making any changes. Update when architecture changes.

---

## Project Overview

A **Product Costing & Bill of Materials (BOM) Management System** built for furniture/woodworking manufacturers (context: India, INR currency ₹). It allows users to:

- Define products (e.g. 3-Door Wardrobe, Coffee Table)
- Manage raw materials, labour, and overhead resources with pricing
- Build Bills of Materials (quantities per product)
- Enter dimensional data (WxBxL) for wood/ply/MDF parts
- Track suppliers and link them to resources with per-supplier pricing
- View auto-calculated cost sheets per product
- Bulk-import all data via Excel workbooks
- Export cost sheets and full data workbooks to Excel

**Target user:** Small-to-medium furniture manufacturer, internal staff only (no public access).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | Django 5.0.6 |
| Database | SQLite (MVP; Render resets on every deploy) |
| Frontend | Bootstrap 5.3.2 + Bootstrap Icons 1.11.3 |
| Font | Inter (Google Fonts, CDN) |
| Static files | WhiteNoise 6.12.0 |
| Excel I/O | pandas 2.3.3 + openpyxl 3.1.5 |
| Config | python-decouple 3.8 |
| WSGI server | Gunicorn 26.0.0 |
| Deployment | Render (PaaS) |

**No JavaScript frameworks.** All interactivity is server-side Django + Bootstrap. No REST API. No Celery/background tasks.

---

## Project Structure

```
bom_costing/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/             # Dashboard, SystemConfig, decorators, template tags
│   ├── accounts/         # Login/logout (Django auth, no registration)
│   ├── products/         # Product CRUD + soft delete + clone
│   ├── resources/        # Resource CRUD + categories + supplier linking
│   ├── suppliers/        # Supplier CRUD + ResourceSupplier join table
│   ├── bom/              # BOMItem + WoodPart CRUD
│   ├── costing/          # Cost sheet views + Excel export
│   └── imports/          # Excel import service + logs
├── templates/
│   ├── base.html
│   ├── 403.html          # Permission denied page
│   ├── partials/
│   │   └── pagination.html
│   └── [app]/
├── static/
├── media/
├── build.sh
├── requirements.txt
└── manage.py
```

---

## Application Modules

### `apps.core`
- **SystemConfig** — singleton model (pk=1). Stores `company_name` and `wood_divisor` (default 144). Call `SystemConfig.get_config()` everywhere.
- **Dashboard view** — 6 clickable stat cards + recent products/resources tables.
- **`decorators.py`** — `admin_required` decorator for staff-only views (see Permissions section).
- **`custom_filters`** templatetag — `get_item` filter for dict lookups by variable key.
- **`create_default_superuser`** management command.

### `apps.accounts`
- Login/logout only. Uses Django's built-in `authenticate`/`login`/`logout`.
- No user registration, no password reset (MVP).
- All views behind `@login_required`.

### `apps.products`
- **Product** model: `product_name`, `product_code`, `active`, `is_deleted`.
- Soft delete, product code uniqueness among non-deleted records only.
- Clone: copies product + all BOMItems + all WoodParts atomically.

### `apps.resources`
- **ResourceCategory** — DB-managed, admin-editable.
- **Resource** model: `resource_name`, `category`, `unit`, `rate`, `manual_override_rate`, `override_reason`, `active`.
- Rate priority chain: override → preferred supplier → lowest supplier → master rate.
- `effective_rate` and `effective_rate_source` properties.

### `apps.suppliers`
- **Supplier** model: `supplier_name`, `phone_number`, `gst_number`, `active`.
- **ResourceSupplier** join table: `resource`, `supplier`, `supplier_rate`, `preferred`, `active`.
- First supplier linked → auto-preferred. Remove preferred → auto-promote cheapest.

### `apps.bom`
- **BOMItem**: product + resource + quantity. Cost calculated live via `effective_rate`.
- **WoodPart**: product + resource + part_name + W/B/H/L/pieces + formula_type.
- Formula types: `standard` (W×B×H×L×pcs ÷ divisor), `area` (W×L×pcs ÷ divisor).
- `unique_together` on BOMItem — one resource per product in standard BOM.

### `apps.costing`
- Pure calculation views — no models.
- `costing_list`: all active products.
- `cost_sheet`: full cost breakdown grouped by category. Grand total = Standard BOM + Dimensional BOM.
- WoodParts shown for reference, NOT added to grand total.
- Excel export: per-product at `/costing/<pk>/export/`; full workbook at `/costing/export/full/`.

### `apps.imports`
- **ImportLog** — registered in Django admin as view/delete only (no add/edit).
- Two-phase import: validate → import atomically.
- `SHEET_REGISTRY` in `services.py` for extensibility.
- WoodPart import uses `update_or_create` keyed on `(product, resource, part_name)`.

---

## Permissions

### Two roles — no new models, no migrations needed

| Role | Django field | Access |
|---|---|---|
| **Viewer** | `is_staff=False` | Read-only: lists, detail pages, cost sheets, BOM view, import history |
| **Admin** | `is_staff=True` | Everything: create, edit, delete, toggle, clone, import, supplier linking |

### Decorators

```python
# apps/core/decorators.py
from apps.core.decorators import admin_required

# Read-only views — any authenticated user
@login_required
def product_list(request): ...

# Mutating views — staff only
@login_required
@admin_required          # ← goes BELOW @login_required
def product_create(request): ...
```

`@admin_required` raises `PermissionDenied` (→ 403) if `request.user.is_staff` is False (or the user is a carpenter).
`@login_required` must still be present — it handles unauthenticated users before `@admin_required` runs.

**Every view outside `apps.carpenter` must also carry `@not_carpenter`**, directly below `@login_required`:

```python
@login_required
@not_carpenter
@admin_required          # only on mutating views
def product_create(request): ...
```

**Only exception:** `carpenter:link_form` (public magic-link form, no login — see Carpenter Entry).

`apps/accounts/tests.py: CarpenterLockoutTests` walks the URL resolver and fails if any URL in the pre-existing app namespaces doesn't return 403 to a carpenter (GET and POST). When adding a **new app** that carpenters must not see, add its namespace to `BLOCKED_NAMESPACES` there. Carpenter-area views use `@carpenter_required` (carpenter + admin) instead.

### Setting roles
Via Django admin → Users → edit user → check/uncheck "Staff status".

### 403 page
`templates/403.html` — rendered automatically by Django on `PermissionDenied`.

---

## Critical Business Rules

1. **Cost is never stored.** `BOMItem.cost = quantity × resource.effective_rate`. Rate changes affect all products immediately.
2. **Grand total = Standard BOM only.** WoodPart cost is already captured in BOM — adding both double-counts.
3. **Soft delete products only.** Never hard-delete products.
4. **Resource uniqueness** = `(resource_name, category)` pair.
5. **Product code uniqueness** = among non-deleted products only.
6. **Preferred supplier auto-management**: first link → auto-preferred; remove preferred → auto-promote cheapest.
7. **wood_divisor** — never hardcode 144. Always read from `SystemConfig.get_config()`.
8. **Import is atomic** — any failure after validation rolls back the entire transaction.

---

## Cost Calculation Rules

### Resource Effective Rate (single source of truth)

```
Priority 1: resource.manual_override_rate  (if not None)
Priority 2: preferred supplier rate         (ResourceSupplier where preferred=True, active=True)
Priority 3: lowest active supplier rate     (cheapest active ResourceSupplier)
Priority 4: resource.rate                   (master rate — fallback when no suppliers)
```

Use `resource.effective_rate` everywhere. Use `resource.effective_rate_source` for UI display.

### BOMItem Cost
```python
cost = bom_item.quantity * resource.effective_rate  # confirmed correct, tested
```

### WoodPart Cost
```python
cost = calculated_quantity * resource.effective_rate  # confirmed correct, tested
```

### WoodPart Calculated Quantity
```python
# Standard: quantity = (W × B × H × L × Pieces) / wood_divisor
# Area:     quantity = (W × L × Pieces) / wood_divisor
# H defaults to 1 if 0 or not provided
```

---

## Import / Export Rules

### Import sheet requirements

| Sheet | Required Columns | Notes |
|---|---|---|
| `Resource` | Resource, Category, Units, Rate | header row 0. Optional: `Tamil Name`, `Aliases` — only non-blank cells overwrite; workbooks without them import unchanged |
| `Products` | (column A, no header) | skips: column1, products, select, '' |
| `BOM` | Product, Resource, Quantity | Product column forward-filled |
| `Wood, Ply MDF` | Product, Resource, Width, Breath, Length | "Breath" — typo in spec, must match |
| `Suppliers` | Supplier Name, Supplier Mobile | header=1 (row 0 is 'Table 1') |

### Upsert behaviour

| Sheet | Key | Behaviour |
|---|---|---|
| Resources | (name, category) | updates unit/rate if exists |
| Products | code | restores soft-deleted if same code |
| BOM | (product, resource) | updates quantity if exists |
| WoodParts | (product, resource, part_name) | updates dimensions if exists |
| Suppliers | name | updates phone if exists |

### Export
7-sheet workbook: Products, Resources, Suppliers, SupplierRates, BOM, Dimensions, CostSummary.

---

## Pagination

- Products, Resources, Suppliers: 25 per page
- Import History: 20 per page
- Partial: `templates/partials/pagination.html` — include after table, before `{% else %}` empty state
- Uses `{% query_string page=N %}` to preserve search/filter params across pages

---

## Coding Standards

- **Function-based views only.**
- **`@login_required` on every view.** Mutating views also get `@admin_required` (below `@login_required`).
- **POST-only for mutations.** Never GET for delete/toggle/link.
- **Decimal for all money.**
- **`transaction.atomic()`** for multi-model writes.
- **`select_related`** on FKs in list views.
- **Bootstrap 5** in templates.
- **`messages` framework** for all user feedback.
- **App namespace** in every `urls.py`. Use `{% url 'app:name' %}` in templates.
- **No hardcoded rates or divisors.**
- **Global template dir** (`templates/` in project root).

---

## Testing

- **Run:** `python manage.py test apps.accounts.tests apps.core.tests apps.imports.tests apps.bom.tests apps.products.tests apps.resources.tests apps.suppliers.tests apps.costing.tests apps.carpenter.tests` (full dotted paths on Windows)
- Security-critical: `apps.accounts.tests.CarpenterLockoutTests` — every pre-existing URL returns 403 to a carpenter. Never weaken or skip it.
- Known stale tests (6, pre-date the Carpenter work): `products.ProductListPaginationTests` ×2, `suppliers.SupplierViewsTests` ×2 log in as non-staff against now admin-only views; `resources.ResourceFormFormulaExpressionTests` ×2 test a removed formula field.
- Add tests alongside new features, especially cost calculation changes.

---

## Development Constraints

- **SQLite only** for MVP. Limited concurrent write support.
- **No async/Celery** — synchronous only.
- **No REST API** — server-rendered HTML only.
- **Media files not persisted on Render.**
- **`staticfiles/` is generated** — do not edit directly.

---

## Deployment Information
- **Platform:** Contabo VPS, deployed and managed via **Coolify**
- **Stack:** Public internet → Traefik (Coolify's reverse proxy, Let's Encrypt TLS) → Gunicorn → Django → PostgreSQL (Docker container, Coolify-managed)
- **Containerization:** Docker, built from repo's `Dockerfile` via Coolify's GitHub integration (`Am3li1/BOM_Calculator_MVP_v2`, branch `main`)
- **Entrypoint:** `docker-entrypoint.sh` — waits for Postgres, runs migrations, collectstatic, then Gunicorn
- **Database:** PostgreSQL 16-alpine, Coolify-managed Docker resource — persistent volume, no data loss on redeploy
- **Access model:** App is publicly reachable over HTTPS. There is no network-level access control — **authentication is the only access control** (see Security section below).
- **URL:** `https://bom.lumelabs.dev` (primary, Coolify-managed Let's Encrypt cert)
- **Default superuser:** created manually via `docker exec ... python manage.py createsuperuser` — change credentials as needed.
- **Env vars required (set in Coolify UI):** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (points to internal Docker network container name, not host IP). Optional: `BOM_ASSISTANT_API_KEY` (enables the BOM voice assistant), `BOM_ASSISTANT_BASE_URL`, `BOM_ASSISTANT_MODEL`.
- **Timezone:** `Asia/Kolkata` (IST)
- **User roles:** Set via the Authentication section below (Admin / Viewer / Carpenter).

---

## Security

The app is **public-internet-facing** (no VPN/tailnet/IP allowlist in front of it). Authentication is therefore the only access control, and it must be treated as security-critical, not incidental.

Rules:
1. **No MFA (removed by owner decision, Nov 2026).** Login is username + password (or Google sign-in for allow-listed admins). Admins can see all costs/rates and mutate all data, so admin passwords must be strong and unique; the lockout below is the main brute-force defence.
2. **Account lockout on repeated failed logins** (django-allauth / django-axes style rate limiting) — mitigates credential-stuffing and brute force against a publicly reachable login page.
3. **No rates or costs are ever visible to the Carpenter role.** Carpenter-facing views/templates/serializers must not include `resource.rate`, `effective_rate`, `BOMItem.cost`, `WoodPart` cost, or any cost-sheet data — enforced server-side, not just hidden in the template.
4. **Every view enforces its role check server-side.** Never rely on hiding a link/button in a template as the only protection — a Carpenter or Viewer hitting a URL directly must be blocked by the view itself (decorator or explicit check), same pattern as `@admin_required` today.
5. **HTTPS-only cookies.** `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True` in production settings, since there's no longer a trusted private network fallback.
6. **`DEBUG = False` in production, always.** A public-facing Django app with `DEBUG=True` leaks stack traces, settings, and source snippets to anyone who can trigger a 500.

---

## Authentication

Auth is built on **django-allauth**, not Clerk — Clerk has no first-party Django SDK and would require a JS frontend, which conflicts with this project's server-rendered-only architecture (see Tech Stack / Development Constraints).

### Roles

| Role | Mechanism | Access |
|---|---|---|
| **Admin** | `is_staff=True` | Everything — create, edit, delete, toggle, clone, import, supplier linking, user management. Full cost/rate visibility. |
| **Viewer** | `is_staff=False`, no Carpenter group | Read-only: lists, detail pages, cost sheets, BOM view, import history. Full cost/rate visibility. |
| **Carpenter** | `UserProfile.role='carpenter'` (always `is_staff=False`) | Restricted, cost-free view: can see product/BOM/part structure and submit new BOM data (see Carpenter Entry below), but **never** sees rates, costs, or cost sheets. 403 on every page except `/carpenter/`; redirected there after login. |

**`apps.accounts.UserProfile`** (OneToOne → User, `related_name='profile'`): `role` (admin/viewer/carpenter) + `language` (en/ta). Auto-created for every user by a `post_save` signal (`apps/accounts/signals.py`). `is_staff` stays authoritative for admin and is kept in sync both ways: saving a profile sets `is_staff = (role == 'admin')`; saving a User with `is_staff=True` promotes the role to admin, and `is_staff=False` demotes admin → viewer (carpenter is preserved). Read roles via `apps/core/roles.py` (`get_role`, `is_carpenter`); templates get `user_role` / `is_carpenter` from `apps.core.context_processors.user_role`. Roles are set in User Management (Role select) or the Django admin user page.

Role checks remain server-side decorators in `apps/core/decorators.py` (`admin_required`, `not_carpenter`, `carpenter_required`) — do not introduce a separate permissions system.

---

## Carpenter Entry

Carpenters need a way to submit BOM/dimension data from the shop floor without direct write access to production `BOMItem`/`WoodPart` records, and without seeing costs. Design:

- **`BOMSubmission`** — a staging header record: which product, which carpenter (user), timestamp, status (`pending` / `approved` / `rejected`).
- **`SubmissionLine`** — staging line items under a `BOMSubmission`: resource, quantity or dimensions, part name. Mirrors the shape of `BOMItem`/`WoodPart` but is never itself costed and never feeds the cost sheet directly.
- **Admin approval required.** An Admin reviews pending `BOMSubmission`s and approves/rejects; approval is the only path that copies a `SubmissionLine` into real `BOMItem`/`WoodPart` records. Rejections stay in the staging table for audit/history.
- **Data is stored in English canonical form.** `Resource`, `Product`, and part names remain the single English source of truth used everywhere else in the system (costing, exports, imports).
- **Tamil is a display layer only**, via `name_ta` / `aliases` fields (planned: on `Resource`, possibly `Product`/`Part`) — used to render the Carpenter-facing submission UI in Tamil and to accept Tamil input, but always resolved back to the canonical English record before storage. No parallel Tamil data model.

**Implemented so far:**
- Carpenter role + lockout (see Authentication above). `/carpenter/` is still a placeholder landing page for logged-in carpenters.
- **Magic-link submissions (built).** `apps.carpenter.models`: `BOMSubmission` (product, `token`, carpenter name/phone, language en/ta, `expires_at`, status `open → pending → approved | rejected`, plus `revoked`) and `SubmissionLine` (`line_type` `bom`/`dimension`, same fields as BOMItem/WoodPart, never costed).
  - Admin: BOM page → **Request from carpenter** → `bom:submission_link_create` → detail page with Copy + WhatsApp (`wa.me`) share. Review at `bom:submission_list` / `bom:submission_detail` (current BOM qty shown per line, lines editable + tickable) → `bom:submission_approve` / `_reject` / `_revoke`. Views in `apps/bom/views_submissions.py`, so the lockout sweep covers them.
  - Public form: `carpenter:link_form` at `/carpenter/link/<token>/` — **the one deliberate exception to `@login_required`**. The 256-bit token is the credential; the link works once, expires (default 7 days, max 30), and can be revoked. Standalone layout (`carpenter/link_base.html`), no nav. Resource picker JSON is an explicit field whitelist — **never add rate/cost fields to `_resource_options()`**.
  - Approval writes through `apps/bom/services.py: apply_lines()` — BOM lines upsert on (product, resource) like the import; dimension lines create a WoodPart (+ `Part.get_or_create`). Rejected submissions stay as history.
- `name_ta` (CharField, blank) and `aliases` (TextField, blank, one per line) on `Resource` and `Part`. Both are NFC-normalised on save.
- `apps/core/search.py: search_by_name(queryset, query, name_field)` — case-insensitive match against the English name field, `name_ta` and `aliases` (query is NFC-normalised so differently-typed Tamil vowel signs still match). Use it for any carpenter-facing lookup.

---

## Voice Assistant (admin BOM page)

- **Voice Assistant** button on `bom:list` (admins only) opens an offcanvas chat. Speech-to-text and text-to-speech are the **browser's Web Speech API** (Chrome/Edge/Android; always `en-IN`, regardless of the user's profile language). Other browsers get a text box.
- **Voice is English only.** Recognition is fixed to `en-IN`; speech synthesis uses an en-IN/en-US voice and strips Tamil script before speaking. Tamil is display/typing only — the admin can type Tamil and search still matches `name_ta`/aliases. Replies are always English.
- `apps/bom/assistant.py` runs a manual tool-call loop over any **OpenAI-compatible** chat-completions API (`openai` SDK, `client.chat.completions.create`, function-calling format) — default is the Gemini free tier, Groq also works. Free models are less reliable, so: every tool call's `arguments` go through `parse_arguments()` (bad JSON / missing or mistyped fields → an `error` tool result the model can correct, never a crash), the loop is capped at `MAX_TOOL_ROUNDS`, and 429 / network / 5xx errors become "The assistant is busy, try again in a moment" in the chat (HTTP 200, history rolled back). Session state carries `format: 'openai-1'`; older sessions keep their draft and restart the conversation. Tools: `search_resources` (uses `search_by_name`, never returns rates), `search_parts`, `get_current_bom`, `get_draft`, `stage_material`, `stage_dimension`, `remove_staged_row`.
- **It never writes to the BOM.** Stage tools only add to a draft in `request.session['bom_assistant'][product_pk]`. **Save to BOM** (`bom:assistant_commit`) re-validates every row and writes through `services.apply_lines()`.
- History is append-only and stored in OpenAI chat format (tool calls echoed back unchanged, including provider extras like Gemini thought signatures). A failed turn rolls back to the previous good state.
- Env vars (all optional; check the provider's current model list):

  | Variable | Gemini (default) | Groq |
  |---|---|---|
  | `BOM_ASSISTANT_API_KEY` | AI Studio key (empty → assistant hidden) | `gsk_...` |
  | `BOM_ASSISTANT_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `https://api.groq.com/openai/v1` |
  | `BOM_ASSISTANT_MODEL` | `gemini-2.5-flash` | `llama-3.3-70b-versatile` |

- Tests mock `assistant._client` and never call the API.

### Known host-level quirk
`/data/coolify/databases/` and `/data/coolify/applications/` subdirectories are sometimes created by Coolify with owner `santosh:santosh` and no traverse permission on parent dirs (`/data/coolify`, `/data/coolify/databases`, `/data/coolify/applications` are `9999:root`, mode 700). This breaks Coolify's own file-write steps (`.env` generation, Postgres init files) with `Permission denied`. Fixed via:
```bash
sudo setfacl -m u:santosh:--x /data/coolify
sudo setfacl -m u:santosh:--x /data/coolify/databases
sudo setfacl -m u:santosh:--x /data/coolify/applications
sudo chown -R santosh:santosh /data/coolify/applications/<app-uuid>   # app dirs — santosh writes .env directly
sudo chown -R 70:70 /data/coolify/databases/<db-uuid>                # db dirs — postgres container runs as uid 70
```
Watch for this same pattern if new databases/apps are added later. Also: `santosh` must be in the `docker` group (`sudo usermod -aG docker santosh`) for Coolify's server validation to pass.

---

## Important Warnings

1. **No CSRF bypass** — all POST forms must include `{% csrf_token %}`.
2. **`ResourceSupplier.supplier_code`** uses join table PK, not Supplier PK — misleading name.
3. **~~SQLite in production on Render~~ — resolved.** Now deployed on PostgreSQL via Coolify; data persists across deploys.
3a. **CSRF_TRUSTED_ORIGINS must include every scheme+host the app is accessed by** — currently needs the `https://bom.lumelabs.dev` origin. Missing an origin here causes `403 CSRF verification failed` even though the request otherwise succeeds.
4. **WoodPart part_name fallback** — if "Parts" column is empty, falls back to resource name. Multiple cuts of same material for same product will overwrite each other on re-import.
5. **Portfolio cost on dashboard** — summed in Python, not SQL. Acceptable for MVP; will slow with very large datasets.

---

## Future Roadmap

1. ~~**PostgreSQL migration**~~ ✅ done — deployed on Coolify-managed PostgreSQL
2. **User management UI** — add/remove users without Django admin
3. ~~**django-allauth + MFA + Carpenter role**~~ ✅ done (MFA later removed) — see Authentication / Security / Carpenter Entry sections above
4. **Overhead allocation** — % overhead on direct costs
5. **Audit trail** — who changed what and when
6. **Supplier additional fields** — address, email, payment terms, lead time
7. **ResourceSupplier fields** — stock_available, lead_time_days
8. **BOM versioning / history**
9. **Pagination** ✅ done
10. **Bulk operations** — bulk activate/deactivate