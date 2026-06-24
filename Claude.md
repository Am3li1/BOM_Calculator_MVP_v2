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
├── config/               # Django project config
│   ├── settings.py       # All settings (decouple for env vars)
│   ├── urls.py           # Root URL routing
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/             # Dashboard, SystemConfig, template tags
│   ├── accounts/         # Login/logout (Django auth, no registration)
│   ├── products/         # Product CRUD + soft delete + clone
│   ├── resources/        # Resource CRUD + categories + supplier linking
│   ├── suppliers/        # Supplier CRUD + ResourceSupplier join table
│   ├── bom/              # BOMItem + WoodPart CRUD
│   ├── costing/          # Cost sheet views (read-only, calculated)
│   └── imports/          # Excel import service + logs
├── templates/            # Global templates dir (all HTML here)
├── static/               # Project static files
├── media/                # Uploaded files (Excel imports)
├── build.sh              # Render deploy script
├── requirements.txt      # Python dependencies
└── manage.py
```

---

## Application Modules

### `apps.core`
- **SystemConfig** — singleton model (pk=1 always). Stores `company_name` and `wood_divisor` (default 144). Call `SystemConfig.get_config()` everywhere.
- **Dashboard view** — summary counts + recent products/resources.
- **`custom_filters`** templatetag — `get_item` filter for dict lookups by variable key in templates.
- **`create_default_superuser`** management command.

### `apps.accounts`
- Login/logout only. Uses Django's built-in `authenticate`/`login`/`logout`.
- No user registration, no password reset (MVP).
- All views behind `@login_required` (set `LOGIN_URL = '/accounts/login/'`).

### `apps.products`
- **Product** model: `product_name`, `product_code`, `active`, `is_deleted`.
- **Soft delete** via overridden `.delete()` method — sets `is_deleted=True`.
- **Product code uniqueness** enforced only among non-deleted records (custom `clean_product_code` in form).
- **Clone** feature: copies product + all BOMItems + all WoodParts into a new product atomically.
- Never hard-delete products — historical BOM data would break.

### `apps.resources`
- **ResourceCategory** — DB-managed categories (not hardcoded). Admin-editable.
- **Resource** model: `resource_name`, `category`, `unit`, `rate`, `manual_override_rate`, `override_reason`, `active`.
- **Rate priority chain** (critical — see Cost Calculation section below).
- Resources with active BOM/WoodPart references use `PROTECT` — cannot be deleted, only deactivated.

### `apps.suppliers`
- **Supplier** model: `supplier_name`, `phone_number`, `gst_number`, `active`.
- **ResourceSupplier** join table: `resource` FK, `supplier` FK, `supplier_rate`, `preferred`, `active`.
- Rate lives on `ResourceSupplier` (not on Resource), because the same material has different prices from different suppliers.
- First supplier linked to a resource is auto-set as `preferred=True`.
- When preferred supplier is unlinked, cheapest remaining supplier is auto-promoted to preferred.

### `apps.bom`
- **BOMItem**: product + resource + quantity. Rate/cost NOT stored — always calculated live.
- **WoodPart**: product + resource + part_name + W/B/H/L/pieces + per-dimension units + formula_type.
- Two formula types: `standard` (W×B×L×pcs ÷ divisor), `area` (W×L×pcs ÷ divisor). Height is optional.
- `unique_together = [['product', 'resource']]` on BOMItem — one resource per product in standard BOM.
- WoodPart cost = `calculated_quantity × resource.rate` (uses master rate, not effective_rate — see Known Issues).

### `apps.costing`
- **No models** — pure calculation views.
- `costing_list`: list of all active products.
- `cost_sheet`: full cost breakdown per product. Groups BOM items by resource category. Grand total = Standard BOM total ONLY.
- Dimensions (WoodParts) are shown for reference but NOT added to grand total (their material cost is already in Standard BOM).

### `apps.imports`
- **ImportLog** model — tracks every upload attempt with status, counts, error log.
- **Two-phase import**: validate → import. Validation failures never touch the DB.
- **`services.py`** — all logic here. Validators + importers per sheet. `SHEET_REGISTRY` dict for extensibility.
- Supports full workbook import OR individual sheet import.
- Sheets: `Resource`, `Products`, `BOM`, `Wood, Ply MDF`, `Suppliers`.
- BOM/Wood validators cross-reference Products and Resources from either the same file (full import) or the DB (individual import).

---

## Critical Business Rules

1. **Cost is never stored.** `BOMItem.cost = quantity × resource.rate`. Changing a resource rate immediately affects all products.
2. **Grand total = Standard BOM only.** WoodPart entries are dimensional records. Their material cost is already captured in BOM. Adding both would double-count.
3. **Soft delete products only.** Never call `Product.objects.filter(...).delete()` or SQL DELETE on products.
4. **Resource uniqueness** = `(resource_name, category)` pair. Same name can exist in different categories.
5. **Product code uniqueness** = among non-deleted products only.
6. **Preferred supplier auto-management**: first link → auto-preferred. Remove preferred → auto-promote cheapest.
7. **wood_divisor** controls the WoodPart formula. Do not hardcode 144. Always read from `SystemConfig.get_config()`.
8. **Import is atomic** — if any part of the import fails after validation passes, the entire transaction rolls back.

---

## Cost Calculation Rules

### Resource Effective Rate (single source of truth)

```
Priority 1: resource.manual_override_rate  (if not None)
Priority 2: preferred supplier rate         (ResourceSupplier where preferred=True, active=True)
Priority 3: lowest active supplier rate     (cheapest active ResourceSupplier)
Priority 4: resource.rate                   (master rate — fallback when no suppliers)
```

Use `resource.effective_rate` everywhere in costing. Use `resource.effective_rate_source` for UI display showing WHERE the rate comes from.

### BOMItem Cost
```python
cost = bom_item.quantity * resource.effective_rate
```
Note: `BOMItem.cost` property currently uses `resource.rate` (master rate), NOT `effective_rate`. This is a known bug.

### WoodPart Calculated Quantity
```python
# Standard formula:
quantity = (W × B × H × L × Pieces) / wood_divisor

