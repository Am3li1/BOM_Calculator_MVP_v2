# PROJECT_STATUS.md — BOM Costing System

> **Living document.** Update this file whenever major features are completed or the roadmap shifts.
> Last updated: June 2026 — Role-based permissions complete

---

## Project Status

**Current Version:** MVP v1.0 — Feature-complete for core BOM costing. In active use/development.

**Overall Health:** Functional and deployed. All core workflows work end-to-end. All medium-priority bugs resolved. Role-based permissions (admin vs viewer) now enforced across all views.

---

## Completed Features

### Module: Authentication (`apps.accounts`)
**Status: ✅ Complete**
- Login/logout, `@login_required` on all views, auto-redirect authenticated users
- **Notes:** No registration, no password reset. Django admin used for user management.

---

### Module: Core / Dashboard (`apps.core`)
**Status: ✅ Complete**
- Dashboard: 6 stat cards (products, resources, BOM items, dimensions, suppliers, portfolio cost)
- All stat cards are clickable links
- Recent products and resources tables
- `SystemConfig` singleton, `get_item` template filter, `create_default_superuser` command
- `admin_required` decorator in `apps/core/decorators.py`

---

### Module: Role-Based Permissions
**Status: ✅ Complete**
- Two roles: **Admin** (`is_staff=True`) and **Viewer** (`is_staff=False`)
- Managed via Django admin — no new models or migrations needed
- `@admin_required` decorator in `apps/core/decorators.py`
- Viewer can access: all list pages, detail pages, cost sheets, BOM view, import history
- Admin only: create, edit, delete, toggle active, clone, all imports, all supplier linking
- 403 page at `templates/403.html` with link back to dashboard

---

### Module: Products (`apps.products`)
**Status: ✅ Complete**
- List (viewer), create/edit/delete/clone (admin only)
- Soft delete, product code uniqueness among non-deleted records

---

### Module: Resources (`apps.resources`)
**Status: ✅ Complete**
- List + detail (viewer), create/edit/delete/toggle/override (admin only)
- Rate priority chain: override → preferred supplier → lowest supplier → master rate

---

### Module: Suppliers (`apps.suppliers`)
**Status: ✅ Complete**
- List + detail (viewer), create/edit/toggle/link/unlink/set-preferred/update-rate (admin only)
- Supplier detail page stays on page after toggle (fixed Jun 2026)

---

### Module: BOM Management (`apps.bom`)
**Status: ✅ Complete**
- BOM list (viewer), add/edit/remove BOM items and WoodParts (admin only)
- Formula types: standard and area

---

### Module: Cost Sheets (`apps.costing`)
**Status: ✅ Complete**
- Cost sheet list and full cost sheet (viewer access)
- Per-product and full workbook Excel export

---

### Module: Excel Import (`apps.imports`)
**Status: ✅ Complete**
- Upload and import (admin only), history and result pages (viewer access)
- ImportLog in Django admin as view/delete only

---

### Module: Excel Export (`apps.costing`)
**Status: ✅ Complete**
- Per-product and full workbook export

---

### Pagination
**Status: ✅ Complete**
- Products, Resources, Suppliers: 25 per page
- Import History: 20 per page
- Filters and search preserved across pages via `{% query_string %}`

---

### Unit Tests (`apps/imports/tests.py`)
**Status: ✅ In place — 6 tests passing**
- Rate priority chain, BOMItem cost with/without supplier
- Run: `python manage.py test apps.imports.tests`

---

## Pending Features

