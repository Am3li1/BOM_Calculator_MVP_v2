# apps/imports/services.py

"""
Import service layer for the BOM Costing System.

Architecture:
    Two-phase approach:
        Phase 1: validate_workbook(path) → list of ValidationError dicts
        Phase 2: import_workbook(path)   → only runs if validation passes

    This guarantees ALL-OR-NOTHING imports.
    Bad data never enters the database.

    Each sheet has its own validator and importer.
    Adding a new sheet = add one validator + one importer.
    Nothing else needs to change.
"""

import re
import pandas as pd
from decimal import Decimal, InvalidOperation
from django.db import transaction

from apps.resources.models import Resource
from apps.products.models import Product
from apps.bom.models import BOMItem, WoodPart
from apps.imports.models import ImportLog


# ── Helpers ───────────────────────────────────────────────────────────

def _normalize(value):
    """Strip whitespace, collapse internal spaces, return '' for NaN."""
    if pd.isna(value):
        return ''
    return ' '.join(str(value).split())


def _read_sheet(path, sheet_name):
    """
    Reads one sheet from the workbook.
    Returns (DataFrame, error_string).
    error_string is None on success.
    """
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
        df.columns = df.columns.str.strip()
        return df, None
    except Exception as e:
        return None, str(e)


def _make_product_code(product_name):
    """Generates a product code from a product name."""
    code = re.sub(r'[^A-Za-z0-9]+', '-', product_name.strip())
    return code.strip('-').upper()[:30]


def _err(sheet, row, message):
    """Creates a standardised error dict."""
    return {
        'sheet': sheet,
        'row':   row,
        'message': message,
    }


# ════════════════════════════════════════════════════════════════════
# PHASE 1 — VALIDATORS
# Each validator returns a list of error dicts.
# Validators NEVER write to the database.
# ════════════════════════════════════════════════════════════════════

def validate_resources(path):
    """
    Validates the Resource sheet.

    Checks:
    - Sheet exists
    - Required columns present
    - No empty resource names
    - No empty categories
    - No empty units
    - Rate is numeric and non-negative
    - No duplicate resource names within the file
    - No duplicate (name, category) combinations within the file
    """
    errors = []
    sheet = 'Resource'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Resource', 'Category', 'Units', 'Rate']
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing_cols)}. '
            f'Found: {", ".join(df.columns.tolist())}')]

    seen_names = {}        # resource_name → first row seen
    seen_name_cat = {}     # (name, category) → first row seen

    for idx, row in df.iterrows():
        excel_row = idx + 2

        name     = _normalize(row['Resource'])
        category = _normalize(row['Category'])
        unit     = _normalize(row['Units'])
        rate_raw = row['Rate']

        # Skip completely blank rows
        if not name and not category and pd.isna(rate_raw):
            continue

        if not name:
            errors.append(_err(sheet, excel_row,
                'Resource Name is empty.'))
            continue   # can't validate further without a name

        if not category:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Category is empty.'))

        if not unit:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Unit is empty.'))

        # Validate rate
        try:
            if pd.isna(rate_raw):
                raise ValueError('blank')
            rate = Decimal(str(rate_raw))
            if rate < 0:
                errors.append(_err(sheet, excel_row,
                    f'"{name}": Rate cannot be negative '
                    f'(got {rate_raw}).'))
        except (ValueError, InvalidOperation):
            errors.append(_err(sheet, excel_row,
                f'"{name}": Rate "{rate_raw}" is not a '
                f'valid number.'))

        # Duplicate name check within file
        if name in seen_names:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Duplicate resource name. '
                f'First seen at row {seen_names[name]}.'))
        else:
            seen_names[name] = excel_row

    return errors


