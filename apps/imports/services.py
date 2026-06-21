# apps/imports/services.py

import re
import pandas as pd
from django.db import transaction

from apps.resources.models import Resource
from apps.products.models import Product
from apps.bom.models import BOMItem, WoodPart
from apps.imports.models import ImportLog


# ── Helpers ──────────────────────────────────────────────────────────

def _normalize(value):
    """
    Cleans a single cell value:
    - Strips leading/trailing whitespace
    - Collapses multiple internal spaces into one
    - Returns '' for NaN/None
    
    This handles the common Excel issue where "MDF 18mm" and "MDF 18 mm"
    are the same resource typed differently by different users.
    """
    if pd.isna(value):
        return ''
    # Strip outer whitespace, then collapse all internal whitespace to single space
    return ' '.join(str(value).split())


def _read_sheet(workbook_path, sheet_name):
    """
    Safely reads one named sheet.
    Returns (DataFrame, error_string_or_None).
    """
    try:
        df = pd.read_excel(workbook_path, sheet_name=sheet_name)
        df.columns = df.columns.str.strip()
        return df, None
    except Exception as e:
        return None, str(e)


def _make_product_code(product_name):
    """
    Auto-generates a product code from a product name.
    'Chair Alta'        → 'CHAIR-ALTA'
    'Cot 6 Marigold'   → 'COT-6-MARIGOLD'

    Truncated to 30 characters to fit the model field.
    """
    # Replace any non-alphanumeric character with a hyphen
    code = re.sub(r'[^A-Za-z0-9]+', '-', product_name.strip())
    # Remove leading/trailing hyphens
    code = code.strip('-')
    # Uppercase and truncate
    return code.upper()[:30]


# ── Step 1: Import Resources ─────────────────────────────────────────

def import_resources(workbook_path):
    """
    Reads the 'Resource' sheet.

    Real column names in this workbook:
        Resource | Category | Units | Rate

    Logic:
    - Skip rows where Resource name is blank (trailing junk rows)
    - get_or_create on (resource_name, category)
    - If resource exists: update rate and unit
    - If resource is new: create it
    """
    result = {
        'imported': 0, 'updated': 0,
        'skipped': 0, 'errors': []
    }

    df, error = _read_sheet(workbook_path, 'Resource')
    if error:
        result['errors'].append(f'Cannot read "Resource" sheet: {error}')
        return result

    # Map actual column names to what we need
    # The workbook uses 'Units' not 'unit', 'Resource' not 'resource_name'
    col_map = {
        'Resource': 'resource_name',
        'Category': 'category',
        'Units':    'unit',
        'Rate':     'rate',
    }
    missing = [c for c in col_map.keys() if c not in df.columns]
    if missing:
        result['errors'].append(
            f'Resource sheet missing columns: {missing}. '
            f'Found: {df.columns.tolist()}'
        )
        return result

    df = df.rename(columns=col_map)

    for row_num, row in df.iterrows():
        excel_row = row_num + 2

        resource_name = _normalize(row['resource_name'])
        category      = _normalize(row['category'])
        unit          = _normalize(row['unit'])
        rate_raw      = row['rate']

        # Skip blank rows (the workbook has ~100 trailing empty rows)
        if not resource_name:
            continue

        # Validate rate — also catches NaN explicitly
        try:
            if pd.isna(rate_raw):
                raise ValueError("Rate is blank.")
            rate = float(rate_raw)
            if rate < 0:
                raise ValueError("Rate cannot be negative.")
        except (TypeError, ValueError) as e:
            result['errors'].append(
                f'Row {excel_row}: "{resource_name}" — '
                f'invalid rate "{rate_raw}" ({e}), skipped.'
            )
            result['skipped'] += 1
            continue

        if not unit:
            unit = 'nos'  # Safe default for missing units

        if not category:
            result['errors'].append(
                f'Row {excel_row}: "{resource_name}" has no category, skipped.'
            )
            result['skipped'] += 1
            continue

        try:
            resource, created = Resource.objects.get_or_create(
                resource_name=resource_name,
                category=category,
                defaults={
                    'unit': unit,
                    'rate': rate,
                    'active': True,
                }
            )
            if created:
                result['imported'] += 1
            else:
                # Always update rate and unit from the latest workbook
                resource.unit = unit
                resource.rate = rate
                resource.active = True
                resource.save()
                result['updated'] += 1

        except Exception as e:
            result['errors'].append(
                f'Row {excel_row}: "{resource_name}" — DB error: {e}'
            )
            result['skipped'] += 1

    return result


# ── Step 2: Import Products ───────────────────────────────────────────

