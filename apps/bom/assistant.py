# apps/bom/assistant.py
#
# Conversational voice assistant for the admin BOM page. The browser does
# speech-to-text / text-to-speech (Web Speech API, English only); this
# module only turns the transcribed text into a chat-completions
# conversation with tools. Any OpenAI-compatible provider works (Gemini,
# Groq, ...) — see BOM_ASSISTANT_BASE_URL / BOM_ASSISTANT_MODEL.
#
# The assistant NEVER writes to the BOM. Its "stage_*" tools only add to
# a draft kept in the session; an admin has to press "Save to BOM"
# (views.assistant_commit), which re-validates every row and writes them
# through apps.bom.services.apply_lines — the same path carpenter
# submissions use.

import json
import logging
import time
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.core.search import search_by_name
from apps.resources.models import Resource, DIMENSIONAL_UNIT_CODES

from .models import BOMItem, WoodPart, Part
from .services import LineError, clean_bom_line, clean_dimension_line

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
TURN_TIME_BUDGET = 90          # seconds; Gunicorn's worker timeout is 120
MAX_HISTORY_MESSAGES = 80      # beyond this the admin is asked to start over
MAX_DRAFT_ROWS = 50
SEARCH_LIMIT = 8

SYSTEM_PROMPT = """\
You help an admin at a furniture workshop add rows to the Bill of Materials \
(BOM) of one product: {product_name} (code {product_code}).

The admin's words come from speech-to-text, so expect mis-heard words and \
numbers spelled out. They may also type Tamil names; search handles those. \
Always reply in English, in one or two short plain sentences (they are read \
aloud): no markdown, lists or symbols. Ask one question at a time. When you name \
a resource, use its English name.

Rows:
- Material row: resource + quantity (in the resource's unit). Use stage_material.
- Dimension row: resource, part name, width, breadth, length (optional height), \
a unit for each ({units}), and pieces. Use stage_dimension.

Rules:
1. Always call search_resources first and use the id it returns. Never invent an \
id. If several match, ask which one (name at most three). If none match, say so.
2. Call search_parts before naming a new part, to reuse existing names.
3. If a required value is missing, ask for it. Do not guess. If units are not \
given, suggest the usual ones (solid wood: width and breadth in inches, length \
in feet; ply or MDF sheets: feet) and say which you used.
4. To fix a staged row, call remove_staged_row, then stage the corrected row.
5. If a tool returns an "error", read it, then fix the arguments or ask the admin.
6. Staged rows are only a draft; the admin presses Save to BOM to write them. \
You cannot save, delete BOM rows, or see rates. For anything else, say you can \
only help add BOM rows.

Example 1. Admin: "eight hinges"
-> search_resources {{"query": "hinge"}} returns id 12 "Hinge" (unit nos)
-> stage_material {{"resource_id": 12, "quantity": 8}}
-> reply: "Added 8 Hinge."

Example 2. Admin: "teak leg 2 by 2 inch, 30 inch long, 4 pieces"
-> search_resources {{"query": "teak"}} returns id 5 "Teak Wood"
-> search_parts {{"query": "leg"}} returns "Leg"
-> stage_dimension {{"resource_id": 5, "part_name": "Leg", "width": 2, \
"width_unit": "in", "breadth": 2, "breadth_unit": "in", "length": 30, \
"length_unit": "in", "pieces": 4}}
-> reply: "Added 4 Teak Wood legs, 2 by 2 by 30 inches."
"""


def _function(name, description, properties=None, required=()):
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {'type': 'object', 'properties': properties or {}, 'required': list(required)},
        },
    }


