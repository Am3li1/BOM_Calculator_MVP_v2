# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: June 2026 — BOMItem.cost confirmed correct; unit tests added

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. In active use/development.

**Overall Health:** Functional and deployed. All core workflows work end-to-end. All medium-priority bugs are resolved. Unit test coverage added for rate priority chain and cost calculation. PostgreSQL migration is the main remaining infrastructure item.

---

## Completed Features

### Module: Authentication (`apps.accounts`)
**Status: ✅ Complete**
- Login/logout, `@login_required` on all views, auto-redirect authenticated users
- **Notes:** No registration, no password reset. Django admin used for user management.

---

### Module: Core / Dashboard (`apps.core`)
**Status: ✅ Complete**
- Dashboard summary counts, recent products/resources widgets
- `SystemConfig` singleton (company name, wood_divisor)
- `get_item` custom template filter, `create_default_superuser` management command

---

### Module: Products (`apps.products`)
**Status: ✅ Complete**
- List with search/filter, create, edit, soft delete, clone (product + BOM + WoodParts atomically)
- Product code uniqueness among non-deleted records only

---

### Module: Resources (`apps.resources`)
**Status: ✅ Complete**
- List with search/category/status filters, create, edit, toggle active, safe delete
- Resource detail page with supplier pricing panel
- Manual override rate (set/clear with reason)
- Rate priority chain: override → preferred supplier → lowest supplier → master rate
- `effective_rate` and `effective_rate_source` properties

---

### Module: Suppliers (`apps.suppliers`)
**Status: ✅ Complete**
- List, create, edit, toggle active
- Resource-supplier linking with auto-preferred, set preferred, update rate, unlink
- Supplier detail page with stats and linked resources table
- **Bug fixed:** redirect to `'suppliers:supplier_list'` (was `'suppliers:list'`)
- **Bug fixed:** multi-line `{# #}` comments rendering as visible text

---

### Module: BOM Management (`apps.bom`)
**Status: ✅ Complete**
- Add/edit/remove BOM items and WoodParts per product
- Formula types: standard (W×B×H×L×pcs ÷ divisor) and area (W×L×pcs ÷ divisor)
- Grand total = Standard BOM only
- `BOMItem.cost` and `WoodPart.cost` correctly use `resource.effective_rate` (verified Jun 2026)

---

### Module: Cost Sheets (`apps.costing`)
**Status: ✅ Complete**
- Cost sheet list and full cost sheet per product, grouped by category with subtotals
- Print-friendly CSS
- Cost calculations use `effective_rate` — supplier pricing and overrides are reflected correctly

---

### Module: Excel Import (`apps.imports`)
**Status: ✅ Complete**
- Full workbook and individual sheet import
- Two-phase: validate → import atomically
- Upsert behaviour for all sheets including WoodParts — keyed on (product, resource, part_name)
- ImportLog registered in Django admin as view/delete only (no add, no edit)

---

### Module: Excel Export (`apps.costing`)
**Status: ✅ Complete**
- Per-product export at `/costing/<pk>/export/`
- Full workbook export at `/costing/export/full/`
- 7 sheets: Products, Resources, Suppliers, SupplierRates, BOM, Dimensions, CostSummary

---

### Unit Tests (`apps/imports/tests.py`)
**Status: ✅ In place**
- `ImportServicesTests` — `_sheet_exists` closes temp files (SimpleTestCase)
- `EffectiveRateTest` — rate priority chain: master, preferred supplier, manual override
- `BOMItemCostTest` — cost without supplier uses master rate; cost with supplier uses effective rate
- **Run:** `python manage.py test apps.imports.tests`

---

## Pending Features

