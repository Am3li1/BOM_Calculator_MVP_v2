# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: June 2026

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. In active use/development.

**Overall Health:** Functional and deployed. Core workflows work end-to-end. Several important bugs and missing features (export, correct cost calculations) need addressing before production-critical use.

---

## Completed Features

### Module: Authentication (`apps.accounts`)
**Status: ✅ Complete**
- Login view with redirect to `next` param
- Logout view
- All views protected with `@login_required`
- Auto-redirect authenticated users away from login page
- **Notes:** No registration, no password reset, no user management UI. Django admin used for user management.

---

### Module: Core / Dashboard (`apps.core`)
**Status: ✅ Complete**
- Dashboard with summary counts (products, resources, BOM items, wood parts)
- Recent products and recently updated resources widgets
- `SystemConfig` singleton for company name and wood_divisor
- `get_item` custom template filter for dict variable-key lookups
- `create_default_superuser` management command
- **Notes:** Dashboard is minimal — no charts, no trend data, no supplier counts. Suitable for MVP.

---

### Module: Products (`apps.products`)
**Status: ✅ Complete**
- Product list with search (name, code) and status filter (active/inactive)
- Create product (with soft-delete collision handling — restores if same code exists)
- Edit product
- Soft delete (marks `is_deleted=True`, never hard-deletes)
- **Clone product** — copies product + all BOM items + all WoodParts atomically
- Product code uniqueness enforced only among non-deleted records
- Django admin integration
- **Notes:** Clone is a particularly well-implemented feature. No bulk delete/archive UI.

---

### Module: Resources (`apps.resources`)
**Status: ✅ Complete**
- Resource list with search + category filter + status filter
- Create / edit resources
- Toggle active/inactive
- Safe delete: blocked if resource is referenced in BOM or WoodParts; offers deactivation instead
- Resource detail page showing supplier pricing panel
- Manual override rate: set/clear from detail page with optional reason
- `ResourceCategory` model for DB-managed categories (admin-editable)
- Rate priority chain: override → preferred supplier → lowest supplier → master rate
- `effective_rate` and `effective_rate_source` properties for UI display
- **Notes:** Category filter merges DB categories with imported categories for completeness.

---

### Module: Suppliers (`apps.suppliers`)
**Status: ✅ Complete**
- Supplier list with search
- Create / edit suppliers (name, phone, GST)
- Toggle active/inactive
- Resource-supplier linking: link supplier to resource with rate
- Auto-preferred: first supplier linked becomes preferred automatically
- Set preferred supplier manually
- Update supplier rate
- Unlink supplier (with auto-promotion of next cheapest if preferred was removed)
- Price comparison display on resource detail (cheapest vs highest, savings)
- **Notes:** No supplier detail page yet. Supplier-level view of all linked resources is missing.

---

### Module: BOM Management (`apps.bom`)
**Status: ✅ Complete**
- BOM list per product (Standard BOM items + Dimension entries on same page)
- Add BOM item (resource + quantity; excludes already-added resources)
- Edit BOM item quantity inline
- Remove BOM item
- Add WoodPart (dimensional entry: part name, resource, W/B/H/L, pieces, units per dimension)
- Edit WoodPart (all fields including resource)
- Remove WoodPart
- Formula types: standard (W×B×H×L×pcs ÷ divisor) and area (W×L×pcs ÷ divisor)
- Grand total = Standard BOM only (WoodParts are measurement records, not additive)
- **Notes:** `unique_together` on BOMItem prevents same resource twice per product. WoodParts allow duplicates.

---

### Module: Cost Sheets (`apps.costing`)
**Status: ✅ Complete (with known bug)**
- Cost sheet list (all active products, searchable)
- Full cost sheet per product
  - Standard BOM items grouped by resource category
  - Per-category subtotals
  - Category cost breakdown with percentage
  - Dimensions section (WoodParts shown for reference — no cost added)
  - Grand total
- Print-friendly CSS (sidebar/navbar hidden on print)
- **Known Bug:** Cost calculations use `resource.rate` (master rate) NOT `resource.effective_rate`. Supplier pricing and overrides are NOT reflected in cost sheets. See Known Issues section.

---

