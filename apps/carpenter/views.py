# apps/carpenter/views.py
#
# Carpenter area — the only part of the app the Carpenter role can reach.
# Nothing here may expose rates, costs, suppliers or cost sheets
# (CLAUDE.md Security rule 3).
#
# link_form is the one deliberate exception to "@login_required on every
# view": it is reached through a magic link (BOMSubmission.token) sent to
# a carpenter who may have no account. The token is the credential — it
# is unguessable, expires, and stops working once used or revoked. The
# form only stages data (BOMSubmission / SubmissionLine); an admin must
# approve before anything reaches the real BOM.

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.bom.models import BOMItem, Part, WoodPart
from apps.bom.services import LineError, clean_bom_line, clean_dimension_line
from apps.core.decorators import carpenter_required
from apps.products.models import Product
from apps.resources.models import Resource, DIMENSIONAL_UNIT_CHOICES

from .models import BOMSubmission, SubmissionLine


@login_required
@carpenter_required
def home(request):
    return render(request, 'carpenter/home.html', {
        'page_title': 'Carpenter',
    })


# ── Magic-link form ─────────────────────────────────────────────────

LABELS = {
    'en': {
        'title': 'Materials needed',
        'intro': 'Add every material this product needs, with the quantity. '
                 'Add the wood / ply parts with their measurements below.',
        'materials': 'Materials',
        'dimensions': 'Parts with measurements',
        'material': 'Material',
        'quantity': 'Quantity',
        'part_name': 'Part name',
        'width': 'Width (W)',
        'breadth': 'Breadth (B)',
        'height': 'Height (H)',
        'length': 'Length (L)',
        'pieces': 'Pieces',
        'optional': '(optional)',
        'add_material': 'Add material',
        'add_part': 'Add part',
        'add': 'Add',
        'remove': 'Remove',
        'edit': 'Edit',
        'size': 'Size (W × B × L)',
        'nothing_yet': 'Nothing added yet.',
        'pick_material': 'Pick a material from the list.',
        'enter_quantity': 'Enter a quantity greater than 0.',
        'enter_part': 'Enter the part name.',
        'enter_sizes': 'Enter width, breadth and length.',
        'enter_pieces': 'Pieces must be a whole number, 1 or more.',
        'not_added': 'You have typed something that is not added yet — press Add or clear it.',
        'part_search': 'e.g. Table top, Leg, Shelf…',
        'new_part': 'new part',
        'search': 'Type to search — e.g. teak, ply, hinge…',
        'no_match': 'No materials match.',
        'note': 'Note for the office',
        'submit': 'Send',
        'fix_errors': 'Please fix the problems below.',
        'need_one_line': 'Add at least one material or part.',
        'line': 'Line',
        'duplicate': 'This material is listed twice — combine the quantities into one line.',
        'thanks_title': 'Thank you!',
        'thanks_body': 'Your list has been sent. The office will check it.',
        'closed_title': 'This link can no longer be used',
        'closed_body': 'It has expired or has already been used. Ask the office for a new link.',
        'pick_title': 'Start from a similar product?',
        'pick_intro': 'If this product is like one below, copy its list and change only what is '
                      'different. Otherwise start a new product.',
        'pick_intro_fixed': 'If this product is like one below, copy its list and change only what is '
                            'different. Otherwise start with an empty list.',
        'new_product': 'New product',
        'empty_list': 'Start with an empty list',
        'copy': 'Copy & edit',
        'view': 'View list',
        'hide': 'Hide',
        'product_search': 'Search products…',
        'no_products': 'No products match.',
        'product_name': 'Product name',
        'product_name_hint': 'e.g. 3-Door Wardrobe',
        'enter_product_name': 'Enter the product name.',
        'copied_from': 'Copied from',
        'new_list': 'New list',
        'change': 'Change',
        'confirm_change': 'Go back? The list you have made below will be cleared.',
        'materials_count': 'materials',
        'parts_count': 'parts',
    },
    'ta': {
        'title': 'தேவையான பொருட்கள்',
        'intro': 'இந்தப் பொருளுக்குத் தேவையான அனைத்துப் பொருட்களையும் அளவுடன் சேர்க்கவும். '
                 'மரம் / ப்ளை பாகங்களை அவற்றின் அளவுகளுடன் கீழே சேர்க்கவும்.',
        'materials': 'பொருட்கள்',
        'dimensions': 'அளவுகளுடன் பாகங்கள்',
        'material': 'பொருள்',
        'quantity': 'அளவு',
        'part_name': 'பாகத்தின் பெயர்',
        'width': 'அகலம் (W)',
        'breadth': 'கனம் (B)',
        'height': 'உயரம் (H)',
        'length': 'நீளம் (L)',
        'pieces': 'எண்ணிக்கை',
        'optional': '(விருப்பம்)',
        'add_material': 'பொருள் சேர்க்க',
        'add_part': 'பாகம் சேர்க்க',
        'add': 'சேர்',
        'remove': 'நீக்கு',
        'edit': 'திருத்து',
        'size': 'அளவு (W × B × L)',
        'nothing_yet': 'இன்னும் எதுவும் சேர்க்கப்படவில்லை.',
        'pick_material': 'பட்டியலிலிருந்து ஒரு பொருளைத் தேர்ந்தெடுக்கவும்.',
        'enter_quantity': '0-ஐ விட அதிகமான அளவை உள்ளிடவும்.',
        'enter_part': 'பாகத்தின் பெயரை உள்ளிடவும்.',
        'enter_sizes': 'அகலம், கனம், நீளம் ஆகியவற்றை உள்ளிடவும்.',
        'enter_pieces': 'எண்ணிக்கை 1 அல்லது அதற்கு மேற்பட்ட முழு எண்ணாக இருக்க வேண்டும்.',
        'not_added': 'நீங்கள் தட்டச்சு செய்தது இன்னும் சேர்க்கப்படவில்லை — சேர் அழுத்தவும் அல்லது அழிக்கவும்.',
        'part_search': 'எ.கா. மேசை மேல், கால், அலமாரி…',
        'new_part': 'புதிய பாகம்',
        'search': 'தேடுக — தேக்கு, ப்ளை…',
        'no_match': 'பொருத்தமான பொருள் இல்லை.',
        'note': 'அலுவலகத்திற்கான குறிப்பு',
        'submit': 'அனுப்பு',
        'fix_errors': 'தயவுசெய்து கீழே உள்ள பிழைகளைச் சரிசெய்யவும்.',
        'need_one_line': 'குறைந்தது ஒரு பொருள் அல்லது பாகத்தைச் சேர்க்கவும்.',
        'line': 'வரி',
        'duplicate': 'இந்தப் பொருள் இரண்டு முறை உள்ளது — அளவுகளை ஒரே வரியில் சேர்க்கவும்.',
        'thanks_title': 'நன்றி!',
        'thanks_body': 'உங்கள் பட்டியல் அனுப்பப்பட்டது. அலுவலகம் சரிபார்க்கும்.',
        'closed_title': 'இந்த இணைப்பைப் பயன்படுத்த முடியாது',
        'closed_body': 'இது காலாவதியானது அல்லது ஏற்கனவே பயன்படுத்தப்பட்டது. அலுவலகத்திடம் புதிய இணைப்பைக் கேளுங்கள்.',
        'pick_title': 'ஒத்த பொருளிலிருந்து தொடங்கவா?',
        'pick_intro': 'இந்தப் பொருள் கீழே உள்ள ஒன்றைப் போல இருந்தால், அதன் பட்டியலை நகலெடுத்து '
                      'மாறுபட்டதை மட்டும் திருத்தவும். இல்லையெனில் புதிய பொருளைத் தொடங்கவும்.',
        'pick_intro_fixed': 'இந்தப் பொருள் கீழே உள்ள ஒன்றைப் போல இருந்தால், அதன் பட்டியலை நகலெடுத்து '
                            'மாறுபட்டதை மட்டும் திருத்தவும். இல்லையெனில் வெற்றுப் பட்டியலுடன் தொடங்கவும்.',
        'new_product': 'புதிய பொருள்',
        'empty_list': 'வெற்றுப் பட்டியலுடன் தொடங்கு',
        'copy': 'நகலெடுத்துத் திருத்து',
        'view': 'பட்டியலைப் பார்',
        'hide': 'மறை',
        'product_search': 'பொருட்களைத் தேடுக…',
        'no_products': 'பொருத்தமான பொருள் இல்லை.',
        'product_name': 'பொருளின் பெயர்',
        'product_name_hint': 'எ.கா. 3-கதவு அலமாரி',
        'enter_product_name': 'பொருளின் பெயரை உள்ளிடவும்.',
        'copied_from': 'நகல் எடுத்தது',
        'new_list': 'புதிய பட்டியல்',
        'change': 'மாற்று',
        'confirm_change': 'பின் செல்லவா? கீழே நீங்கள் செய்த பட்டியல் அழிக்கப்படும்.',
        'materials_count': 'பொருட்கள்',
        'parts_count': 'பாகங்கள்',
    },
}