TOOLS = [
    _function(
        'search_resources',
        'Search active resources (materials, hardware, labour) by English name, '
        'Tamil name or alias. Returns up to 8 matches with id, name, Tamil name, '
        'category, unit and material_type (solid_wood, sheet or other).',
        {'query': {'type': 'string', 'description': 'Name or part of a name, e.g. "teak" or "தேக்கு".'}},
        ['query'],
    ),
    _function(
        'search_parts',
        'Search existing part names (e.g. "Table Top", "Leg") so the same names are reused.',
        {'query': {'type': 'string'}},
        ['query'],
    ),
    _function('get_current_bom', "List what is already in this product's BOM (material rows and dimension rows)."),
    _function('get_draft', 'List the rows staged so far in this conversation, numbered from 1.'),
    _function(
        'stage_material',
        'Add a material row (resource + quantity) to the draft.',
        {
            'resource_id': {'type': 'integer'},
            'quantity': {'type': 'number', 'description': "In the resource's own unit."},
        },
        ['resource_id', 'quantity'],
    ),
    _function(
        'stage_dimension',
        'Add a dimension row (a measured part cut from a resource) to the draft.',
        {
            'resource_id': {'type': 'integer'},
            'part_name': {'type': 'string'},
            'width': {'type': 'number'},
            'width_unit': {'type': 'string', 'enum': DIMENSIONAL_UNIT_CODES},
            'breadth': {'type': 'number'},
            'breadth_unit': {'type': 'string', 'enum': DIMENSIONAL_UNIT_CODES},
            'length': {'type': 'number'},
            'length_unit': {'type': 'string', 'enum': DIMENSIONAL_UNIT_CODES},
            'height': {'type': 'number', 'description': 'Optional.'},
            'height_unit': {'type': 'string', 'enum': DIMENSIONAL_UNIT_CODES},
            'pieces': {'type': 'integer', 'minimum': 1},
        },
        ['resource_id', 'part_name', 'width', 'width_unit', 'breadth',
         'breadth_unit', 'length', 'length_unit', 'pieces'],
    ),
    _function(
        'remove_staged_row',
        'Remove one row from the draft by its number (as listed by get_draft).',
        {'row_number': {'type': 'integer', 'minimum': 1}},
        ['row_number'],
    ),
]

_SCHEMAS = {t['function']['name']: t['function']['parameters'] for t in TOOLS}


class AssistantError(Exception):
    """Something went wrong talking to the model. Message is user-facing."""


def is_configured():
    return bool(getattr(settings, 'BOM_ASSISTANT_API_KEY', ''))


# Bumped when the stored message format changes; older sessions keep
# their draft but start a fresh conversation.
STATE_FORMAT = 'openai-1'


def new_state():
    return {'messages': [], 'draft': [], 'format': STATE_FORMAT}


def load_state(stored):
    if not stored:
        return new_state()
    if stored.get('format') != STATE_FORMAT:
        return {**new_state(), 'draft': stored.get('draft', [])}
    return stored


# ── Draft rows ──────────────────────────────────────────────────────
# Stored in the session as plain JSON (strings for numbers), and turned
# back into cleaned lines by draft_to_lines() at commit time.

def _draft_row(line):
    resource = line['resource']
    row = {
        'type': line['type'],
        'resource_id': resource.pk,
        'resource_name': resource.resource_name,
        'unit': resource.unit,
    }
    if line['type'] == 'bom':
        row['quantity'] = str(line['quantity'])
    else:
        for field in ('part_name', 'width_unit', 'breadth_unit', 'height_unit', 'length_unit'):
            row[field] = line[field]
        for field in ('width', 'breadth', 'height', 'length'):
            row[field] = str(line[field])
        row['pieces'] = line['pieces']
    return row


def draft_to_lines(draft):
    """Re-validates every draft row. Raises LineError naming the bad row."""
    lines = []
    for i, row in enumerate(draft, start=1):
        try:
            if row['type'] == 'bom':
                lines.append(clean_bom_line(row['resource_id'], row['quantity']))
            else:
                lines.append(clean_dimension_line(
                    row['resource_id'], row['part_name'], row['width'], row['breadth'],
                    row['length'], row['pieces'], height=row['height'],
                    width_unit=row['width_unit'], breadth_unit=row['breadth_unit'],
                    height_unit=row['height_unit'], length_unit=row['length_unit'],
                ))
        except LineError as e:
            raise LineError(f'Row {i} ({row.get("resource_name", "?")}): {e}')
    return lines