### Module: Excel Import (`apps.imports`)
**Status: ✅ Complete**
- Full workbook import (all sheets in one file)
- Individual sheet import per sheet type
- Two-phase import: validate → (if clean) → import atomically
- ImportLog: every attempt recorded with status, counts, error log
- Import history view
- Import result view with validation error display
- **Supported sheets:** Resource, Products, BOM, Wood/Ply/MDF, Suppliers
- Upsert behaviour for Resources, Products, BOM, Suppliers
- BOM/Wood cross-reference validation (file-based for full import; DB-based for individual)
- File constraints: .xlsx/.xls, max 10MB
- **Notes:** WoodPart import always creates new records — re-importing duplicates wood parts. ImportLog admin registration is missing (imports admin.py is empty).

---

## Pending Features

Prioritised list:

| Priority | Feature | Notes |
|---|---|---|
| 🔴 HIGH | **Fix `BOMItem.cost` to use `effective_rate`** | Correctness bug — cost sheets show wrong values when suppliers are configured |
| 🔴 HIGH | **Fix `WoodPart.cost` to use `effective_rate`** | Same issue |
| 🔴 HIGH | **Cost sheet Excel export** | Most-wanted user feature |
| 🟡 MEDIUM | **Fix WoodPart re-import duplication** | Add upsert by (product, resource, part_name) |
| 🟡 MEDIUM | **ImportLog admin registration** | `apps/imports/admin.py` is empty |
| 🟡 MEDIUM | **Supplier detail page** | Show all resources linked to a supplier |
| 🟡 MEDIUM | **PostgreSQL migration** | Required before real production use |
| 🟡 MEDIUM | **Cost sheet PDF export** | Print-to-PDF works but a proper PDF download would be better |
| 🟢 LOW | **Dashboard enhancements** | Charts, supplier count, cost totals across all products |
| 🟢 LOW | **Role-based permissions** | Admin vs read-only viewer |
| 🟢 LOW | **User management UI** | Currently requires Django admin |
| 🟢 LOW | **Password reset** | Currently no self-service reset |
| 🟢 LOW | **Supplier additional fields** | Address, email, payment terms, lead time |
| 🟢 LOW | **ResourceSupplier fields** | stock_available, lead_time_days, last_quoted_at |
| 🟢 LOW | **BOM versioning** | Track changes over time |
| 🟢 LOW | **Overhead allocation** | % overhead on top of direct costs |
| 🟢 LOW | **Audit trail** | Who changed what and when |
| 🟢 LOW | **Bulk operations** | Bulk activate/deactivate products/resources |

---

## Known Issues

### 🔴 CRITICAL: Wrong Rate Used in Cost Calculations

**File:** `apps/bom/models.py`

```python
# BOMItem.cost property (WRONG — uses master rate):
@property
def cost(self):
    return self.quantity * self.resource.rate   # ← should be effective_rate

# BOMItem.rate property (CORRECT):
@property
def rate(self):
    return self.resource.effective_rate  # ← this is right

# WoodPart.cost property (WRONG — uses master rate):
@property
def cost(self):
    return Decimal(str(self.calculated_quantity)) * self.resource.rate  # ← should be effective_rate
```

**Impact:** If a supplier is linked and preferred, the cost sheet does NOT reflect that rate. It uses the `resource.rate` (master/import rate) instead. All cost sheets showing resources with supplier pricing are potentially incorrect.

**Fix:** Change both `.cost` properties to use `self.resource.effective_rate`.

---

### 🟡 MEDIUM: WoodPart Re-import Creates Duplicates

**File:** `apps/imports/services.py → import_wood()`

The function always creates new WoodPart records. Re-uploading the same Excel file doubles all wood part entries for every product.

**Fix:** Use `get_or_create` on `(product, resource, part_name)` or clear existing WoodParts before import.

---

### 🟡 MEDIUM: ImportLog Not Registered in Admin

**File:** `apps/imports/admin.py` (empty)

ImportLog records are visible only through the web UI import history page. Admins cannot manage them via Django admin.

**Fix:** Register `ImportLog` in `apps/imports/admin.py`.

---

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading

**File:** `apps/suppliers/models.py`

```python
@property
def supplier_code(self):
    return f'SUP-{self.pk:03d}'  # pk is ResourceSupplier PK, not Supplier PK
```

This property is on `ResourceSupplier` (the join table) and uses that table's PK, not the Supplier's PK. The name implies it's a supplier identifier, but it's actually a link identifier.

---

### 🟢 LOW: No CSRF on Some Quick-Action Forms

