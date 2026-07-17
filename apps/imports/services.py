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
from apps.bom.models import BOMItem, WoodPart, Part
from apps.suppliers.models import Supplier
from apps.imports.models import ImportLog

# Valid dimension units — single source of truth shared by validate_wood
# (rejects bad WU/BU/LU cells) and import_wood (trusts they're clean).
_VALID_UNITS = {choice[0] for choice in WoodPart.UNIT_CHOICES}


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
        with pd.ExcelFile(path) as xl:
            df = pd.read_excel(xl, sheet_name=sheet_name)
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
        'sheet':   sheet,
        'row':     row,
        'message': message,
    }


def _sheet_exists(path, sheet_name):
    """Returns True if the workbook contains the named sheet."""
    try:
        with pd.ExcelFile(path) as xl:
            return sheet_name in xl.sheet_names
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════
# PHASE 1 — VALIDATORS
# Each validator returns a list of error dicts.
# Validators NEVER write to the database.
# ════════════════════════════════════════════════════════════════════

def validate_resources(path):
    """
    Validates the Resource sheet.

    Checks:
    - Sheet exists and required columns present
    - No empty resource names, categories, or units
    - Rate is numeric and non-negative
    - No duplicate resource names within the file
    """
    errors = []
    sheet  = 'Resource'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required     = ['Resource', 'Category', 'Units', 'Rate']
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing_cols)}. '
            f'Found: {", ".join(df.columns.tolist())}')]

    seen_names = {}

    for idx, row in df.iterrows():
        excel_row = idx + 2
        name      = _normalize(row['Resource'])
        category  = _normalize(row['Category'])
        unit      = _normalize(row['Units'])
        rate_raw  = row['Rate']

        # Skip completely blank rows
        if not name and not category and pd.isna(rate_raw):
            continue

        if not name:
            errors.append(_err(sheet, excel_row,
                'Resource Name is empty.'))
            continue

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
                f'"{name}": Rate "{rate_raw}" is not a valid number.'))

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
    - Skips known placeholder rows
    """
    errors      = []
    sheet       = 'Products'
    seen_names  = {}
    seen_codes  = {}
    SKIP_VALUES = {'column1', 'products', 'select', ''}

    try:
        df = pd.read_excel(path, sheet_name=sheet,
                           header=None, usecols=[0])
    except Exception as e:
        return [_err(sheet, '—', f'Cannot read sheet: {e}')]

    for idx, row in df.iterrows():
        excel_row = idx + 1
        name      = _normalize(row[0])

        if name.lower() in SKIP_VALUES:
            continue

        code = _make_product_code(name)

        if name.lower() in seen_names:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Duplicate product name. '
                f'First seen at row {seen_names[name.lower()]}.'))
        else:
            seen_names[name.lower()] = excel_row

        if code in seen_codes:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Generates duplicate product code '
                f'"{code}". First seen at row {seen_codes[code]}.'))
        else:
            seen_codes[code] = excel_row

    return errors

def validate_parts(path):
    """
    Validates the Parts sheet.
    Columns: Product (forward-filled), Part.
    """
    errors = []
    sheet  = 'Parts'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Product', 'Part']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—', f'Missing columns: {", ".join(missing)}.')]

    df['Product'] = df['Product'].ffill()
    valid_products = _get_product_names_from_file(path)

    for idx, row in df.iterrows():
        excel_row    = idx + 2
        product_name = _normalize(row['Product'])
        part_name    = _normalize(row['Part'])

        if not product_name and not part_name:
            continue
        if not product_name:
            errors.append(_err(sheet, excel_row, 'Product is empty.'))
            continue
        if not part_name:
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Part name is empty.'))
            continue

        code = _make_product_code(product_name)
        if (product_name.lower() not in valid_products
                and code not in valid_products):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Not found in Products sheet.'))

    return errors

def validate_bom(path):
    """
    Validates the BOM sheet.

    Checks:
    - Sheet exists and required columns present
    - Product and Resource names not empty (after forward-fill)
    - Quantity is numeric and positive
    - Cross-references Products and Resources from the same file
    """
    errors = []
    sheet  = 'BOM'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Product', 'Resource', 'Quantity']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing)}.')]

    df['Product'] = df['Product'].ffill()

    valid_products  = _get_product_names_from_file(path)
    valid_resources = _get_resource_names_from_file(path)

    for idx, row in df.iterrows():
        excel_row     = idx + 2
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

        try:
            if pd.isna(qty_raw):
                raise ValueError('blank')
            qty = float(qty_raw)
            if qty <= 0:
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}" / "{resource_name}": '
                    f'Quantity must be greater than 0 (got {qty_raw}).'))
        except (ValueError, TypeError):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}" / "{resource_name}": '
                f'Quantity "{qty_raw}" is not a valid number.'))

        product_code = _make_product_code(product_name)
        if (product_name.lower() not in valid_products
                and product_code not in valid_products):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Not found in the Products sheet. '
                f'Add it to the Products sheet first.'))

        if resource_name.lower() not in valid_resources:
            errors.append(_err(sheet, excel_row,
                f'"{resource_name}": Not found in the Resource sheet. '
                f'Add it to the Resource sheet first.'))

    return errors


def validate_wood(path):
    """
    Validates the Wood/Ply/MDF (Dimensions) sheet.

    Checks:
    - Sheet exists and required columns present
    - Product and Resource names not empty (after forward-fill)
    - Width/Breath always numeric and non-negative; Length only checked
      for solid_wood resources — sheet materials (Plywood/MDF/PLPB) use
      Width x Breadth for their SFT formula and never touch Length, so a
      blank/garbage Length or Length Unit there is not a real error.
    - Width/Breadth Units always checked; Length Unit only checked for
      solid_wood resources, for the same reason.
    - Cross-references Products and Resources from the same file
    """
    errors = []
    sheet  = 'Wood, Ply MDF'

    df, read_error = _read_sheet(path, sheet)
    if read_error:
        return [_err(sheet, '—', f'Cannot read sheet: {read_error}')]

    required = ['Product', 'Resource', 'Width', 'Breath', 'Length']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing)}.')]

    df['Product'] = df['Product'].ffill()

    valid_products  = _get_product_names_from_file(path)
    valid_resources = _get_resource_names_from_file(path)

    # Resource name (lowercased) -> material_type, for skipping Length
    # checks on sheet goods. Only resources already saved in the DB are
    # known here — a resource being imported for the first time in this
    # same file falls back to 'unknown' and gets the stricter (solid_wood
    # style) validation, since we can't yet tell what it is.
    material_types = dict(
        Resource.objects.filter(active=True)
        .values_list('resource_name', 'material_type')
    )
    material_types = {name.lower(): mt for name, mt in material_types.items()}

    for idx, row in df.iterrows():
        excel_row     = idx + 2
        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        part_value = _normalize(row.get('Parts', ''))

        if not part_value or part_value.lower() == 'select':
            errors.append(_err(sheet, excel_row,
                f'"{product_name}" / "{resource_name}": '
                f'Parts value is missing or still set to "Select". '
                f'Enter the actual part name (e.g. "Leg 1", "Table Top").'))

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

        material_type = material_types.get(resource_name.lower())
        is_sheet = material_type == 'sheet'

        dim_cols = ['Width', 'Breath'] if is_sheet else ['Width', 'Breath', 'Length']
        for dim_col in dim_cols:
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

        unit_cols = ([('WU', 'Width'), ('BU', 'Breath')] if is_sheet
                     else [('WU', 'Width'), ('BU', 'Breath'), ('LU', 'Length')])
        for unit_col, dim_label in unit_cols:
            unit_val = _normalize(row.get(unit_col)).lower()
            if unit_val not in _VALID_UNITS:
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}" / "{resource_name}": '
                    f'{dim_label} Unit ("{unit_val or "blank"}") is not valid. '
                    f'Must be one of: {", ".join(sorted(_VALID_UNITS))}.'))

        product_code = _make_product_code(product_name)
        if (product_name.lower() not in valid_products
                and product_code not in valid_products):
            errors.append(_err(sheet, excel_row,
                f'"{product_name}": Not found in Products sheet.'))

        if resource_name.lower() not in valid_resources:
            errors.append(_err(sheet, excel_row,
                f'"{resource_name}": Not found in Resource sheet.'))

    return errors


def validate_suppliers(path):
    """
    Validates the Suppliers sheet.

    Your file structure:
        Row 0: 'Table 1' (title — skipped)
        Row 1: 'Supplier ID | Supplier Name | Supplier Mobile' (header)
        Row 2+: actual data

    Checks:
    - Sheet exists
    - Required columns present (Supplier Name, Supplier Mobile)
    - Supplier Name not empty
    - Phone number not empty
    - No duplicate supplier names within the file
    """
    errors = []
    sheet  = 'Suppliers'

    try:
        # header=1 means use row index 1 as column names
        # (skips 'Table 1' title row at index 0)
        df = pd.read_excel(path, sheet_name=sheet, header=1)
        df.columns = df.columns.str.strip()
    except Exception as e:
        return [_err(sheet, '—', f'Cannot read sheet: {e}')]

    required = ['Supplier Name', 'Supplier Mobile']
    missing  = [c for c in required if c not in df.columns]
    if missing:
        return [_err(sheet, '—',
            f'Missing columns: {", ".join(missing)}. '
            f'Found: {", ".join(df.columns.tolist())}')]

    seen_names = {}

    for idx, row in df.iterrows():
        # header is at Excel row 2, data starts at row 3
        # pandas idx 0 = Excel row 3
        excel_row = idx + 3

        name  = _normalize(row.get('Supplier Name', ''))
        phone = _normalize(str(row.get('Supplier Mobile', '')))

        # Skip completely blank rows
        if not name and (not phone or phone == 'nan'):
            continue

        if not name:
            errors.append(_err(sheet, excel_row,
                'Supplier Name is empty.'))
            continue

        if not phone or phone == 'nan':
            errors.append(_err(sheet, excel_row,
                f'"{name}": Phone number is empty.'))

        # Duplicate name check within file
        name_lower = name.lower()
        if name_lower in seen_names:
            errors.append(_err(sheet, excel_row,
                f'"{name}": Duplicate supplier name. '
                f'First seen at row {seen_names[name_lower]}.'))
        else:
            seen_names[name_lower] = excel_row

    return errors


# ── Cross-reference helpers ───────────────────────────────────────────

def _get_product_names_from_file(path):
    """
    Returns a set of product names/codes from the Products sheet.
    Used by BOM and Wood validators for cross-referencing.
    """
    try:
        df   = pd.read_excel(path, sheet_name='Products',
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


# ── Master validator ──────────────────────────────────────────────────

def validate_workbook(path):
    """
    Runs all sheet validators.
    Only validates sheets that actually exist in the workbook.
    Returns:
        {
            'valid': bool,
            'errors': [list of error dicts],
            'error_count': int,
            'sheets_checked': [list of sheet names],
        }
    """
    all_errors     = []
    sheets_checked = []

    # Core sheets — always validated if present
    validators = [
        ('Resource',      validate_resources),
        ('Products',      validate_products),
        ('BOM',           validate_bom),
        ('Wood, Ply MDF', validate_wood),
        ('Suppliers',     validate_suppliers),
        ('Parts',         validate_parts),
    ]

    for sheet_name, validator_fn in validators:
        if _sheet_exists(path, sheet_name):
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
# Only run after validate_workbook() returns valid=True.
# Each importer assumes data is already validated.
# ════════════════════════════════════════════════════════════════════

def import_resources(path):
    result = {'imported': 0, 'updated': 0, 'errors': []}

    df, read_error = _read_sheet(path, 'Resource')
    if read_error or df is None:
        return result

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
            resource.unit   = unit
            resource.rate   = rate
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

        code     = _make_product_code(name)
        existing = Product.objects.filter(product_code=code).first()

        if existing:
            if existing.is_deleted:
                existing.is_deleted   = False
                existing.active       = True
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

def import_parts(path):
    result = {'imported': 0, 'updated': 0, 'errors': []}

    df, read_error = _read_sheet(path, 'Parts')
    if read_error or df is None:
        return result

    df['Product'] = df['Product'].ffill()

    for _, row in df.iterrows():
        product_name = _normalize(row['Product'])
        part_name    = _normalize(row['Part'])

        if not product_name or not part_name:
            continue

        code    = _make_product_code(product_name)
        product = Product.objects.filter(
            product_code=code, is_deleted=False
        ).first()
        if not product:
            continue

        _, created = Part.objects.get_or_create(
            product=product, name=part_name
        )
        if created:
            result['imported'] += 1
        else:
            result['updated'] += 1

    return result

def import_bom(path):
    result = {'imported': 0, 'skipped': 0, 'errors': []}

    df, read_error = _read_sheet(path, 'BOM')
    if read_error or df is None:
        return result

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
    """
    Imports the Wood/Ply/MDF dimensions sheet.

    Only called after validate_wood() has passed — WU/BU/LU are
    therefore guaranteed to already be valid entries from
    WoodPart.UNIT_CHOICES, so no defaulting/fallback logic is needed
    here (see validate_wood for the unit checks).

    Length is read and stored for every row, but note it is NOT used
    in the SFT calculation for sheet materials (Plywood/MDF/PLPB) —
    WoodPart.calculated_quantity uses Width x Breadth for those.
    Length only participates in the CFT formula for solid wood.
    """
    result = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    df, read_error = _read_sheet(path, 'Wood, Ply MDF')
    if read_error or df is None:
        return result

    df['Product'] = df['Product'].ffill()

    for _, row in df.iterrows():
        product_name  = _normalize(row['Product'])
        resource_name = _normalize(row['Resource'])
        part_name = _normalize(row.get('Parts', ''))

        if not product_name or not resource_name:
            continue

        try:
            width   = float(row['Width'])
            breadth = float(row['Breath'])
            length  = float(row['Length'])
            pieces  = int(float(row.get('Quantity', 1) or 1))
            # Length is allowed to be 0/blank — sheet materials don't
            # use it. Width and Breadth are required by both formulas.
            if width <= 0 or breadth <= 0:
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

        # WU/BU/LU are trusted here — validate_wood already rejected
        # any row with a missing/invalid unit before import ever runs.
        width_unit   = _normalize(row.get('WU')).lower()
        breadth_unit = _normalize(row.get('BU')).lower()
        length_unit  = _normalize(row.get('LU')).lower()

        # Use update_or_create keyed on (product, resource, part_name).
        # If a matching WoodPart already exists, its dimensions are updated.
        # If no match exists, a new record is created.
        # This prevents duplicate rows when the same file is re-imported.
        _, created = WoodPart.objects.update_or_create(
            product=product,
            resource=resource,
            part_name=part_name,
            defaults={
                'width':        width,
                'width_unit':   width_unit,
                'breadth':      breadth,
                'breadth_unit': breadth_unit,
                'length':       length,
                'length_unit':  length_unit,
                'pieces':       pieces,
                'part':         Part.objects.get_or_create(
                                    product=product, name=part_name
                                )[0],
            },
        )

        if created:
            result['imported'] += 1
        else:
            result['updated'] += 1

    return result


def import_suppliers(path):
    """
    Imports the Suppliers sheet.
    Uses get_or_create on supplier_name to avoid duplicates.
    Updates phone number if supplier already exists.
    """
    result = {'imported': 0, 'updated': 0, 'errors': []}

    try:
        # Skip row 0 (title 'Table 1'), use row 1 as header
        df = pd.read_excel(path, sheet_name='Suppliers', header=1)
        df.columns = df.columns.str.strip()
    except Exception as e:
        result['errors'].append(str(e))
        return result

    for _, row in df.iterrows():
        name  = _normalize(row.get('Supplier Name', ''))
        phone = _normalize(str(row.get('Supplier Mobile', '')))

        if not name:
            continue

        # Clean phone — pandas reads numbers without leading zeros
        # and NaN becomes the string 'nan'
        if phone == 'nan':
            phone = ''

        supplier, created = Supplier.objects.get_or_create(
            supplier_name=name,
            defaults={
                'phone_number': phone,
                'active':       True,
            }
        )
        if created:
            result['imported'] += 1
        else:
            if phone and supplier.phone_number != phone:
                supplier.phone_number = phone
                supplier.save()
            result['updated'] += 1

    return result


# ── Master import orchestrator ────────────────────────────────────────

def import_workbook(path, log, uploaded_by):
    """
    Runs all importers inside one atomic transaction.
    Receives an existing ImportLog to update (not create new).
    Only called AFTER validate_workbook() returns valid=True.

    If anything fails mid-import, the entire transaction rolls back.
    """
    try:
        with transaction.atomic():
            r = import_resources(path) if _sheet_exists(path, 'Resource') else {'imported': 0, 'updated': 0, 'errors': []}
            p = import_products(path) if _sheet_exists(path, 'Products') else {'imported': 0, 'updated': 0, 'errors': []}
            pt = import_parts(path) if _sheet_exists(path, 'Parts') else {'imported': 0, 'updated': 0, 'errors': []}
            b = import_bom(path) if _sheet_exists(path, 'BOM') else {'imported': 0, 'skipped': 0, 'errors': []}
            w = import_wood(path) if _sheet_exists(path, 'Wood, Ply MDF') else {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': []}
            s = (import_suppliers(path)
                 if _sheet_exists(path, 'Suppliers')
                 else {'imported': 0, 'updated': 0})

            log.resources_imported  = r['imported'] + r['updated']
            log.products_imported   = p['imported'] + p['updated']
            log.parts_imported      = pt['imported'] + pt['updated']
            log.bom_rows_imported   = b['imported']
            log.wood_parts_imported = w['imported'] + w['updated']
            log.suppliers_imported  = s['imported'] + s['updated']
            log.status              = 'success'
            log.error_log           = ''
            log.save()

    except Exception as e:
        log.status    = 'failed'
        log.error_log = f'Critical error during import: {e}'
        log.save()

    return log


# ════════════════════════════════════════════════════════════════════
# SINGLE-SHEET VALIDATION & IMPORT
# Used when user selects "Import Suppliers Only" etc.
# Adding a new sheet in future = add one entry to SHEET_REGISTRY.
# ════════════════════════════════════════════════════════════════════

SHEET_REGISTRY = {
    'resources': {
        'label':     'Resources',
        'sheet':     'Resource',
        'validator': validate_resources,
        'importer':  import_resources,
        'log_field': 'resources_imported',
    },
    'products': {
        'label':     'Products',
        'sheet':     'Products',
        'validator': validate_products,
        'importer':  import_products,
        'log_field': 'products_imported',
    },
    'parts': {
        'label':     'Parts',
        'sheet':     'Parts',
        'validator': validate_parts,
        'importer':  import_parts,
        'log_field': 'parts_imported',
    },
    'bom': {
        'label':     'BOM',
        'sheet':     'BOM',
        'validator': validate_bom,
        'importer':  import_bom,
        'log_field': 'bom_rows_imported',
    },
    'wood': {
        'label':     'Dimensions (Wood/Ply/MDF)',
        'sheet':     'Wood, Ply MDF',
        'validator': validate_wood,
        'importer':  import_wood,
        'log_field': 'wood_parts_imported',
    },
    'suppliers': {
        'label':     'Suppliers',
        'sheet':     'Suppliers',
        'validator': validate_suppliers,
        'importer':  import_suppliers,
        'log_field': 'suppliers_imported',
    },
}


def validate_single_sheet(path, sheet_key):
    """
    Validates one sheet only.
    BOM and Wood cross-reference the database instead of the file
    when imported individually (since the other sheets aren't present).
    """
    if sheet_key not in SHEET_REGISTRY:
        return {
            'valid':          False,
            'errors':         [_err('—', '—',
                               f'Unknown sheet key: {sheet_key}')],
            'error_count':    1,
            'sheets_checked': [],
        }

    entry = SHEET_REGISTRY[sheet_key]

    if sheet_key in ('bom', 'wood'):
        errors = _validate_bom_or_wood_against_db(path, sheet_key)
    else:
        errors = entry['validator'](path)

    return {
        'valid':          len(errors) == 0,
        'errors':         errors,
        'error_count':    len(errors),
        'sheets_checked': [entry['sheet']],
    }


def _validate_bom_or_wood_against_db(path, sheet_key):
    """
    Validates BOM or Wood cross-references against the database
    instead of against sheets in the same file.
    Used when importing BOM or Wood individually.
    """
    errors = []

    if sheet_key == 'bom':
        sheet      = 'BOM'
        df, read_error = _read_sheet(path, sheet)
        if read_error:
            return [_err(sheet, '—',
                f'Cannot read sheet: {read_error}')]

        required = ['Product', 'Resource', 'Quantity']
        missing  = [c for c in required if c not in df.columns]
        if missing:
            return [_err(sheet, '—',
                f'Missing columns: {", ".join(missing)}.')]

        df['Product'] = df['Product'].ffill()

        db_product_codes = set(
            Product.objects.filter(
                is_deleted=False
            ).values_list('product_code', flat=True)
        )
        db_product_name_codes = {
            _make_product_code(name)
            for name in Product.objects.filter(
                is_deleted=False
            ).values_list('product_name', flat=True)
        }
        db_resources = set(
            Resource.objects.filter(
                active=True
            ).values_list('resource_name', flat=True)
        )

        for idx, row in df.iterrows():
            excel_row     = idx + 2
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
                    f'"{product_name}": Resource is empty.'))
                continue

            try:
                if pd.isna(qty_raw):
                    raise ValueError()
                qty = float(qty_raw)
                if qty <= 0:
                    errors.append(_err(sheet, excel_row,
                        f'"{product_name}" / "{resource_name}": '
                        f'Quantity must be > 0.'))
            except (ValueError, TypeError):
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}" / "{resource_name}": '
                    f'Quantity "{qty_raw}" is not valid.'))

            code = _make_product_code(product_name)
            if (code not in db_product_codes
                    and code not in db_product_name_codes):
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}": Not found in database. '
                    f'Import Products first.'))

            if resource_name not in db_resources:
                errors.append(_err(sheet, excel_row,
                    f'"{resource_name}": Not found in database. '
                    f'Import Resources first.'))

    elif sheet_key == 'wood':
        sheet      = 'Wood, Ply MDF'
        df, read_error = _read_sheet(path, sheet)
        if read_error:
            return [_err(sheet, '—',
                f'Cannot read sheet: {read_error}')]

        required = ['Product', 'Resource', 'Width', 'Breath', 'Length']
        missing  = [c for c in required if c not in df.columns]
        if missing:
            return [_err(sheet, '—',
                f'Missing columns: {", ".join(missing)}.')]

        df['Product'] = df['Product'].ffill()

        db_product_codes = set(
            Product.objects.filter(
                is_deleted=False
            ).values_list('product_code', flat=True)
        )
        db_resources = set(
            Resource.objects.filter(
                active=True
            ).values_list('resource_name', flat=True)
        )

        for idx, row in df.iterrows():
            excel_row     = idx + 2
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
                    f'"{product_name}": Resource is empty.'))
                continue

            for dim in ['Width', 'Breath', 'Length']:
                val = row.get(dim)
                try:
                    if pd.isna(val):
                        raise ValueError()
                    f = float(val)
                    if f < 0:
                        errors.append(_err(sheet, excel_row,
                            f'"{product_name}": '
                            f'{dim} cannot be negative.'))
                except (ValueError, TypeError):
                    errors.append(_err(sheet, excel_row,
                        f'"{product_name}": '
                        f'{dim} "{val}" is not valid.'))

            code = _make_product_code(product_name)
            if code not in db_product_codes:
                errors.append(_err(sheet, excel_row,
                    f'"{product_name}": Not found in database.'))

            if resource_name not in db_resources:
                errors.append(_err(sheet, excel_row,
                    f'"{resource_name}": Not found in database.'))

    return errors


def import_single_sheet(path, sheet_key, log, uploaded_by):
    """
    Imports one sheet only.
    Receives existing ImportLog to update.
    Only called after validate_single_sheet() returns valid=True.
    """
    entry = SHEET_REGISTRY[sheet_key]

    try:
        with transaction.atomic():
            result = entry['importer'](path)
            count  = result.get('imported', 0) + result.get('updated', 0)
            setattr(log, entry['log_field'], count)
            log.status    = 'success'
            log.error_log = ''
            log.save()

    except Exception as e:
        log.status    = 'failed'
        log.error_log = f'Critical error: {e}'
        log.save()

    return log