# Area formula (when formula_type == 'area'):
quantity = (W × L × Pieces) / wood_divisor
```
H defaults to 1 if 0 or not provided.

### WoodPart Cost
```python
cost = calculated_quantity * resource.rate   # uses master rate, not effective_rate
```

---

## Import / Export Rules

### Import (Excel → DB)

**Supported sheets and their column requirements:**

| Sheet Name | Required Columns | Notes |
|---|---|---|
| `Resource` | Resource, Category, Units, Rate | header row 0 |
| `Products` | (column A, no header) | skips: column1, products, select, '' |
| `BOM` | Product, Resource, Quantity | Product column is forward-filled |
| `Wood, Ply MDF` | Product, Resource, Width, Breath, Length | Note: "Breath" (typo in spec, must match) |
| `Suppliers` | Supplier Name, Supplier Mobile | header=1 (row 0 is 'Table 1' title) |

**Upsert behaviour (not replace):**
- Resources: `get_or_create` on (name, category); updates unit/rate if exists.
- Products: `get_or_create` on code; restores soft-deleted if same code.
- BOM: `get_or_create` on (product, resource); updates quantity if exists.
- WoodParts: always creates new (no upsert — duplicates possible on re-import).
- Suppliers: `get_or_create` on name; updates phone if exists.

**File constraints:** `.xlsx` or `.xls`, max 10MB.

### Export

**Export functionality does not exist yet.** This is a pending feature. No Excel/CSV/PDF export is implemented.

---

## Coding Standards

- **Function-based views only.** No class-based views.
- **`@login_required` on every view** without exception.
- **POST-only for mutations.** Delete/toggle/link operations must be POST, never GET.
- **Decimal for all money.** Use `Decimal` not `float` for rates and costs.
- **`transaction.atomic()`** for multi-model writes (clone, import).
- **`select_related`** on FKs in list views to avoid N+1 queries.
- **Bootstrap 5 classes** in templates. Use `form-control`, `form-select`, `btn-*` etc.
- **`messages` framework** for all user feedback (success/error/info).
- **App namespace** in every `urls.py` (`app_name = 'xxx'`). Use `{% url 'app:name' %}` in templates.
- **No hardcoded rates or divisors** — always read from DB.
- **Template dir is global** (`templates/` in project root), not per-app.

---

## Development Constraints

- **SQLite only** for MVP. No PostgreSQL migration yet. Be aware: SQLite has limited concurrent write support.
- **No async/Celery** — keep everything synchronous. Large imports block the request.
- **No tests except** `apps/imports/tests.py` (one SimpleTestCase). Add tests alongside new features.
- **No REST API** — server-rendered HTML only.
- **Media files not persisted on Render** — uploads in `media/imports/` are ephemeral.
- **`staticfiles/` is generated** by `collectstatic`. Do not edit files there.

---

## Deployment Information

- **Platform:** Render (PaaS)
- **Build command:** `build.sh` (pip install → collectstatic → migrate → createsuperuser)
- **Database resets on every deploy** (SQLite file in repo — ephemeral). This is a known limitation for MVP.
- **Static files:** WhiteNoise serves them without Nginx.
- **Default superuser:** `admin` / `changeme123` — MUST be changed in production.
- **Environment variables required:**
  - `SECRET_KEY` — Django secret key
  - `DEBUG` — `False` in production
  - `ALLOWED_HOSTS` — comma-separated (e.g. `your-app.onrender.com`)
- **Timezone:** `Asia/Kolkata` (IST)

---

## Important Warnings

1. **`BOMItem.cost` uses `resource.rate`, not `resource.effective_rate`.** This is a bug — the cost sheet does NOT reflect supplier pricing overrides. The `rate` property on `BOMItem` returns `effective_rate` but `cost` uses `resource.rate`. Fix carefully — changing this affects all cost sheets.

2. **WoodPart.cost also uses `resource.rate`**, same issue.

3. **No CSRF protection bypass** — all POST forms must include `{% csrf_token %}`.

4. **ResourceSupplier.supplier_code** property uses `self.pk` (ResourceSupplier PK, not Supplier PK). This is misleading naming — it's a link code, not a supplier code.

5. **WoodPart re-import creates duplicates** — the import_wood function always creates new WoodPart records. Re-importing the same file doubles the wood parts for a product.

6. **No multi-user access control** — all authenticated users have equal access. No role-based permissions.

7. **SQLite in production on Render** — data is lost on every deployment. Move to PostgreSQL before going to real production use.

---

## Future Roadmap

In rough priority order:

1. **Cost sheet Excel/PDF export** — high priority user request
2. **Fix `BOMItem.cost` to use `effective_rate`** — correctness bug
3. **Fix WoodPart import deduplication** (upsert by product+resource+part_name)
4. **PostgreSQL migration** — production data persistence
5. **Role-based access** (admin vs viewer)
6. **Supplier: additional fields** — address, email, payment_terms, lead_time_days, last_quoted_at
7. **ResourceSupplier: stock_available, lead_time_days**
8. **BOM versioning / history** — track changes over time
9. **Overhead allocation** — percentage-based overhead on top of direct costs
10. **User management UI** — add/remove users without Django admin
11. **Password reset** flow
12. **Audit trail** — who changed what and when