def validate_products(path):
    """
    Validates the Products sheet.

    Checks:
    - Sheet exists
    - Product names not empty
    - No duplicate product names within the file
    - Skips known placeholder rows ('Column1', 'Products', 'select')
    """
    errors = []
    sheet = 'Products'

    try:
        df = pd.read_excel(path, sheet_name=sheet,
                           header=None, usecols=[0])
    except Exception as e:
        return [_err(sheet, '—', f'Cannot read sheet: {e}')]

    seen_names  = {}
    seen_codes  = {}
    SKIP_VALUES = {'column1', 'products', 'select', ''}

    for idx, row in df.iterrows():
        excel_row = idx + 1
        name = _normalize(row[0])

        if name.lower() in SKIP_VALUES:
            continue

        code = _make_product_code(name)

        # Duplicate name check within file
        if name.lower() in seen_names:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Duplicate product name. '
                f'First seen at row {seen_names[name.lower()]}.'))
        else:
            seen_names[name.lower()] = excel_row

        # Duplicate code check within file
        if code in seen_codes:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Generates duplicate product code '
                f'"{code}". '
                f'First seen at row {seen_codes[code]}.'))
        else:
            seen_codes[code] = excel_row

    return errors


def validate_bom(path):
    """
    Validates the BOM sheet.

    Checks:
    - Sheet exists + required columns
    - Product name not empty (after forward-fill)
    - Resource name not empty
    - Quantity is numeric and positive
    - Referenced products exist in Products sheet of same file
    - Referenced resources exist in Resource sheet of same file
    """
    errors = []
    sheet = 'BOM'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Product', 'Resource', 'Quantity']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing)}.')]

    # Forward-fill product column (merged cells in Excel)
    df['Product'] = df['Product'].ffill()

    # Build sets of valid products and resources from the same file
    # so we can cross-reference without hitting the database yet
    valid_products  = _get_product_names_from_file(path)
    valid_resources = _get_resource_names_from_file(path)

    for idx, row in df.iterrows():
        excel_row = idx + 2

        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        qty_raw       = row['Quantity']

        if not product_name and not resource_name:
            continue

        if not product_name:
            errors.append(_err(sheet, excel_row,
                'Product Name is empty.'))
            continue

        if not resource_name:
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Resource Name is empty.'))
            continue

        # Validate quantity
        try:
            if pd.isna(qty_raw):
                raise ValueError('blank')
            qty = float(qty_raw)
            if qty <= 0:
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}" / "{resource_name}": '
                    f'Quantity must be greater than 0 '
                    f'(got {qty_raw}).'))
        except (ValueError, TypeError):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}" / "{resource_name}": '
                f'Quantity "{qty_raw}" is not a valid number.'))

        # Cross-reference checks
        product_code = _make_product_code(product_name)
        if (product_name.lower() not in valid_products
                and product_code not in valid_products):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Product not found in the '
                f'Products sheet. Add it to the Products sheet '
                f'first.'))

        if resource_name.lower() not in valid_resources:
            errors.append(_err(sheet, excel_row,
                f'"{resource_name}": Resource not found in the '
                f'Resource sheet. Add it to the Resource sheet '
                f'first.'))

    return errors


def validate_wood(path):
    """
    Validates the Wood/Ply/MDF (Dimensions) sheet.

    Checks:
    - Sheet exists + required columns
    - Product name not empty (after forward-fill)
    - Resource name not empty
    - Dimensions (Width, Breath, Length) are numeric and positive
    - Referenced products exist in Products sheet
    - Referenced resources exist in Resource sheet
    """
    errors = []
    sheet = 'Wood, Ply MDF'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Product', 'Resource', 'Width', 'Breath', 'Length']
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing)}.')]

    df['Product'] = df['Product'].ffill()

    valid_products  = _get_product_names_from_file(path)
    valid_resources = _get_resource_names_from_file(path)

    for idx, row in df.iterrows():
        excel_row = idx + 2

        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])

        if not product_name and not resource_name:
            continue

        if not product_name:
            errors.append(_err(sheet, excel_row,
                'Product Name is empty.'))
            continue

        if not resource_name:
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Resource Name is empty.'))
            continue

        # Validate dimensions
        for dim_col in ['Width', 'Breath', 'Length']:
            val = row.get(dim_col)
            try:
                if pd.isna(val):
                    raise ValueError('blank')
                f = float(val)
                if f < 0:
                    errors.append(_err(sheet, excel_row,
                        f'"{product_name}" / "{resource_name}": '
                        f'{dim_col} cannot be negative.'))
            except (ValueError, TypeError):
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}" / "{resource_name}": '
                    f'{dim_col} "{val}" is not a valid number.'))

        # Cross-reference checks
        product_code = _make_product_code(product_name)
        if (product_name.lower() not in valid_products
                and product_code not in valid_products):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Not found in Products sheet.'))

        if resource_name.lower() not in valid_resources:
            errors.append(_err(sheet, excel_row,
                f'"{resource_name}": Not found in Resource sheet.'))

    return errors