_DIM_FIELDS = ['resource', 'part', 'width', 'width_unit', 'breadth', 'breadth_unit',
               'height', 'height_unit', 'length', 'length_unit', 'pieces']


def _resource_options():
    """
    Resource picker data for the public form. Deliberately an explicit
    whitelist of fields — never rate, override or supplier data
    (CLAUDE.md Security rule 3).
    """
    return [
        {
            'id': r.pk,
            'name': r.resource_name,
            'name_ta': r.name_ta,
            'aliases': r.aliases,
            'category': r.category,
            'unit': r.unit,
            'material_type': r.material_type,
        }
        for r in Resource.objects.filter(active=True).order_by('category', 'resource_name')
    ]


def _number(value):
    """Decimal → plain string for the form ('2.5', '100', not '2.5000'
    or '1E+2'); empty for None / zero."""
    if not value:
        return ''
    return format(value.normalize(), 'f')


def _product_library():
    """
    Existing products with their material and part lists, so a carpenter
    can copy a similar product instead of starting from nothing.
    Quantities and measurements only — never rates or costs (CLAUDE.md
    Security rule 3). Lines on inactive resources are left out because
    the form can't submit them.
    """
    products = {
        p.pk: {'id': p.pk, 'name': p.product_name, 'bom': [], 'dim': []}
        for p in Product.active_products().order_by('product_name')
    }
    bom_items = (
        BOMItem.objects.filter(product_id__in=products, resource__active=True)
        .order_by('resource__category', 'resource__resource_name')
        .values_list('product_id', 'resource_id', 'quantity')
    )
    for product_id, resource_id, quantity in bom_items:
        products[product_id]['bom'].append({'resource': resource_id, 'quantity': _number(quantity)})

    wood_parts = (
        WoodPart.objects.filter(product_id__in=products, resource__active=True)
        .order_by('id')
        .values('product_id', 'resource_id', 'part_name', 'width', 'width_unit',
                'breadth', 'breadth_unit', 'height', 'height_unit',
                'length', 'length_unit', 'pieces')
    )
    for wp in wood_parts:
        products[wp['product_id']]['dim'].append({
            'resource': wp['resource_id'],
            'part': wp['part_name'],
            'width': _number(wp['width']), 'width_unit': wp['width_unit'],
            'breadth': _number(wp['breadth']), 'breadth_unit': wp['breadth_unit'],
            'height': _number(wp['height']), 'height_unit': wp['height_unit'],
            'length': _number(wp['length']), 'length_unit': wp['length_unit'],
            'pieces': str(wp['pieces']),
        })

    return [p for p in products.values() if p['bom'] or p['dim']]


