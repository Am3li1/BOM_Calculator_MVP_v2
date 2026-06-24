# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: June 2026 — Supplier Detail Page complete, redirect bug fixed

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. In active use/development.

**Overall Health:** Functional and deployed. All core workflows work end-to-end. Excel import and export are complete. Supplier Detail Page is now complete. Three medium-priority items remain: WoodPart import deduplication, ImportLog admin registration, and PostgreSQL migration for production persistence.

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
- **Bug fixed:** `supplier_create`, `supplier_edit`, `supplier_toggle_active` were all
  redirecting to `'suppliers:list'` (NoReverseMatch). Fixed to `'suppliers:supplier_list'`.

---

### Module: Supplier Detail Page (`apps.suppliers`)
**Status: ✅ Complete**
- `supplier_detail` view in `apps/suppliers/views.py`
- URL route `<int:pk>/` registered as `suppliers:supplier_detail`
- Supplier name in list page is now a clickable link to the detail page
- "View" button added to supplier list actions column
- Template at `templates/suppliers/supplier_detail.html` with:
  - Header: supplier name, Active/Inactive badge, Edit and Deactivate/Activate buttons
  - Supplier info card: name, phone (tap-to-call link), GST number, status
  - 4 equal-height stat cards: Total Resources, Active Links, Preferred For, Sum of Active Rates
  - Resources table: resource name, category badge, unit, supplier rate (₹), preferred star, link status, jump-to-resource button
  - Row colour coding: grey for inactive links, green for active+preferred, white for active only
  - Empty state when no resources are linked
- `select_related('resource')` used to eliminate N+1 queries
- **Bug fixed:** Multi-line `{# #}` comments were rendering as visible text. Replaced with
  `{% comment %}...{% endcomment %}` block tags throughout.
- **Notes:** Toggle active from detail page redirects to supplier list (existing behaviour).
  Minor polish item: pass `?next=` to stay on detail page after toggle.

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
- **Known Bug:** Cost calculations use `resource.rate` (master rate) NOT `resource.effective_rate`.
  Supplier pricing and manual overrides are NOT reflected in cost sheets. See Known Issues.

---

### Module: Excel Import (`apps.imports`)
**Status: ✅ Complete**
- Full workbook import (all sheets in one file)
- Individual sheet import per sheet type
- Two-phase import: validate → (if clean) → import atomically
- ImportLog: every attempt recorded with status, counts, error log
- Import history view and import result view with validation error display
- **Supported sheets:** Resource, Products, BOM, Wood/Ply/MDF, Suppliers
- Upsert behaviour for Resources, Products, BOM, Suppliers
- BOM/Wood cross-reference validation (file-based for full import; DB-based for individual)
- File constraints: .xlsx/.xls, max 10MB
- **Notes:** WoodPart import always creates new records — re-importing duplicates wood parts.
  ImportLog not registered in Django admin.

---

### Module: Excel Export (`apps.costing`)
**Status: ✅ Complete**
- Per-product cost sheet export at `/costing/<pk>/export/`
- Full workbook export at `/costing/export/full/`
- 7-sheet export: Products, Resources, Suppliers, SupplierRates, BOM, Dimensions, CostSummary
- Frozen header rows, auto-sized columns, currency formatting, alternating row striping
- Preferred supplier rows highlighted in green
- CostSummary sorted by highest total cost first
- Filename format: `Product_Costing_Export_YYYYMMDD.xlsx`

---

## Pending Features