Some small inline POST forms (toggle active, set preferred, update rate) may not consistently include `{% csrf_token %}`. Should audit all templates.

---

### 🟢 LOW: SQLite Production Data Loss

Every Render deployment resets the SQLite database. This is documented and accepted for MVP but must be resolved before real production use.

---

## Technical Debt

1. **`BOMItem.cost` vs `BOMItem.rate` inconsistency** — `.rate` uses `effective_rate` but `.cost` uses `resource.rate`. The two properties are inconsistent. Should be unified.

2. **`WoodPart.calculated_quantity` imports `SystemConfig` inside the property** — lazy import pattern; could be a class-level concern.

3. **`resource.rate` stored as `Decimal` but `WoodPart` dimensions use `float` in view** — the view converts to float then stores as Decimal. Mixing float/Decimal risks precision issues.

4. **`bom_item.cost` in `bom/views.py` uses raw Python sum()** — `sum(item.cost for item in bom_items)` — no database aggregation. Will be slow for large BOMs.

5. **No select_related on BOM list view** — `bom_items.select_related('resource')` is used but `resource.supplier_links` is not prefetched when displaying effective rate on BOM page. Could cause N+1 queries.

6. **`_make_product_code` in services.py regex could collide** — "TEAK WOOD" and "TEAK-WOOD" would both become "TEAK-WOOD". Product code uniqueness across import batches could be fragile.

7. **`upload_sheet` view imports services inline** — `from .services import SHEET_REGISTRY, ...` inside the function. Should be module-level import.

8. **`category` on Resource is a plain CharField** — not a FK to `ResourceCategory`. Import can create resources with categories not in `ResourceCategory`, causing filter inconsistencies. The view compensates by merging both sources.

9. **No pagination** — resource list, product list, supplier list, import history have no pagination. Will degrade with large datasets.

10. **`BOMItem.cost` calculated in Python, not SQL** — `costing/views.py` fetches all BOM items and sums in Python. No `annotate(total=Sum(...))`.

---

## Recent Changes (Git History Summary)

Based on migration files and code structure:
- Initial project setup: Django 5, apps scaffold
- Products: soft delete, product code, basic CRUD
- Resources: categories as DB model, supplier linking, override rate
- BOM: WoodPart model with units per dimension, formula types
- Suppliers: ResourceSupplier join table, preferred logic
- Imports: two-phase validate+import, ImportLog, individual sheet import
- Costing: cost sheet with category grouping, print CSS
- Products: clone feature
- Suppliers: import support added to services.py

---

## Recommended Next Task

**Fix the cost calculation bug first** (`BOMItem.cost` and `WoodPart.cost` should use `effective_rate`). This is a correctness issue affecting every cost sheet where supplier pricing has been configured. It's a 2-line fix with wide impact:

```python
# In apps/bom/models.py

# BOMItem.cost — change:
return self.quantity * self.resource.rate
# to:
return self.quantity * self.resource.effective_rate

# WoodPart.cost — change:
return Decimal(str(self.calculated_quantity)) * self.resource.rate
# to:
return Decimal(str(self.calculated_quantity)) * self.resource.effective_rate
```

Then write a test verifying the effective_rate chain is used.

**After that:** Implement Excel export for cost sheets (`openpyxl` is already in requirements).

---

## Deployment Notes

- **Platform:** Render (free tier or standard)
- **Build script:** `build.sh` — runs pip install, collectstatic, migrate, createsuperuser
- **Database:** SQLite at `db.sqlite3` — **resets on every Render deploy**
- **Default credentials:** `admin` / `changeme123` — change immediately
- **Static files:** Served by WhiteNoise; `collectstatic` runs in build
- **Media files:** Ephemeral on Render (uploaded Excel files not persisted)
- **Timezone:** Asia/Kolkata (IST)
- **Required env vars on Render:** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=your-app.onrender.com`

---

## Testing Notes

- **Only one test file:** `apps/imports/tests.py` — one `SimpleTestCase` verifying `_sheet_exists` closes temp files.
- **No model tests, no view tests, no form tests.**
- Run tests: `python manage.py test`
- Before any significant refactor, especially to cost calculation logic, add unit tests for:
  - `Resource.effective_rate` priority chain
  - `BOMItem.cost` with and without suppliers
  - `WoodPart.calculated_quantity` for both formula types
  - Import validators (validate_resources, validate_bom, validate_wood)