| Priority | Feature | File / Location | Notes |
|---|---|---|---|
| 🟡 MEDIUM | **PostgreSQL migration** | `config/settings.py`, `requirements.txt`, Render config | SQLite resets on every Render deploy |
| 🟢 LOW | **Supplier detail: stay on page after toggle** | `apps/suppliers/views.py` | Currently redirects to list after toggle |
| 🟢 LOW | **Dashboard enhancements** | `apps/core/views.py` | Supplier count, portfolio cost, charts |
| 🟢 LOW | **Role-based permissions** | New middleware or decorators | Admin vs read-only viewer |
| 🟢 LOW | **User management UI** | `apps/accounts/` | Currently requires Django admin |
| 🟢 LOW | **Password reset flow** | `apps/accounts/urls.py` | No self-service reset |
| 🟢 LOW | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW | **ResourceSupplier fields** | `apps/suppliers/models.py` | stock_available, lead_time_days, last_quoted_at |
| 🟢 LOW | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW | **Pagination** | All list views | No pagination on any list |
| 🟢 LOW | **Bulk operations** | List views | Bulk activate/deactivate |

---

## Known Issues

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading

**File:** `apps/suppliers/models.py` — uses join table PK, not Supplier PK. Display-only risk.

---

### 🟢 LOW: SQLite Production Data Loss

Every Render deployment resets the SQLite database. Must migrate to PostgreSQL before real production use.

---

### 🟢 LOW: No CSRF Audit on Quick-Action Forms

Inline POST forms (toggle active, set preferred, update rate) should be audited for `{% csrf_token %}`.

---

### 🟢 LOW: WoodPart part_name Fallback Risk

If the Excel "Parts" column is empty, `part_name` falls back to the resource name. Multiple cuts of
the same material for the same product with no part name will all share the same key and overwrite
each other on re-import. Ensure the Parts column is populated for products with multiple cuts.

---

## Technical Debt

1. **`WoodPart.calculated_quantity` imports `SystemConfig` inside the property** — should be module-level.
2. **Float/Decimal mixing in WoodPart views** — dimensions parsed as float, stored as Decimal; precision risk.
3. **`bom_item.cost` summed in Python, not SQL** — will degrade with large BOMs.
4. **No `select_related` on BOM list for supplier links** — potential N+1 queries.
5. **`_make_product_code` collision risk** — "TEAK WOOD" and "TEAK-WOOD" both produce "TEAK-WOOD".
6. **`category` on Resource is a plain CharField** — import can create categories not in `ResourceCategory`.
7. **No pagination on any list view** — will degrade with large datasets.

---

## Recent Changes Log

| Date | Change | Files |
|---|---|---|
| Jun 2026 | **Verified BOMItem.cost and WoodPart.cost use effective_rate** — confirmed correct in live code; added unit tests as regression guard | `apps/imports/tests.py` |
| Jun 2026 | **ImportLog admin registration** — view/delete only; Add and Change permissions disabled | `apps/imports/admin.py` |
| Jun 2026 | **Fixed WoodPart re-import duplication** — `update_or_create` keyed on `(product, resource, part_name)` | `apps/imports/services.py` |
| Jun 2026 | Supplier Detail Page — new view, URL, template | `apps/suppliers/views.py`, `apps/suppliers/urls.py`, `templates/suppliers/supplier_detail.html` |
| Jun 2026 | Fixed supplier redirect bug | `apps/suppliers/views.py` |
| Jun 2026 | Excel Export module completed | `apps/costing/` |
| Jun 2026 | Initial project setup through import module | All apps |

---

## Deployment Notes

- **Platform:** Render (free tier or standard)
- **Build script:** `build.sh` — pip install, collectstatic, migrate, createsuperuser
- **Database:** SQLite — **resets on every Render deploy**
- **Default credentials:** `admin` / `changeme123` — change immediately
- **Timezone:** Asia/Kolkata (IST)
- **Required env vars:** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=your-app.onrender.com`

---

## Testing Notes

- **Run:** `python manage.py test apps.imports.tests` (full dotted path required on Windows)
- **6 tests, all passing**
- Before any future changes to cost calculation logic, run tests first to confirm baseline