| Priority | Feature | File / Location | Notes |
|---|---|---|---|
| 🟡 MEDIUM | **Fix WoodPart re-import duplication** | `apps/imports/services.py → import_wood()` | Always creates new records; re-import doubles wood parts |
| 🟡 MEDIUM | **Register ImportLog in admin** | `apps/imports/admin.py` (currently empty) | Admins can't manage import logs via Django admin |
| 🟡 MEDIUM | **PostgreSQL migration** | `config/settings.py`, `requirements.txt`, Render config | SQLite resets on every Render deploy; data lost in production |
| 🟡 MEDIUM | **Fix BOMItem.cost to use effective_rate** | `apps/bom/models.py`, `apps/costing/views.py` | Cost sheets don't reflect supplier pricing or overrides |
| 🟢 LOW | **Supplier detail: stay on page after toggle** | `apps/suppliers/views.py → supplier_toggle_active` | Currently redirects to list; pass `next` param to stay on detail |
| 🟢 LOW | **Dashboard enhancements** | `apps/core/views.py` | Add supplier count, total portfolio cost, simple charts |
| 🟢 LOW | **Role-based permissions** | New middleware or decorators | Admin vs read-only viewer |
| 🟢 LOW | **User management UI** | New views in `apps/accounts` | Currently requires Django admin |
| 🟢 LOW | **Password reset flow** | `apps/accounts/urls.py` | No self-service reset |
| 🟢 LOW | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW | **ResourceSupplier fields** | `apps/suppliers/models.py` | stock_available, lead_time_days, last_quoted_at |
| 🟢 LOW | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW | **Pagination** | All list views | Resource, product, supplier, import history lists have no pagination |
| 🟢 LOW | **Bulk operations** | List view templates + views | Bulk activate/deactivate products/resources |

---

## Known Issues

### 🟡 MEDIUM: BOMItem.cost Uses Master Rate, Not Effective Rate

**Files:** `apps/bom/models.py`, `apps/costing/views.py`

`BOMItem.cost` uses `resource.rate` directly. `BOMItem.rate` (a separate property) correctly uses
`resource.effective_rate`. The two are inconsistent. Cost sheets do not reflect supplier pricing
or manual override rates — they always show the master rate.

**Fix:** Change `BOMItem.cost` to use `self.resource.effective_rate`. Same fix needed for
`WoodPart.cost`. Add unit tests before and after to verify the change.

---

### 🟡 MEDIUM: WoodPart Re-import Creates Duplicates

**File:** `apps/imports/services.py → import_wood()`

Always creates new `WoodPart` records. Re-uploading the same Excel file doubles all wood part
entries for every product silently.

**Fix:** Use `update_or_create` keyed on `(product, resource, part_name)`.

---

### 🟡 MEDIUM: ImportLog Not Registered in Admin

**File:** `apps/imports/admin.py` (empty)

ImportLog records are only visible through the web UI import history page.

**Fix:**
```python
from django.contrib import admin
from .models import ImportLog

@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'sheet_name', 'status', 'rows_imported', 'rows_failed']
    list_filter = ['status', 'sheet_name']
    readonly_fields = ['created_at', 'error_log']
```

---

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading

**File:** `apps/suppliers/models.py`

```python
@property
def supplier_code(self):
    return f'SUP-{self.pk:03d}'  # pk is ResourceSupplier PK, not Supplier PK
```

Uses the join table's PK, not the Supplier's PK. The name implies a supplier identifier but it
is actually a link identifier. Low risk (display only) but confusing for developers.

---

### 🟢 LOW: SQLite Production Data Loss

Every Render deployment resets the SQLite database. Documented and accepted for MVP. Must be
resolved before real production use — migrate to PostgreSQL.

---

### 🟢 LOW: No CSRF Audit on Quick-Action Forms

Some small inline POST forms (toggle active, set preferred, update rate) may not consistently
include `{% csrf_token %}`. Should audit all templates before production.

---

## Technical Debt

1. **`BOMItem.cost` vs `BOMItem.rate` inconsistency** — `.rate` uses `effective_rate` but
   `.cost` uses `resource.rate`. Should be unified. High priority to fix before real use.

2. **`WoodPart.calculated_quantity` imports `SystemConfig` inside the property** — lazy import
   pattern; should be a module-level import for clarity.

3. **`resource.rate` is Decimal but `WoodPart` dimensions use float in views** — the view
   converts to float then stores as Decimal. Mixing float/Decimal risks precision loss.