def _part_options():
    """Existing part names for the part picker — names only, nothing
    costed."""
    return [
        {'name': p.name, 'name_ta': p.name_ta, 'aliases': p.aliases}
        for p in Part.objects.order_by('name')
    ]


def _rows(post, prefix, fields):
    """Zips the parallel getlist() arrays of one repeatable section into
    a list of dicts, one per row."""
    columns = {f: post.getlist(f'{prefix}_{f}') for f in fields}
    count = max((len(v) for v in columns.values()), default=0)
    return [
        {f: (columns[f][i] if i < len(columns[f]) else '').strip() for f in fields}
        for i in range(count)
    ]


def _parse_submission(post, labels):
    """Returns (cleaned_lines, raw_bom_rows, raw_dim_rows, errors)."""
    bom_rows = [r for r in _rows(post, 'bom', ['resource', 'quantity']) if any(r.values())]
    dim_rows = [
        r for r in _rows(post, 'dim', _DIM_FIELDS)
        if any(r[f] for f in ('resource', 'part', 'width', 'breadth', 'length'))
    ]

    lines, errors = [], []
    seen_resources = set()

    for i, row in enumerate(bom_rows, start=1):
        try:
            line = clean_bom_line(row['resource'], row['quantity'])
            if line['resource'].pk in seen_resources:
                raise LineError(labels['duplicate'])
            seen_resources.add(line['resource'].pk)
            lines.append(line)
        except LineError as e:
            errors.append(f"{labels['materials']} — {labels['line']} {i}: {e}")

    for i, row in enumerate(dim_rows, start=1):
        try:
            lines.append(clean_dimension_line(
                row['resource'], row['part'], row['width'], row['breadth'],
                row['length'], row['pieces'], height=row['height'],
                width_unit=row['width_unit'], breadth_unit=row['breadth_unit'],
                height_unit=row['height_unit'], length_unit=row['length_unit'],
            ))
        except LineError as e:
            errors.append(f"{labels['dimensions']} — {labels['line']} {i}: {e}")

    if not lines and not errors:
        errors.append(labels['need_one_line'])

    return lines, bom_rows, dim_rows, errors