def import_products(workbook_path):
    """
    Reads the 'Products' sheet.

    Real structure: single column of product names, no codes.
    Row 0 has header 'Column1', actual names start from row 1.
    One stray row mid-sheet just says 'Products' — we skip it.

    We auto-generate product_code from product_name.
    """
    result = {
        'imported': 0, 'updated': 0,
        'skipped': 0, 'errors': []
    }

    # Read with no header — the sheet has 'Column1'/'Column2' as headers
    # which are not useful. We just want the first column of names.
    try:
        df = pd.read_excel(
            workbook_path,
            sheet_name='Products',
            header=None,
            usecols=[0]   # Only the first column
        )
    except Exception as e:
        result['errors'].append(f'Cannot read "Products" sheet: {e}')
        return result

    for row_num, row in df.iterrows():
        excel_row = row_num + 1

        product_name = _normalize(row[0])

        # Skip blank rows, the header row, and the stray 'Products' label
        if not product_name:
            continue
        if product_name.lower() in ('column1', 'products'):
            continue

        product_code = _make_product_code(product_name)

        try:
            existing = Product.objects.filter(
                product_code=product_code
            ).first()

            if existing:
                if existing.is_deleted:
                    # Restore soft-deleted product
                    existing.is_deleted = False
                    existing.active = True
                    existing.product_name = product_name
                    existing.save()
                    result['updated'] += 1
                else:
                    # Already exists and is active — nothing to do
                    result['updated'] += 1
            else:
                Product.objects.create(
                    product_code=product_code,
                    product_name=product_name,
                    active=True,
                )
                result['imported'] += 1

        except Exception as e:
            result['errors'].append(
                f'Row {excel_row}: "{product_name}" — DB error: {e}'
            )
            result['skipped'] += 1

    return result


# ── Step 3: Import BOM Items ─────────────────────────────────────────

def import_bom(workbook_path):
    """
    Reads the 'BOM' sheet.

    Real columns: Product | Resource | Units | Rate | Quantity | Cost
    (Rate and Cost are Excel-computed — we IGNORE them entirely.
     Our system always calculates cost from the Resource master rate.)

    Key challenge: 227 rows have blank Product name due to merged cells.
    Fix: forward-fill the Product column downward.
    """
    result = {
        'imported': 0, 'skipped': 0, 'errors': []
    }

    df, error = _read_sheet(workbook_path, 'BOM')
    if error:
        result['errors'].append(f'Cannot read "BOM" sheet: {error}')
        return result

    required = ['Product', 'Resource', 'Quantity']
    missing = [c for c in required if c not in df.columns]
    if missing:
        result['errors'].append(
            f'BOM sheet missing columns: {missing}. Found: {df.columns.tolist()}'
        )
        return result

    # THE KEY FIX: forward-fill Product column
    # Blank product names mean "same as the row above" (merged cells in Excel)
    df['Product'] = df['Product'].fillna(method='ffill')

    for row_num, row in df.iterrows():
        excel_row = row_num + 2

        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        qty_raw       = row['Quantity']

        # Skip if essential data is missing
        if not product_name or not resource_name:
            continue

        # Validate quantity
        try:
            quantity = float(qty_raw)
            if quantity <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            result['errors'].append(
                f'Row {excel_row}: "{product_name}" / "{resource_name}" '
                f'— invalid quantity "{qty_raw}", skipped.'
            )
            result['skipped'] += 1
            continue

        # Look up product (by auto-generated code)
        product_code = _make_product_code(product_name)
        product = Product.objects.filter(
            product_code=product_code,
            is_deleted=False
        ).first()

        if not product:
            result['errors'].append(
                f'Row {excel_row}: Product "{product_name}" not found in database. '
                f'Import Products first.'
            )
            result['skipped'] += 1
            continue

        # Look up resource by name
        resource = Resource.objects.filter(
            resource_name=resource_name,
            active=True
        ).first()

        if not resource:
            result['errors'].append(
                f'Row {excel_row}: Resource "{resource_name}" not found. '
                f'Import Resources first.'
            )
            result['skipped'] += 1
            continue

        # get_or_create to avoid duplicates
        # unique_together on (product, resource) means only one BOM item
        # per product-resource combination
        try:
            bom_item, created = BOMItem.objects.get_or_create(
                product=product,
                resource=resource,
                defaults={'quantity': quantity}
            )
            if not created:
                # Update quantity if it changed
                bom_item.quantity = quantity
                bom_item.save()

            result['imported'] += 1

        except Exception as e:
            result['errors'].append(
                f'Row {excel_row}: "{product_name}" / "{resource_name}" '
                f'— DB error: {e}'
            )
            result['skipped'] += 1

    return result


# ── Step 4: Import Wood Parts ─────────────────────────────────────────