def describe_draft_row(row):
    if row['type'] == 'bom':
        return f"{row['resource_name']}: {row['quantity']} {row['unit']}"
    dims = f"{row['width']}{row['width_unit']} x {row['breadth']}{row['breadth_unit']} x {row['length']}{row['length_unit']}"
    if row['height'] not in ('0', '0.0', '0.0000', ''):
        dims += f" x {row['height']}{row['height_unit']}"
    return f"{row['part_name']} ({row['resource_name']}): {dims}, {row['pieces']} pcs"


# ── Tool implementations ────────────────────────────────────────────

def _resource_result(r):
    return {
        'id': r.pk,
        'name': r.resource_name,
        'name_ta': r.name_ta,
        'category': r.category,
        'unit': r.unit,
        'material_type': r.material_type,
    }


def _search_resources(query):
    active = Resource.objects.filter(active=True)
    matches = list(search_by_name(active, query, 'resource_name')[:SEARCH_LIMIT]) if query.strip() else []
    if not matches:
        # Speech often adds extra words ("teak wood plank"): fall back to
        # per-word matching, best-covered resources first.
        hits = {}
        for word in {w for w in query.split() if len(w) >= 3}:
            for r in search_by_name(active, word, 'resource_name')[:50]:
                hits.setdefault(r.pk, [r, 0])[1] += 1
        matches = [r for r, _ in sorted(hits.values(), key=lambda h: -h[1])][:SEARCH_LIMIT]
    return {'matches': [_resource_result(r) for r in matches]}


def _search_parts(query):
    parts = search_by_name(Part.objects.all(), query, 'name')[:SEARCH_LIMIT]
    return {'parts': [{'name': p.name, 'name_ta': p.name_ta} for p in parts]}


def _current_bom(product):
    items = BOMItem.objects.filter(product=product).select_related('resource')
    parts = WoodPart.objects.filter(product=product).select_related('resource')
    return {
        'materials': [
            {'resource': i.resource.resource_name, 'quantity': str(i.quantity.normalize()), 'unit': i.resource.unit}
            for i in items
        ],
        'dimensions': [
            {
                'part': p.part_name, 'resource': p.resource.resource_name,
                'size': f'{p.width.normalize()}{p.width_unit} x {p.breadth.normalize()}{p.breadth_unit} '
                        f'x {p.length.normalize()}{p.length_unit}',
                'pieces': p.pieces,
            }
            for p in parts
        ],
    }


def _draft_listing(draft):
    return {'draft': [f'{i}. {describe_draft_row(r)}' for i, r in enumerate(draft, start=1)]}


def execute_tool(name, args, product, state):
    """Runs one tool call. Returns (result_dict, is_error)."""
    draft = state['draft']
    try:
        if name == 'search_resources':
            return _search_resources(str(args.get('query', ''))), False
        if name == 'search_parts':
            return _search_parts(str(args.get('query', ''))), False
        if name == 'get_current_bom':
            return _current_bom(product), False
        if name == 'get_draft':
            return _draft_listing(draft), False

        if name in ('stage_material', 'stage_dimension'):
            if len(draft) >= MAX_DRAFT_ROWS:
                return {'error': 'The draft is full. Ask the admin to save it first.'}, True
            if name == 'stage_material':
                line = clean_bom_line(args.get('resource_id'), args.get('quantity'))
                if any(r['type'] == 'bom' and r['resource_id'] == line['resource'].pk for r in draft):
                    return {'error': 'That material is already staged. Remove the staged row first to change it.'}, True
            else:
                line = clean_dimension_line(
                    args.get('resource_id'), args.get('part_name'), args.get('width'),
                    args.get('breadth'), args.get('length'), args.get('pieces'),
                    height=args.get('height'),
                    width_unit=args.get('width_unit', 'in'),
                    breadth_unit=args.get('breadth_unit', 'in'),
                    height_unit=args.get('height_unit', 'in'),
                    length_unit=args.get('length_unit', 'in'),
                )
            draft.append(_draft_row(line))
            return {'staged': describe_draft_row(draft[-1]), **_draft_listing(draft)}, False

        if name == 'remove_staged_row':
            index = int(args.get('row_number', 0)) - 1
            if not 0 <= index < len(draft):
                return {'error': f'There is no row {index + 1}. The draft has {len(draft)} rows.'}, True
            removed = draft.pop(index)
            return {'removed': describe_draft_row(removed), **_draft_listing(draft)}, False

        return {'error': f'Unknown tool {name}.'}, True
    except LineError as e:
        return {'error': str(e)}, True
    except (TypeError, ValueError) as e:
        return {'error': f'Invalid input: {e}'}, True


