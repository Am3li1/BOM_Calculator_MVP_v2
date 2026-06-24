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
- `cost_sheet`: full cost breakdown grouped by category. Grand total = Standard BOM only.
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

`@admin_required` raises `PermissionDenied` (→ 403) if `request.user.is_staff` is False.
`@login_required` must still be present — it handles unauthenticated users before `@admin_required` runs.

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
| `Resource` | Resource, Category, Units, Rate | header row 0 |
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

- **Run:** `python manage.py test apps.imports.tests` (full dotted path on Windows)
- **6 tests passing:**
  - `ImportServicesTests` — `_sheet_exists` closes temp files
  - `EffectiveRateTest` — rate priority chain (3 tests)
  - `BOMItemCostTest` — cost calculation (2 tests)
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

- **Platform:** Render (PaaS)
- **Build:** `build.sh` (pip install → collectstatic → migrate → createsuperuser)
- **Database resets on every deploy** — SQLite limitation. MVP only.
- **Default superuser:** `admin` / `changeme123` — change immediately.
- **Env vars required:** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`
- **Timezone:** `Asia/Kolkata` (IST)
- **User roles:** Set `is_staff=True` for admin users in Django admin.

---

## Important Warnings

1. **No CSRF bypass** — all POST forms must include `{% csrf_token %}`.
2. **`ResourceSupplier.supplier_code`** uses join table PK, not Supplier PK — misleading name.
3. **SQLite in production on Render** — data lost on every deploy. Move to PostgreSQL before real use.
4. **WoodPart part_name fallback** — if "Parts" column is empty, falls back to resource name. Multiple cuts of same material for same product will overwrite each other on re-import.
5. **Portfolio cost on dashboard** — summed in Python, not SQL. Acceptable for MVP; will slow with very large datasets.

---

## Future Roadmap

1. **PostgreSQL migration** — production data persistence
2. **User management UI** — add/remove users without Django admin
3. **Password reset flow**
4. **Overhead allocation** — % overhead on direct costs
5. **Audit trail** — who changed what and when
6. **Supplier additional fields** — address, email, payment terms, lead time
7. **ResourceSupplier fields** — stock_available, lead_time_days
8. **BOM versioning / history**
9. **Pagination** ✅ done
10. **Bulk operations** — bulk activate/deactivate