4. **`bom_item.cost` summed in Python, not SQL** — `sum(item.cost for item in bom_items)` has
   no database aggregation. Will degrade with large BOMs.

5. **No `select_related` on BOM list for supplier links** — `resource.supplier_links` is not
   prefetched when displaying effective rate on BOM page. Potential N+1 queries.

6. **`_make_product_code` regex collision risk** — "TEAK WOOD" and "TEAK-WOOD" both become
   "TEAK-WOOD". Product code uniqueness across import batches could be fragile.

7. **`upload_sheet` view imports services inline** — `from .services import ...` inside the
   function body. Should be a module-level import.

8. **`category` on Resource is a plain CharField, not a FK** — import can create resources with
   categories not in `ResourceCategory`, causing filter inconsistencies. The view compensates
   by merging both sources, but the root cause is unresolved.

9. **No pagination on any list view** — resource, product, supplier, import history lists will
   degrade significantly with large datasets.

10. **`BOMItem.cost` calculated in Python, not SQL** — `costing/views.py` fetches all BOM items
    and sums in Python. Should use `annotate(total=Sum(...))` for large datasets.

---

## Recent Changes Log

| Date | Change | Files |
|---|---|---|
| Jun 2026 | Supplier Detail Page — new view, URL, template | `apps/suppliers/views.py`, `apps/suppliers/urls.py`, `templates/suppliers/supplier_detail.html` |
| Jun 2026 | Fixed supplier redirect bug — `'suppliers:list'` → `'suppliers:supplier_list'` in 3 views | `apps/suppliers/views.py` |
| Jun 2026 | Fixed multi-line `{# #}` comments rendering as visible text in supplier detail template | `templates/suppliers/supplier_detail.html` |
| Jun 2026 | Excel Export module completed | `apps/costing/` |
| Jun 2026 | Initial project setup through import module | All apps |

---

## Recommended Next Task

### Option A — Fix WoodPart Re-import Duplication (🟡 Medium, ~1 hour)

**Why:** Users running regular Excel imports are silently accumulating duplicate wood part rows.
This corrupts dimension data and inflates any dimension-based reporting. It's a data integrity
bug that gets worse with every import.

**What to change:** `apps/imports/services.py → import_wood()`

Replace `WoodPart.objects.create(...)` with `update_or_create` keyed on
`(product, resource, part_name)`:

```python
wood_part, created = WoodPart.objects.update_or_create(
    product=product,
    resource=resource,
    part_name=part_name,
    defaults={
        'width': width,
        'breadth': breadth,
        'height': height,
        'length': length,
        'pieces': pieces,
        'width_unit': width_unit,
        'length_unit': length_unit,
        'formula_type': formula_type,
    }
)
```

---

### Option B — Register ImportLog in Admin (🟡 Medium, ~15 minutes)

**Why:** Admins currently have no way to delete old import logs or inspect them via Django admin.
The fix is four lines of code.

**What to change:** `apps/imports/admin.py` (currently empty — just add the registration block
shown in Known Issues above).

---

### Option C — Fix BOMItem.cost to Use effective_rate (🟡 Medium, ~2 hours with tests)

**Why:** Cost sheets are currently wrong — they show master rates even when a supplier override
or manual override is in effect. This is the most impactful correctness bug in the system.

**What to change:** `apps/bom/models.py` — change `BOMItem.cost` and `WoodPart.cost` to use
`self.resource.effective_rate` instead of `self.resource.rate`. Write unit tests first so you
can verify behaviour before and after.

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

- **Only one test file:** `apps/imports/tests.py` — one `SimpleTestCase` verifying `_sheet_exists`
  closes temp files.
- **No model tests, no view tests, no form tests.**
- Run tests: `python manage.py test`
- Before any significant refactor, especially to cost calculation logic, add unit tests for:
  - `Resource.effective_rate` priority chain (override → preferred supplier → lowest → master)
  - `BOMItem.cost` with and without suppliers
  - `WoodPart.calculated_quantity` for both formula types (standard and area)
  - Import validators (validate_resources, validate_bom, validate_wood)