# ── Tool-call arguments ─────────────────────────────────────────────
# Free models are less reliable than the big ones: arguments arrive as a
# JSON string that may be broken, numbers may come as strings, required
# fields may be missing. Problems go back to the model as a tool error
# so it can correct itself — they never crash the turn.

def _coerce(value, prop):
    """Checks one argument against its schema. Returns (value, problem)."""
    kind = prop.get('type')
    if kind == 'string':
        if isinstance(value, (dict, list)):
            return None, 'must be text'
        value = str(value).strip()
        if 'enum' in prop:
            value = value.lower()
            if value not in prop['enum']:
                return None, f'must be one of {", ".join(prop["enum"])}'
        return value, None

    if isinstance(value, (bool, dict, list)):
        return None, 'must be a number'
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None, 'must be a number'
    if not number.is_finite():
        return None, 'must be a number'

    if kind == 'integer':
        if number != number.to_integral_value():
            return None, 'must be a whole number'
        value = int(number)
    elif isinstance(value, str):
        value = value.strip()    # keep the exact digits for Decimal fields
    if 'minimum' in prop and number < prop['minimum']:
        return None, f'must be at least {prop["minimum"]}'
    return value, None


def parse_arguments(name, raw):
    """
    Turns a tool call's raw `arguments` (a JSON string) into a clean dict.
    Returns (args, error) — exactly one of them is None.
    """
    schema = _SCHEMAS.get(name)
    if schema is None:
        return None, f'Unknown tool "{name}". Use one of: {", ".join(_SCHEMAS)}.'

    if isinstance(raw, dict):
        args = raw
    else:
        try:
            args = json.loads(raw) if raw and str(raw).strip() else {}
        except (TypeError, ValueError):
            return None, ('The arguments were not valid JSON. Call the tool again with a JSON '
                          'object, for example {"query": "teak"}.')
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None, 'The arguments must be a JSON object.'

    clean, problems = {}, []
    for field, prop in schema['properties'].items():
        value = args.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if field in schema['required']:
                problems.append(f'{field} is required')
            continue
        value, problem = _coerce(value, prop)
        if problem:
            problems.append(f'{field} {problem}')
        else:
            clean[field] = value
    if problems:
        return None, 'Invalid arguments: ' + '; '.join(problems) + '.'
    return clean, None


# ── Conversation loop ───────────────────────────────────────────────
# History is stored in OpenAI chat format: user / assistant (optionally
# with tool_calls) / tool messages. The system prompt is not stored; it
# is prepended on every request.

BUSY_MESSAGE = 'The assistant is busy, try again in a moment.'


def _client():
    from openai import OpenAI
    return OpenAI(
        api_key=settings.BOM_ASSISTANT_API_KEY,
        base_url=settings.BOM_ASSISTANT_BASE_URL,
        timeout=45.0,
        max_retries=1,
    )


def _create(client, product, messages):
    system = SYSTEM_PROMPT.format(
        product_name=product.product_name,
        product_code=product.product_code,
        units=', '.join(DIMENSIONAL_UNIT_CODES),
    )
    return client.chat.completions.create(
        model=settings.BOM_ASSISTANT_MODEL,
        messages=[{'role': 'system', 'content': system}, *messages],
        tools=TOOLS,
        tool_choice='auto',
        temperature=0.2,
        max_tokens=4096,
    )


