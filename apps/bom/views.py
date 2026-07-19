from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.decorators import admin_required
from django.contrib import messages

from apps.products.models import Product
from .models import BOMItem


@login_required
@admin_required
def bom_list(request, product_pk):
    from .models import WoodPart

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    bom_items  = BOMItem.objects.filter(
        product=product
    ).select_related('resource')

    wood_parts = WoodPart.objects.filter(
        product=product
    ).select_related('resource', 'part').order_by('part__name', 'resource__resource_name')

    # ── Rule change (intentional): Dimensional BOM cost now counts ──
    # Standard BOM (BOMItem) and Dimensional BOM (WoodPart) are two
    # distinct, non-overlapping cost buckets — a resource belongs to
    # ONE or the other for a given product, never both. Grand total is
    # their sum. (Previously WoodPart cost was reference-only; see
    # CLAUDE.md for the history of this rule.)
    total_bom_cost       = sum(item.cost for item in bom_items)
    total_dimensional_cost = sum(part.cost for part in wood_parts)
    grand_total          = total_bom_cost + total_dimensional_cost

    context = {
        'page_title': f'BOM — {product.product_code}',
        'product': product,
        'bom_items': bom_items,
        'wood_parts': wood_parts,
        'total_bom_cost': total_bom_cost,
        'total_dimensional_cost': total_dimensional_cost,
        'grand_total': grand_total,
    }
    return render(request, 'bom/list.html', context)