# ── Cross-reference helpers ───────────────────────────────────────

def _get_product_names_from_file(path):
    """
    Returns a set of lowercase product names from the Products sheet.
    Used for cross-referencing in BOM and Wood validators.
    """
    try:
        df = pd.read_excel(path, sheet_name='Products',
                           header=None, usecols=[0])
        SKIP = {'column1', 'products', 'select', ''}
        names = set()
        for _, row in df.iterrows():
            name = _normalize(row[0])
            if name.lower() not in SKIP:
                names.add(name.lower())
                names.add(_make_product_code(name))
        return names
    except Exception:
        return set()


def _get_resource_names_from_file(path):
    """
    Returns a set of lowercase resource names from the Resource sheet.
    """
    try:
        df = pd.read_excel(path, sheet_name='Resource')
        df.columns = df.columns.str.strip()
        if 'Resource' not in df.columns:
            return set()
        return {
            _normalize(v).lower()
            for v in df['Resource'].dropna()
            if _normalize(v)
        }
    except Exception:
        return set()


# ── Master validator ──────────────────────────────────────────────

def validate_workbook(path):
    """
    Runs all sheet validators.
    Returns a dict:
        {
            'valid': bool,
            'errors': [list of error dicts],
            'error_count': int,
            'sheets_checked': [list of sheet names],
        }
    """
    all_errors = []
    sheets_checked = []

    validators = [
        ('Resource',     validate_resources),
        ('Products',     validate_products),
        ('BOM',          validate_bom),
        ('Wood, Ply MDF', validate_wood),
    ]

    for sheet_name, validator_fn in validators:
        sheets_checked.append(sheet_name)
        sheet_errors = validator_fn(path)
        all_errors.extend(sheet_errors)

    return {
        'valid':          len(all_errors) == 0,
        'errors':         all_errors,
        'error_count':    len(all_errors),
        'sheets_checked': sheets_checked,
    }


# ════════════════════════════════════════════════════════════════════
# PHASE 2 — IMPORTERS
# Importers only run when validate_workbook() returns valid=True.
# Each importer assumes the data is already validated.
# ════════════════════════════════════════════════════════════════════

def import_resources(path):
    result = {'imported': 0, 'updated': 0, 'errors': []}

    df, _ = _read_sheet(path, 'Resource')
    df = df.rename(columns={
        'Resource': 'resource_name',
        'Category': 'category',
        'Units':    'unit',
        'Rate':     'rate',
    })

    for _, row in df.iterrows():
        name     = _normalize(row['resource_name'])
        category = _normalize(row['category'])
        unit     = _normalize(row['unit'])

        if not name:
            continue

        try:
            rate = Decimal(str(row['rate']))
        except Exception:
            continue

        resource, created = Resource.objects.get_or_create(
            resource_name=name,
            category=category,
            defaults={'unit': unit, 'rate': rate, 'active': True}
        )
        if created:
            result['imported'] += 1
        else:
            resource.unit = unit
            resource.rate = rate
            resource.active = True
            resource.save()
            result['updated'] += 1

    return result