def _assistant_message(message):
    """The model's message as plain JSON for the session. Tool calls are
    kept as returned (including provider extras such as Gemini's thought
    signatures, which have to be echoed back unchanged)."""
    stored = {'role': 'assistant', 'content': (message.content or '').strip()}
    tool_calls = [tc.model_dump(exclude_none=True) for tc in (message.tool_calls or [])]
    for i, call in enumerate(tool_calls):
        if not call.get('id'):
            call['id'] = f'call_{i}'       # some providers omit ids
        call.setdefault('type', 'function')
    if tool_calls:
        stored['tool_calls'] = tool_calls
    return stored


def run_turn(product, state, user_text):
    """
    Sends one admin utterance through the tool loop. Mutates `state`
    (messages + draft) in place and returns the reply text to show and speak.
    History is append-only — earlier turns are never edited.
    """
    import openai

    if len(state['messages']) >= MAX_HISTORY_MESSAGES:
        raise AssistantError('This conversation is getting long. Save your draft and press Start over.')

    messages = state['messages']
    turn_start = len(messages)
    messages.append({'role': 'user', 'content': user_text})

    started = time.monotonic()
    reply = ''

    try:
        client = _client()
        for _ in range(MAX_TOOL_ROUNDS):
            response = _create(client, product, messages)
            if not response.choices:
                raise AssistantError('The AI service sent an empty answer. Please try again.')
            choice = response.choices[0]

            if choice.finish_reason == 'content_filter':
                raise AssistantError("Sorry, I can't help with that. I can only add BOM rows.")

            stored = _assistant_message(choice.message)
            messages.append(stored)
            reply = stored['content']

            # Decide by the presence of tool calls, not finish_reason:
            # some providers report "stop" alongside tool calls.
            if not stored.get('tool_calls'):
                break

            for call in stored['tool_calls']:
                function = call.get('function') or {}
                name = function.get('name', '')
                args, error = parse_arguments(name, function.get('arguments'))
                if error:
                    result = {'error': error}
                else:
                    result, _ = execute_tool(name, args, product, state)
                messages.append({
                    'role': 'tool',
                    'tool_call_id': call['id'],
                    'content': json.dumps(result, ensure_ascii=False),
                })

            if time.monotonic() - started > TURN_TIME_BUDGET:
                break

    except AssistantError:
        _rollback(messages, turn_start)
        raise
    except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError):
        # 429, network trouble / timeouts (APITimeoutError is a subclass
        # of APIConnectionError), and 5xx "overloaded" answers.
        logger.warning('BOM assistant: provider busy or unreachable', exc_info=True)
        _rollback(messages, turn_start)
        raise AssistantError(BUSY_MESSAGE)
    except openai.APIStatusError as e:
        logger.error('BOM assistant: provider error %s: %s', e.status_code, e.message)
        _rollback(messages, turn_start)
        raise AssistantError('The AI service returned an error. Please try again.')
    except Exception:
        # Odd responses from less reliable models must not become a 500.
        logger.exception('BOM assistant: unexpected error')
        _rollback(messages, turn_start)
        raise AssistantError('Something went wrong with the assistant. Please try again.')

    # A turn must end on an assistant message without tool calls: if we
    # stopped mid-loop (tool budget / time budget), the model never
    # answered the last results. Roll back to keep the history valid.
    last = messages[-1] if messages else {}
    if last.get('role') != 'assistant' or last.get('tool_calls'):
        _rollback(messages, turn_start)
        raise AssistantError('Sorry, that took too long. Could you say it again more simply?')

    if not reply:
        reply = 'Okay.'
        last['content'] = reply     # keep the stored history free of empty messages
    return reply


def _rollback(messages, turn_start):
    """Drops everything this turn added, so the stored history stays a
    valid, append-only conversation. Draft changes made by tools in this
    turn are kept — the admin can see and remove them on screen."""
    del messages[turn_start:]