| Priority | Feature | File / Location | Notes |
|---|---|---|---|
| 🟡 MEDIUM | **PostgreSQL migration** | `config/settings.py`, `requirements.txt`, Render config | SQLite resets on every Render deploy |
| 🟢 LOW | **User management UI** | New views in `apps/accounts` | Currently requires Django admin |
| 🟢 LOW | **Password reset flow** | `apps/accounts/urls.py` | No self-service reset |
| 🟢 LOW | **Overhead allocation** | `apps/costing/` | % overhead on top of direct costs |
| 🟢 LOW | **Audit trail** | New middleware or model mixin | Who changed what and when |
| 🟢 LOW | **Supplier additional fields** | `apps/suppliers/models.py` | Address, email, payment terms, lead time |
| 🟢 LOW | **ResourceSupplier fields** | `apps/suppliers/models.py` | stock_available, lead_time_days |
| 🟢 LOW | **BOM versioning / history** | New model in `apps/bom` | Track changes over time |
| 🟢 LOW | **Dashboard enhancements** | `apps/core/views.py` | Top 5 products by cost table |

---

## Known Issues

### 🟡 MEDIUM: ResourceSupplier.supplier_code Is Misleading
Uses join table PK, not Supplier PK. Display-only, low risk.

### 🟢 LOW: SQLite Production Data Loss
Every Render deployment resets the SQLite database.

### 🟢 LOW: No CSRF Audit on Quick-Action Forms
Inline POST forms should be audited for `{% csrf_token %}` before production.

### 🟢 LOW: WoodPart part_name Fallback Risk
If "Parts" column is empty in Excel, multiple cuts of the same material share the same key and overwrite each other on re-import.

---

## Technical Debt

1. **`WoodPart.calculated_quantity` imports `SystemConfig` inside the property** — should be module-level.
2. **Float/Decimal mixing in WoodPart views** — precision risk.
3. **`bom_item.cost` summed in Python, not SQL** — will degrade with large BOMs.
4. **No `select_related` on BOM list for supplier links** — potential N+1 queries.
5. **`_make_product_code` collision risk** — "TEAK WOOD" and "TEAK-WOOD" both produce "TEAK-WOOD".
6. **`category` on Resource is a plain CharField** — can create categories not in `ResourceCategory`.
7. **Portfolio cost on dashboard** summed in Python across all BOM items — acceptable for MVP but will slow with large datasets.

---

## Recent Changes Log

| Date | Change | Files |
|---|---|---|
| Jun 2026 | **Role-based permissions** — `@admin_required` decorator; 403 template; viewer/admin split across all views | `apps/core/decorators.py`, all `views.py` files, `templates/403.html` |
| Jun 2026 | **Dashboard enhancements** — supplier count, portfolio cost, clickable stat cards | `apps/core/views.py`, `templates/core/dashboard.html` |
| Jun 2026 | **Pagination** — 25/page on lists, 20/page on import history; filters preserved | 4 `views.py` files, 4 list templates, `templates/partials/pagination.html` |
| Jun 2026 | **Supplier detail stay-on-page after toggle** — `next` param in form + view | `apps/suppliers/views.py`, `templates/suppliers/supplier_detail.html` |
| Jun 2026 | **ImportLog admin registration** — view/delete only | `apps/imports/admin.py` |
| Jun 2026 | **Fixed WoodPart re-import duplication** — `update_or_create` on `(product, resource, part_name)` | `apps/imports/services.py` |
| Jun 2026 | Supplier Detail Page, redirect bug fix, Excel Export | Various |
| Jun 2026 | Initial project setup through import module | All apps |

---

## Deployment Notes

- **Platform:** Render (free tier or standard)
- **Build script:** `build.sh` — pip install, collectstatic, migrate, createsuperuser
- **Database:** SQLite — **resets on every Render deploy**
- **Default credentials:** `admin` / `changeme123` — change immediately
- **Timezone:** Asia/Kolkata (IST)
- **Required env vars:** `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=your-app.onrender.com`
- **User roles:** Set `is_staff=True` in Django admin for admin users; leave unchecked for viewers

---

## Testing Notes

- **Run:** `python manage.py test apps.imports.tests`
- **6 tests, all passing**
- To test role permissions manually: create a user with `is_staff=False`, verify 403 on any mutation URL