@never_cache
def link_form(request, token):
    submission = (
        BOMSubmission.objects.select_related('product')
        .filter(token=token)
        .first()
    )
    if submission is None or (submission.product and submission.product.is_deleted):
        raise Http404

    labels = LABELS.get(submission.language, LABELS['en'])
    product = submission.product
    base_context = {
        'page_title': labels['title'],
        'labels': labels,
        'lang': submission.language,
        'product': product,
        'heading': product.product_name if product else
                   (submission.new_product_name or labels['new_product']),
        'subheading': product.product_code if product else '',
        'carpenter_name': submission.carpenter_name,
    }

    if not submission.accepts_entries:
        just_sent = submission.status == BOMSubmission.STATUS_PENDING and \
            request.session.pop('carpenter_submitted', None) == submission.pk
        return render(request, 'carpenter/link_closed.html', {
            **base_context, 'thanks': just_sent,
        })

    errors, bom_rows, dim_rows, note = [], [], [], ''
    new_product_name, based_on = '', None

    if request.method == 'POST':
        note = request.POST.get('note', '').strip()[:2000]
        lines, bom_rows, dim_rows, errors = _parse_submission(request.POST, labels)

        based_on_id = request.POST.get('based_on', '')
        if based_on_id.isdigit():
            based_on = Product.active_products().filter(pk=based_on_id).first()
        if product is None:
            new_product_name = ' '.join(request.POST.get('new_product_name', '').split())[:255]
            if not new_product_name:
                errors.insert(0, labels['enter_product_name'])

        if not errors:
            with transaction.atomic():
                # Re-check under a row lock so a double-tap on Send can't
                # create two sets of lines for one link.
                locked = BOMSubmission.objects.select_for_update().get(pk=submission.pk)
                if not locked.accepts_entries:
                    return redirect('carpenter:link_form', token=token)

                SubmissionLine.objects.bulk_create([
                    SubmissionLine(
                        submission=locked,
                        line_type=line['type'],
                        resource=line['resource'],
                        quantity=line.get('quantity'),
                        part_name=line.get('part_name', ''),
                        width=line.get('width'),
                        breadth=line.get('breadth'),
                        height=line.get('height'),
                        length=line.get('length'),
                        width_unit=line.get('width_unit', 'in'),
                        breadth_unit=line.get('breadth_unit', 'in'),
                        height_unit=line.get('height_unit', 'in'),
                        length_unit=line.get('length_unit', 'in'),
                        pieces=line.get('pieces'),
                    )
                    for line in lines
                ])
                locked.note = note
                locked.new_product_name = new_product_name
                locked.based_on = based_on
                locked.status = BOMSubmission.STATUS_PENDING
                locked.submitted_at = timezone.now()
                locked.save(update_fields=['note', 'new_product_name', 'based_on',
                                           'status', 'submitted_at'])

            request.session['carpenter_submitted'] = submission.pk
            return redirect('carpenter:link_form', token=token)

    return render(request, 'carpenter/link_form.html', {
        **base_context,
        'errors': errors,
        'note': note,
        'resource_options': _resource_options(),
        'part_options': _part_options(),
        'product_library': _product_library(),
        'unit_choices': DIMENSIONAL_UNIT_CHOICES,
        'initial_rows': {'bom': bom_rows, 'dim': dim_rows},
        # After a failed submit, go straight back to the list being
        # edited rather than the product chooser.
        'initial_state': {
            'started': request.method == 'POST',
            'based_on': based_on.pk if based_on else None,
            'based_on_name': based_on.product_name if based_on else '',
        },
        'new_product_name': new_product_name,
    })
