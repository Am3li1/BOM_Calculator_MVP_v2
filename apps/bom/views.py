from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.products.models import Product
from .models import BOMItem


@login_required
def bom_list(request, product_pk):
    from .models import WoodPart

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    bom_items  = BOMItem.objects.filter(
        product=product
    ).select_related('resource')

    wood_parts = WoodPart.objects.filter(
        product=product
    ).select_related('resource')

    # Grand total is Standard BOM only.
    # Dimensions are measurement records — their cost is already
    # represented in the Standard BOM and must not be added again.
    total_bom_cost = sum(item.cost for item in bom_items)
    grand_total    = total_bom_cost

    context = {
        'page_title': f'BOM — {product.product_code}',
        'product': product,
        'bom_items': bom_items,
        'wood_parts': wood_parts,
        'total_bom_cost': total_bom_cost,
        'grand_total': grand_total,
    }
    return render(request, 'bom/list.html', context)


@login_required
def bom_add(request, product_pk):
    from apps.resources.models import Resource

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    existing_resource_ids = BOMItem.objects.filter(
        product=product
    ).values_list('resource_id', flat=True)

    available_resources = Resource.objects.filter(
        active=True
    ).exclude(id__in=existing_resource_ids)

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
    }
    return render(request, 'bom/bom_add.html', context)


@login_required
def bom_remove(request, pk):
    bom_item = get_object_or_404(BOMItem, pk=pk)
    product_pk = bom_item.product.pk

    if request.method == 'POST':
        resource_name = bom_item.resource.resource_name
        bom_item.delete()
        messages.success(request, f'"{resource_name}" removed from BOM.')

    return redirect('bom:list', product_pk=product_pk)


@login_required
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
def woodpart_add(request, product_pk):
    """
    Adds a Dimension entry to a product.
    All active resources are available (not just Wood/Ply/MDF).
    """
    from apps.resources.models import Resource
    from apps.core.models import SystemConfig

    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)
    all_resources = Resource.objects.filter(active=True).order_by('category', 'resource_name')
    config = SystemConfig.get_config()

    # Unit choices passed to template so we don't hardcode them there
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
        from .models import WoodPart

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

        if not all([resource_id, part_name, width, breadth, length, pieces]):
            messages.error(request, 'All fields except Height are required.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)

                WoodPart.objects.create(
                    product      = product,
                    resource     = resource,
                    part_name    = part_name,
                    width        = float(width),
                    breadth      = float(breadth),
                    height       = float(height),
                    length       = float(length),
                    pieces       = int(pieces),
                    width_unit   = width_unit,
                    breadth_unit = breadth_unit,
                    height_unit  = height_unit,
                    length_unit  = length_unit,
                )
                messages.success(
                    request,
                    f'Dimension entry "{part_name}" added successfully.'
                )
                return redirect('bom:list', product_pk=product.pk)

            except Resource.DoesNotExist:
                messages.error(request, 'Invalid resource selected.')
            except ValueError:
                messages.error(
                    request,
                    'Please enter valid numbers for all dimensions.'
                )

    context = {
        'page_title': f'Add Dimension — {product.product_code}',
        'product': product,
        'all_resources': all_resources,
        'unit_choices': unit_choices,
        'divisor': config.wood_divisor,
    }
    return render(request, 'bom/woodpart_add.html', context)


@login_required
def woodpart_edit(request, pk):
    """
    Edits an existing Dimension entry.
    All dimension fields and units are editable.
    Resource can also be changed.
    """
    from .models import WoodPart
    from apps.resources.models import Resource
    from apps.core.models import SystemConfig

    wood_part = get_object_or_404(WoodPart, pk=pk)
    product = wood_part.product
    all_resources = Resource.objects.filter(active=True).order_by('category', 'resource_name')
    config = SystemConfig.get_config()

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

        if not all([resource_id, part_name, width, breadth, length, pieces]):
            messages.error(request, 'All fields except Height are required.')
        else:
            try:
                resource = Resource.objects.get(pk=resource_id, active=True)

                wood_part.resource     = resource
                wood_part.part_name    = part_name
                wood_part.width        = float(width)
                wood_part.breadth      = float(breadth)
                wood_part.height       = float(height)
                wood_part.length       = float(length)
                wood_part.pieces       = int(pieces)
                wood_part.width_unit   = width_unit
                wood_part.breadth_unit = breadth_unit
                wood_part.height_unit  = height_unit
                wood_part.length_unit  = length_unit
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

    context = {
        'page_title': f'Edit Dimension — {product.product_code}',
        'product': product,
        'wood_part': wood_part,
        'all_resources': all_resources,
        'unit_choices': unit_choices,
        'divisor': config.wood_divisor,
    }
    return render(request, 'bom/woodpart_edit.html', context)


@login_required
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