@login_required
@admin_required
def bom_add(request, product_pk):
    from apps.resources.models import Resource

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    existing_resource_ids = BOMItem.objects.filter(
        product=product
    ).values_list('resource_id', flat=True)

    # Category-wise, alphabetical-within-category — same ordering
    # used by woodpart_add/woodpart_edit for their resource combobox.
    available_resources = list(
        Resource.objects.filter(
            active=True
        ).exclude(id__in=existing_resource_ids).order_by('category', 'resource_name')
    )

    if request.method == 'POST':
        resource_id = request.POST.get('resource')
        quantity = request.POST.get('quantity')

        if not resource_id or not quantity:
            messages.error(request, 'Please select a resource and enter a quantity.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)
                qty = float(quantity)
                if qty <= 0:
                    raise ValueError("Quantity must be positive.")

                BOMItem.objects.create(
                    product=product,
                    resource=resource,
                    quantity=qty,
                )
                messages.success(request, f'"{resource.resource_name}" added to BOM.')
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError as e:
                messages.error(request, f'Invalid quantity: {e}')

    context = {
        'page_title': f'Add BOM Item — {product.product_code}',
        'product': product,
        'available_resources': available_resources,
        # Flat list for the type-to-filter combobox JS — same shape as
        # woodpart_add's resource_options, plus rate (this page has no
        # material-type unit-defaulting logic, so that map isn't needed
        # here, but showing the rate replaces what the old native
        # <select> used to display inline).
        'resource_options': [
            {
                'id': r.pk,
                'name': r.resource_name,
                'category': r.category,
                'unit': r.unit,
                'rate': str(r.effective_rate),
            }
            for r in available_resources
        ],
    }
    return render(request, 'bom/bom_add.html', context)


@login_required
@admin_required
def bom_remove(request, pk):
    bom_item = get_object_or_404(BOMItem, pk=pk)
    product_pk = bom_item.product.pk

    if request.method == 'POST':
        resource_name = bom_item.resource.resource_name
        bom_item.delete()
        messages.success(request, f'"{resource_name}" removed from BOM.')

    return redirect('bom:list', product_pk=product_pk)


@login_required
@admin_required
def bom_edit_quantity(request, pk):
    bom_item = get_object_or_404(BOMItem, pk=pk)
    product_pk = bom_item.product.pk

    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        try:
            qty = float(quantity)
            if qty <= 0:
                raise ValueError("Must be positive.")
            bom_item.quantity = qty
            bom_item.save()
            messages.success(request, 'Quantity updated.')
        except (TypeError, ValueError) as e:
            messages.error(request, f'Invalid quantity: {e}')

    return redirect('bom:list', product_pk=product_pk)

@login_required
@admin_required
def woodpart_add(request, product_pk):
    """
    Adds a Dimension entry to a product.
    All active resources are available (not just Wood/Ply/MDF).
    """
    from apps.resources.models import Resource
    from .models import Part

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)
    all_resources = Resource.objects.filter(active=True).order_by('category', 'resource_name')
    existing_parts = Part.objects.filter(product=product)

    # Unit choices passed to template so we don't hardcode them there
    unit_choices = [
        ('cm',   'Centimeters'),
        ('cft',  'Cubic Feet'),
        ('ft',   'Feet'),
        ('in',   'Inches'),
        ('m',    'Meters'),
        ('mm',   'Millimeters'),
        ('nos',  'Numbers'),
        ('sqft', 'Square Feet'),
    ]
    
    if request.method == 'POST':
        from .models import WoodPart
        from apps.core.safe_eval import FormulaError

        resource_id  = request.POST.get('resource')
        part_id      = request.POST.get('part')
        new_part_name = request.POST.get('new_part_name', '').strip()
        width        = request.POST.get('width')
        breadth      = request.POST.get('breadth')
        height       = request.POST.get('height') or '0'
        length       = request.POST.get('length')
        pieces       = request.POST.get('pieces')
        width_unit   = request.POST.get('width_unit', 'in')
        breadth_unit = request.POST.get('breadth_unit', 'in')
        height_unit  = request.POST.get('height_unit', 'in')
        length_unit  = request.POST.get('length_unit', 'in')

        # Only honour the typed formula if the checkbox is actually
        # checked — avoids accidentally saving stale text left in a
        # hidden field.
        use_custom_formula = request.POST.get('use_custom_formula') == 'on'
        formula_expression = (
            request.POST.get('formula_expression', '').strip()
            if use_custom_formula else ''
        )

        if not all([resource_id, part_id, width, breadth, length, pieces]) or \
           (part_id == '__new__' and not new_part_name):
            messages.error(request, 'All fields except Height are required.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)
                if part_id == '__new__':
                    part_obj, _ = Part.objects.get_or_create(
                        product=product, name=new_part_name
                    )
                else:
                    part_obj = Part.objects.get(pk=part_id, product=product)

                new_wood_part = WoodPart(
                    product      = product,
                    resource     = resource,
                    part         = part_obj,
                    part_name    = part_obj.name,
                    width        = float(width),
                    breadth      = float(breadth),
                    height       = float(height),
                    length       = float(length),
                    pieces       = int(pieces),
                    width_unit   = width_unit,
                    breadth_unit = breadth_unit,
                    height_unit  = height_unit,
                    length_unit  = length_unit,
                    formula_expression = formula_expression,
                )

                if formula_expression:
                    # Validate against the ACTUAL entered dimensions —
                    # not dummy values — before saving. Uses the exact
                    # same code path the BOM/cost sheet will use later,
                    # so "valid here" really does mean "valid there".
                    new_wood_part.calculated_quantity

                new_wood_part.save()
                messages.success(
                    request,
                    f'Dimension entry "{part_obj.name}" added successfully.'
                )
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError:
                messages.error(
                    request,
                    'Please enter valid numbers for all dimensions.'
                )
            except FormulaError as e:
                messages.error(request, f'Formula error: {e}')

    context = {
        'page_title': f'Add Dimension — {product.product_code}',
        'product': product,
        'all_resources': all_resources,
        'unit_choices': unit_choices,
        'existing_parts': existing_parts,
        # resource.pk (as string, since JSON object keys are always
        # strings) -> material_type. Used by JS to auto-default the
        # unit dropdowns when a material is selected.
        'resource_material_types': {
            str(r.pk): r.material_type for r in all_resources
        },
        # Flat list for the type-to-filter combobox JS — avoids the
        # user having to scroll a huge native <select>.
        'resource_options': [
            {
                'id': r.pk,
                'name': r.resource_name,
                'category': r.category,
                'unit': r.unit,
            }
            for r in all_resources
        ],
    }
    return render(request, 'bom/woodpart_add.html', context)


@login_required
@admin_required
def woodpart_edit(request, pk):
    """
    Edits an existing Dimension entry.
    All dimension fields and units are editable.
    Resource can also be changed.
    """
    from .models import WoodPart
    from .models import Part 
    from apps.resources.models import Resource
    from apps.core.safe_eval import FormulaError

    wood_part = get_object_or_404(WoodPart, pk=pk)
    product = wood_part.product
    all_resources = Resource.objects.filter(active=True).order_by('category', 'resource_name')
    existing_parts = Part.objects.filter(product=product)

    unit_choices = [
        ('in',   'Inches'),
        ('ft',   'Feet'),
        ('sqft', 'Square Feet'),
        ('cft',  'Cubic Feet'),
        ('mm',   'Millimeters'),
        ('cm',   'Centimeters'),
        ('m',    'Meters'),
        ('nos',  'Numbers'),
    ]

    if request.method == 'POST':
        resource_id  = request.POST.get('resource')
        part_name    = request.POST.get('part_name', '').strip()
        width        = request.POST.get('width')
        breadth      = request.POST.get('breadth')
        height       = request.POST.get('height') or '0'
        length       = request.POST.get('length')
        pieces       = request.POST.get('pieces')
        width_unit   = request.POST.get('width_unit', 'in')
        breadth_unit = request.POST.get('breadth_unit', 'in')
        height_unit  = request.POST.get('height_unit', 'in')
        length_unit  = request.POST.get('length_unit', 'in')

        use_custom_formula = request.POST.get('use_custom_formula') == 'on'
        formula_expression = (
            request.POST.get('formula_expression', '').strip()
            if use_custom_formula else ''
        )

        if not all([resource_id, part_name, width, breadth, length, pieces]):
            messages.error(request, 'All fields except Height are required.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)
                part_obj, _ = Part.objects.get_or_create(product=product, name=part_name)

                wood_part.resource     = resource
                wood_part.part         = part_obj
                wood_part.part_name    = part_obj.name
                wood_part.width        = float(width)
                wood_part.breadth      = float(breadth)
                wood_part.height       = float(height)
                wood_part.length       = float(length)
                wood_part.pieces       = int(pieces)
                wood_part.width_unit   = width_unit
                wood_part.breadth_unit = breadth_unit
                wood_part.height_unit  = height_unit
                wood_part.length_unit  = length_unit
                wood_part.formula_expression = formula_expression

                if formula_expression:
                    # Validate against the ACTUAL entered dimensions —
                    # same code path used everywhere else — before
                    # this change is persisted.
                    wood_part.calculated_quantity

                wood_part.save()

                messages.success(
                    request,
                    f'Dimension entry "{part_name}" updated.'
                )
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError:
                messages.error(
                    request,
                    'Please enter valid numbers for all dimensions.'
                )
            except FormulaError as e:
                messages.error(request, f'Formula error: {e}')

    context = {
        'page_title': f'Edit Dimension — {product.product_code}',
        'product': product,
        'wood_part': wood_part,
        'all_resources': all_resources,
        'unit_choices': unit_choices,
        'existing_parts': existing_parts,
        'resource_material_types': {
            str(r.pk): r.material_type for r in all_resources
        },
        'resource_options': [
            {
                'id': r.pk,
                'name': r.resource_name,
                'category': r.category,
                'unit': r.unit,
            }
            for r in all_resources
        ],
    }
    return render(request, 'bom/woodpart_edit.html', context)


@login_required
@admin_required
def woodpart_remove(request, pk):
    """
    Removes a WoodPart. POST only for safety.
    """
    from .models import WoodPart

    wood_part = get_object_or_404(WoodPart, pk=pk)
    product_pk = wood_part.product.pk

    if request.method == 'POST':
        part_name = wood_part.part_name
        wood_part.delete()
        messages.success(request, f'Wood part "{part_name}" removed.')

    return redirect('bom:list', product_pk=product_pk)