def import_products(path):
    result = {'imported': 0, 'updated': 0, 'errors': []}

    try:
        df = pd.read_excel(path, sheet_name='Products',
                           header=None, usecols=[0])
    except Exception:
        return result

    SKIP = {'column1', 'products', 'select', ''}

    for _, row in df.iterrows():
        name = _normalize(row[0])
        if name.lower() in SKIP:
            continue

        code = _make_product_code(name)

        existing = Product.objects.filter(product_code=code).first()
        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
                existing.active = True
                existing.product_name = name
                existing.save()
            result['updated'] += 1
        else:
            Product.objects.create(
                product_code=code,
                product_name=name,
                active=True,
            )
            result['imported'] += 1

    return result


def import_bom(path):
    result = {'imported': 0, 'skipped': 0, 'errors': []}

    df, _ = _read_sheet(path, 'BOM')
    df['Product'] = df['Product'].ffill()

    for _, row in df.iterrows():
        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        qty_raw       = row['Quantity']

        if not product_name or not resource_name:
            continue

        try:
            qty = float(qty_raw)
            if qty <= 0:
                continue
        except (ValueError, TypeError):
            continue

        code    = _make_product_code(product_name)
        product = Product.objects.filter(
            product_code=code, is_deleted=False
        ).first()
        resource = Resource.objects.filter(
            resource_name=resource_name, active=True
        ).first()

        if not product or not resource:
            result['skipped'] += 1
            continue

        bom_item, created = BOMItem.objects.get_or_create(
            product=product,
            resource=resource,
            defaults={'quantity': qty}
        )
        if not created:
            bom_item.quantity = qty
            bom_item.save()

        result['imported'] += 1

    return result


def import_wood(path):
    result = {'imported': 0, 'skipped': 0, 'errors': []}

    df, _ = _read_sheet(path, 'Wood, Ply MDF')
    df['Product'] = df['Product'].ffill()

    for _, row in df.iterrows():
        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        part_name     = _normalize(row.get('Parts', '')) or resource_name

        if not product_name or not resource_name:
            continue

        try:
            width   = float(row['Width'])
            breadth = float(row['Breath'])
            length  = float(row['Length'])
            pieces  = int(float(row.get('Quantity', 1) or 1))
            if width <= 0 or breadth <= 0 or length <= 0:
                continue
        except (ValueError, TypeError):
            continue

        code     = _make_product_code(product_name)
        product  = Product.objects.filter(
            product_code=code, is_deleted=False
        ).first()
        resource = Resource.objects.filter(
            resource_name=resource_name, active=True
        ).first()

        if not product or not resource:
            result['skipped'] += 1
            continue

        WoodPart.objects.create(
            product=product, resource=resource,
            part_name=part_name,
            width=width, breadth=breadth,
            length=length, pieces=pieces,
        )
        result['imported'] += 1

    return result


# ── Master import orchestrator ────────────────────────────────────

def import_workbook(path, file_obj, uploaded_by):
    """
    Runs all importers inside a single atomic transaction.
    Only called AFTER validate_workbook() returns valid=True.

    If anything fails mid-import, the entire transaction rolls back.
    """
    log = ImportLog.objects.create(
        file_name=file_obj.name if file_obj else str(path),
        uploaded_by=uploaded_by,
        status='pending',
    )

    try:
        with transaction.atomic():
            r = import_resources(path)
            p = import_products(path)
            b = import_bom(path)
            w = import_wood(path)

            log.resources_imported  = r['imported'] + r['updated']
            log.products_imported   = p['imported'] + p['updated']
            log.bom_rows_imported   = b['imported']
            log.wood_parts_imported = w['imported']
            log.status              = 'success'
            log.error_log           = ''
            log.save()

    except Exception as e:
        log.status    = 'failed'
        log.error_log = f'Critical error during import: {e}'
        log.save()

    return log