def import_wood_parts(workbook_path):
    """
    Reads the 'Wood, Ply MDF' sheet.

    Real columns:
        Product | Parts | Resource | Unit | Width | WU | Breath | BU |
        Length | LU | Quantity | Total

    WU/BU/LU = unit for each dimension ('in' or 'ft').
    We store dimensions as-is. The formula type tells the system
    which divisor to use (1728 for cubic feet, 144 for square feet).

    'Parts' = part_name (can be blank — we default to resource name).
    'Quantity' = already-calculated quantity from Excel.
    We IGNORE 'Total' (Excel cost) — our system calculates cost live.
    """
    result = {
        'imported': 0, 'skipped': 0, 'errors': []
    }

    df, error = _read_sheet(workbook_path, 'Wood, Ply MDF')
    if error:
        result['errors'].append(f'Cannot read "Wood, Ply MDF" sheet: {error}')
        return result

    required = ['Product', 'Resource', 'Width', 'Breath', 'Length']
    missing = [c for c in required if c not in df.columns]
    if missing:
        result['errors'].append(
            f'Wood sheet missing columns: {missing}. Found: {df.columns.tolist()}'
        )
        return result

    # Forward-fill Product column (same merged-cell issue as BOM)
    df['Product'] = df['Product'].fillna(method='ffill')

    for row_num, row in df.iterrows():
        excel_row = row_num + 2

        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        part_name     = _normalize(row.get('Parts', '')) or resource_name

        # Validate dimensions
        try:
            width   = float(row['Width'])
            breadth = float(row['Breath'])
            length  = float(row['Length'])
            pieces  = int(float(row.get('Quantity', 1) or 1))
            if width <= 0 or breadth <= 0 or length <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            if product_name and resource_name:
                result['errors'].append(
                    f'Row {excel_row}: "{product_name}" / "{part_name}" '
                    f'— invalid dimensions, skipped.'
                )
            result['skipped'] += 1
            continue

        if not product_name or not resource_name:
            result['skipped'] += 1
            continue

        product_code = _make_product_code(product_name)
        product = Product.objects.filter(
            product_code=product_code,
            is_deleted=False
        ).first()

        if not product:
            result['errors'].append(
                f'Row {excel_row}: Product "{product_name}" not found.'
            )
            result['skipped'] += 1
            continue

        resource = Resource.objects.filter(
            resource_name=resource_name,
            active=True
        ).first()

        if not resource:
            result['errors'].append(
                f'Row {excel_row}: Resource "{resource_name}" not found.'
            )
            result['skipped'] += 1
            continue

        try:
            WoodPart.objects.create(
                product   = product,
                resource  = resource,
                part_name = part_name,
                width     = width,
                breadth   = breadth,
                length    = length,
                pieces    = pieces,
            )
            result['imported'] += 1

        except Exception as e:
            result['errors'].append(
                f'Row {excel_row}: "{product_name}" / "{part_name}" '
                f'— DB error: {e}'
            )
            result['skipped'] += 1

    return result


# ── Master Import Orchestrator ────────────────────────────────────────

def import_workbook(file_obj, uploaded_by):
    """
    Runs all four import steps in the correct order.
    Saves progress to ImportLog after each step.

    Order matters:
        1. Resources (no dependencies)
        2. Products  (no dependencies)
        3. BOM       (depends on Resources + Products existing)
        4. Wood      (depends on Resources + Products existing)
    """
    log = ImportLog.objects.create(
        file_name=file_obj.name,
        uploaded_by=uploaded_by,
        status='pending',
    )

    all_errors = []

    try:
        # Save the file temporarily so pandas can read it multiple times
        import tempfile, os, shutil
        suffix = os.path.splitext(file_obj.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file_obj, tmp)
            tmp_path = tmp.name

        # Step 1: Resources
        r_result = import_resources(tmp_path)
        all_errors.extend(r_result['errors'])

        # Step 2: Products
        p_result = import_products(tmp_path)
        all_errors.extend(p_result['errors'])

        # Step 3: BOM (needs resources + products to exist first)
        b_result = import_bom(tmp_path)
        all_errors.extend(b_result['errors'])

        # Step 4: Wood Parts
        w_result = import_wood_parts(tmp_path)
        all_errors.extend(w_result['errors'])

        # Clean up temp file
        os.unlink(tmp_path)

        # Update the log
        log.resources_imported  = r_result['imported'] + r_result['updated']
        log.products_imported   = p_result['imported'] + p_result['updated']
        log.bom_rows_imported   = b_result['imported']
        log.wood_parts_imported = w_result['imported']
        log.error_log           = '\n'.join(all_errors)
        log.status              = 'partial' if all_errors else 'success'
        log.save()

        return log, {
            'resources': r_result,
            'products':  p_result,
            'bom':       b_result,
            'wood':      w_result,
        }

    except Exception as e:
        log.status    = 'failed'
        log.error_log = f'Critical failure: {e}'
        log.save()
        return log, None