from decimal import Decimal

from django.test import TestCase

from apps.products.models import Product
from apps.resources.models import Resource
from apps.bom.models import WoodPart


class WoodPartCalculatedQuantityTests(TestCase):
    """
    Regression tests for the CFT (solid_wood) / SFT (sheet) formula
    split introduced when material_type was added to Resource.
    Locks in the exact numbers verified manually during development —
    if any of these change, the formula has regressed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-01', product_name='Test Product'
        )
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        cls.ply = Resource.objects.create(
            resource_name='Plywood 6mm', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('80'),
        )
        cls.other = Resource.objects.create(
            resource_name='Fevicol', category='Miscellaneous',
            material_type='other', unit='kg', rate=Decimal('300'),
        )

    def test_solid_wood_cft_formula(self):
        # (2in * 2in * 8ft * 4pcs) / 144 = 0.888888...
        wp = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg',
            width=2, width_unit='in',
            breadth=2, breadth_unit='in',
            length=8, length_unit='ft',
            pieces=4,
        )
        expected = (Decimal('2') * Decimal('2') * Decimal('8') * Decimal('4')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )

    def test_solid_wood_unit_conversion_is_equivalent(self):
        # Same physical dimensions expressed in mm/cm must match the
        # inches/feet version exactly — proves conversion isn't a no-op.
        wp_in = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg A',
            width=2, width_unit='in', breadth=2, breadth_unit='in',
            length=8, length_unit='ft', pieces=4,
        )
        wp_mm = WoodPart(
            product=self.product, resource=self.teak, part_name='Leg B',
            width=50.8, width_unit='mm',    # 50.8mm = 2in
            breadth=5.08, breadth_unit='cm', # 5.08cm = 2in
            length=8, length_unit='ft', pieces=4,
        )
        self.assertAlmostEqual(
            float(wp_in.calculated_quantity),
            float(wp_mm.calculated_quantity),
            places=6,
        )

    def test_solid_wood_length_in_inches_matches_feet(self):
        # Solid wood now defaults Length to inches on the forms — 96in
        # must give exactly the same CFT as 8ft.
        kwargs = dict(
            product=self.product, resource=self.teak, part_name='Leg',
            width=2, width_unit='in', breadth=2, breadth_unit='in', pieces=4,
        )
        wp_ft = WoodPart(length=8, length_unit='ft', **kwargs)
        wp_in = WoodPart(length=96, length_unit='in', **kwargs)
        self.assertAlmostEqual(
            float(wp_ft.calculated_quantity),
            float(wp_in.calculated_quantity),
            places=6,
        )

    def test_full_formula_presets_match_builtin(self):
        # The "Plywood" / "Wood" one-click formulas on the dimension
        # form must give the same result as the built-in formulas.
        wood_kwargs = dict(
            product=self.product, resource=self.teak, part_name='Leg',
            width=2, width_unit='in', breadth=3, breadth_unit='in',
            length=90, length_unit='in', pieces=4,
        )
        builtin = WoodPart(**wood_kwargs).calculated_quantity
        preset = WoodPart(
            formula_expression='width_in * breadth_in * length_ft * pieces / 144',
            **wood_kwargs,
        ).calculated_quantity
        self.assertAlmostEqual(float(builtin), float(preset), places=6)

        ply_kwargs = dict(
            product=self.product, resource=self.ply, part_name='Panel',
            width=2, width_unit='ft', breadth=0, breadth_unit='ft',
            length=30, length_unit='in', pieces=3,
        )
        builtin = WoodPart(**ply_kwargs).calculated_quantity
        preset = WoodPart(
            formula_expression='width_ft * length_ft * pieces', **ply_kwargs,
        ).calculated_quantity
        self.assertAlmostEqual(float(builtin), float(preset), places=6)

    def test_sqft_resource_is_always_sheet(self):
        # Two-dimensional materials (priced per sq ft) like Teak Ost
        # must use the plywood formula even if saved as solid_wood.
        ost = Resource.objects.create(
            resource_name='Teak Ost', category='Wood and Plywood',
            material_type='solid_wood', unit='sqft', rate=Decimal('500'),
        )
        ost.refresh_from_db()
        self.assertEqual(ost.material_type, 'sheet')
        wp = WoodPart(
            product=self.product, resource=ost, part_name='Ost',
            width=6, width_unit='in', breadth=0, breadth_unit='in',
            length=2, length_unit='in', pieces=1,
        )
        # 6in × 2in = 12 sq in = 1/12 sq ft
        self.assertAlmostEqual(float(wp.calculated_quantity), 1 / 12, places=6)

    def test_sqft_rule_leaves_existing_resources_alone(self):
        r = Resource.objects.create(
            resource_name='Glass 4mm', category='Glass',
            material_type='other', unit='kg', rate=Decimal('50'),
        )
        Resource.objects.filter(pk=r.pk).update(unit='sqft')
        r.refresh_from_db()
        r.rate = Decimal('60')
        r.save()
        r.refresh_from_db()
        self.assertEqual(r.material_type, 'other')

    def test_sheet_sft_formula_uses_width_times_length(self):
        # 1.25ft * 1.25ft * 4pcs = 6.25. No divisor for sheet goods.
        wp = WoodPart(
            product=self.product, resource=self.ply, part_name='Panel',
            width=1.25, width_unit='ft',
            breadth=99, breadth_unit='ft',   # deliberately absurd — must be ignored
            length=1.25, length_unit='ft',
            pieces=4,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 6.25, places=6)

    def test_sheet_ignores_breadth(self):
        # Sheet goods are two-dimensional (Width x Length) — Breadth must
        # NOT change the result.
        base_kwargs = dict(
            product=self.product, resource=self.ply, part_name='Panel',
            width=4, width_unit='ft', length=8, length_unit='ft', pieces=1,
        )
        wp_a = WoodPart(breadth=0, breadth_unit='ft', **base_kwargs)
        wp_b = WoodPart(breadth=500, breadth_unit='ft', **base_kwargs)
        self.assertEqual(wp_a.calculated_quantity, wp_b.calculated_quantity)
        self.assertAlmostEqual(float(wp_a.calculated_quantity), 32.0, places=6)

    def test_other_material_type_uses_legacy_unit_naive_formula(self):
        # Unclassified resources keep the old raw-number/divisor formula
        # (no unit conversion) — deliberate, so reclassifying nothing
        # doesn't silently change existing costs.
        wp = WoodPart(
            product=self.product, resource=self.other, part_name='Misc',
            width=10, breadth=10, length=10, height=0, pieces=1,
            formula_type='standard',
        )
        expected = (Decimal('10') * Decimal('10') * Decimal('1') * Decimal('10') * Decimal('1')) / Decimal('144')
        self.assertAlmostEqual(
            float(wp.calculated_quantity), float(expected), places=6
        )


class WoodPartFormulaPrecedenceTests(TestCase):
    """
    Regression tests for WoodPart.formula_expression, the only
    custom-formula tier that exists (resource-level formula_expression
    was removed — see CLAUDE.md / migration 0008 in the resources app).
    Precedence is: WoodPart.formula_expression, if set, else the
    built-in material_type formula.
    """

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(
            product_code='TEST-WP', product_name='WoodPart Formula Product'
        )
        cls.plain_sheet = Resource.objects.create(
            resource_name='Plain Sheet', category='Carpentry Materials',
            material_type='sheet', unit='sqft', rate=Decimal('60'),
        )

    def test_woodpart_formula_overrides_material_type_default(self):
        # material_type='sheet' default (W x B) would ignore Length.
        # The custom formula uses Length instead, proving the override
        # takes priority: 4 * 8 * 1 / 4 = 8
        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=4, width_unit='ft', breadth=999, breadth_unit='ft',
            length=8, length_unit='ft', pieces=1,
            formula_expression='width_ft * length_ft * pieces / 4',
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 8.0, places=6)
        self.assertEqual(wp.formula_source, 'woodpart_custom')

    def test_blank_woodpart_formula_falls_back_to_material_type_default(self):
        # No WoodPart-level formula set -> falls straight through to
        # the built-in sheet SFT formula (W x L, Breadth ignored).
        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=4, width_unit='ft', breadth=999, breadth_unit='ft',
            length=8, length_unit='ft', pieces=1,
        )
        self.assertAlmostEqual(float(wp.calculated_quantity), 32.0, places=6)
        self.assertEqual(wp.formula_source, 'material_type_default')

    def test_bad_woodpart_formula_raises_loudly(self):
        from apps.core.safe_eval import FormulaError

        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * nonsense_variable',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity

    def test_no_divisor_variable_available(self):
        # 'divisor' was removed as a formula variable entirely —
        # referencing it must raise, not silently resolve to 144.
        from apps.core.safe_eval import FormulaError

        wp = WoodPart(
            product=self.product, resource=self.plain_sheet,
            part_name='Panel',
            width=1, width_unit='ft', breadth=1, breadth_unit='ft',
            length=1, length_unit='ft', pieces=1,
            formula_expression='width_ft * breadth_ft * pieces / divisor',
        )
        with self.assertRaises(FormulaError):
            wp.calculated_quantity


# ════════════════════════════════════════════════════════════════════
# Voice assistant (apps/bom/assistant.py) — the OpenAI-compatible
# client is always mocked; these tests never call a real provider.
# ════════════════════════════════════════════════════════════════════

import json
from unittest import mock

import openai
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from openai.types.chat import ChatCompletion

from apps.bom import assistant
from apps.bom.models import BOMItem


def _completion(message, finish_reason='stop'):
    return ChatCompletion.model_validate({
        'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 0, 'model': 'gemini-2.5-flash',
        'choices': [{'index': 0, 'finish_reason': finish_reason, 'message': {'role': 'assistant', **message}}],
    })


def _tool_call(name, args, call_id='call_1', raw_arguments=None):
    return _completion({
        'content': None,
        'tool_calls': [{
            'id': call_id, 'type': 'function',
            'function': {'name': name, 'arguments': raw_arguments if raw_arguments is not None else json.dumps(args)},
            # Gemini's thought signature — must survive the round trip.
            'extra_content': {'google': {'thought_signature': 'sig'}},
        }],
    }, finish_reason='tool_calls')


def _text(text):
    return _completion({'content': text})


def _fake_client(*responses):
    client = mock.Mock()
    client.chat.completions.create.side_effect = list(responses)
    return client


def _rate_limit_error():
    response = mock.Mock(status_code=429, headers={}, request=mock.Mock())
    return openai.RateLimitError('Resource has been exhausted', response=response, body=None)


@override_settings(BOM_ASSISTANT_API_KEY='test-key', BOM_ASSISTANT_MODEL='gemini-2.5-flash')
class AssistantTurnTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(product_code='TABLE-01', product_name='Coffee Table')
        cls.teak = Resource.objects.create(
            resource_name='Teak Wood', name_ta='தேக்கு', category='Carpentry Materials',
            material_type='solid_wood', unit='cft', rate=Decimal('1000'),
        )
        cls.hinge = Resource.objects.create(
            resource_name='Hinge', category='Hardware', unit='nos', rate=Decimal('50'),
        )

    def test_tool_loop_stages_a_row_and_returns_reply(self):
        client = _fake_client(
            _tool_call('search_resources', {'query': 'hinges'}, 'call_1'),
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 8}, 'call_2'),
            _text('Added 8 hinges.'),
        )
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=client):
            reply = assistant.run_turn(self.product, state, 'eight hinges')

        self.assertEqual(reply, 'Added 8 hinges.')
        self.assertEqual(state['draft'][0]['resource_id'], self.hinge.pk)
        self.assertEqual(state['draft'][0]['quantity'], '8')
        # user, assistant(tool call), tool, assistant(tool call), tool, assistant(text)
        self.assertEqual([m['role'] for m in state['messages']],
                         ['user', 'assistant', 'tool', 'assistant', 'tool', 'assistant'])
        self.assertEqual(state['messages'][2]['tool_call_id'], 'call_1')
        # Provider extras on tool calls are passed back unchanged.
        self.assertEqual(state['messages'][1]['tool_calls'][0]['extra_content'],
                         {'google': {'thought_signature': 'sig'}})
        # The assistant never writes to the BOM itself.
        self.assertFalse(BOMItem.objects.exists())

        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'gemini-2.5-flash')
        self.assertEqual(kwargs['messages'][0]['role'], 'system')
        self.assertEqual(kwargs['tools'][0]['type'], 'function')
        # Search results reach the model without rates.
        self.assertNotIn('rate', state['messages'][2]['content'])

    def test_tool_calls_with_stop_finish_reason_still_run(self):
        # Some providers report "stop" even when they return tool calls.
        call = _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 2})
        call.choices[0].finish_reason = 'stop'
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(call, _text('Done.'))):
            assistant.run_turn(self.product, state, 'two hinges')
        self.assertEqual(len(state['draft']), 1)

    def test_malformed_tool_arguments_go_back_to_the_model(self):
        client = _fake_client(
            _tool_call('stage_material', None, 'call_1', raw_arguments='{"resource_id": 5, "quantity": '),
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 'eight'}, 'call_2'),
            _tool_call('stage_material', {'quantity': 3}, 'call_3'),
            _tool_call('stage_material', ['not', 'an', 'object'], 'call_4'),
            _tool_call('drop_table', {}, 'call_5'),
            _text('Which material did you mean?'),
        )
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=client), \
                mock.patch.object(assistant, 'MAX_TOOL_ROUNDS', 10):
            reply = assistant.run_turn(self.product, state, 'eight hinges')

        self.assertEqual(reply, 'Which material did you mean?')
        self.assertEqual(state['draft'], [])
        errors = [json.loads(m['content'])['error'] for m in state['messages'] if m['role'] == 'tool']
        self.assertEqual(len(errors), 5)
        self.assertIn('not valid JSON', errors[0])
        self.assertIn('quantity must be a number', errors[1])
        self.assertIn('resource_id is required', errors[2])
        self.assertIn('must be a JSON object', errors[3])
        self.assertIn('Unknown tool', errors[4])

    def test_string_numbers_are_accepted(self):
        args, error = assistant.parse_arguments(
            'stage_dimension',
            json.dumps({'resource_id': str(self.teak.pk), 'part_name': 'Leg', 'width': '2',
                        'width_unit': 'IN', 'breadth': 2, 'breadth_unit': 'in', 'length': '2.5',
                        'length_unit': 'ft', 'pieces': '4.0'}),
        )
        self.assertIsNone(error)
        self.assertEqual(args['resource_id'], self.teak.pk)
        self.assertEqual(args['pieces'], 4)
        self.assertEqual(args['width_unit'], 'in')

        _, error = assistant.parse_arguments('remove_staged_row', '{"row_number": 0}')
        self.assertIn('at least 1', error)
        _, error = assistant.parse_arguments('stage_dimension', json.dumps({
            'resource_id': self.teak.pk, 'part_name': 'Leg', 'width': 2, 'width_unit': 'yards',
            'breadth': 2, 'breadth_unit': 'in', 'length': 2, 'length_unit': 'ft', 'pieces': 1,
        }))
        self.assertIn('width_unit must be one of', error)

    def test_search_falls_back_to_individual_words(self):
        # Speech adds extra words; the whole phrase matches nothing, so
        # per-word matching has to find "Hinge".
        result, is_error = assistant.execute_tool(
            'search_resources', {'query': 'steel hinge pieces'}, self.product, assistant.new_state()
        )
        self.assertFalse(is_error)
        self.assertEqual(result['matches'][0]['id'], self.hinge.pk)
        self.assertNotIn('rate', result['matches'][0])

    def test_search_matches_tamil_name(self):
        result, _ = assistant.execute_tool(
            'search_resources', {'query': 'தேக்கு'}, self.product, assistant.new_state()
        )
        self.assertEqual(result['matches'][0]['id'], self.teak.pk)

    def test_invalid_stage_is_reported_to_the_model(self):
        state = assistant.new_state()
        result, is_error = assistant.execute_tool(
            'stage_material', {'resource_id': 99999, 'quantity': 2}, self.product, state
        )
        self.assertTrue(is_error)
        self.assertEqual(state['draft'], [])

    def test_same_material_cannot_be_staged_twice(self):
        state = assistant.new_state()
        args = {'resource_id': self.hinge.pk, 'quantity': 2}
        assistant.execute_tool('stage_material', args, self.product, state)
        _, is_error = assistant.execute_tool('stage_material', args, self.product, state)
        self.assertTrue(is_error)
        self.assertEqual(len(state['draft']), 1)

    def test_stage_dimension_and_remove(self):
        state = assistant.new_state()
        _, is_error = assistant.execute_tool('stage_dimension', {
            'resource_id': self.teak.pk, 'part_name': 'Leg', 'width': 2, 'width_unit': 'in',
            'breadth': 2, 'breadth_unit': 'in', 'length': 2.5, 'length_unit': 'ft', 'pieces': 4,
        }, self.product, state)
        self.assertFalse(is_error)
        self.assertEqual(state['draft'][0]['part_name'], 'Leg')

        _, is_error = assistant.execute_tool('remove_staged_row', {'row_number': 1}, self.product, state)
        self.assertFalse(is_error)
        self.assertEqual(state['draft'], [])

    def test_content_filter_rolls_back_the_turn(self):
        blocked = _completion({'content': None}, finish_reason='content_filter')
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(blocked)):
            with self.assertRaises(assistant.AssistantError):
                assistant.run_turn(self.product, state, 'something odd')
        self.assertEqual(state['messages'], [])

    def test_rate_limit_gives_busy_message_and_keeps_earlier_turns(self):
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(_text('Hi.'))):
            assistant.run_turn(self.product, state, 'hello')
        before = list(state['messages'])

        with mock.patch.object(assistant, '_client', return_value=_fake_client(_rate_limit_error())):
            with self.assertRaisesMessage(assistant.AssistantError, assistant.BUSY_MESSAGE):
                assistant.run_turn(self.product, state, 'eight hinges')
        self.assertEqual(state['messages'], before)

    def test_network_error_gives_busy_message(self):
        failing = mock.Mock()
        failing.chat.completions.create.side_effect = openai.APIConnectionError(request=mock.Mock())
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=failing):
            with self.assertRaisesMessage(assistant.AssistantError, assistant.BUSY_MESSAGE):
                assistant.run_turn(self.product, state, 'eight hinges')
        self.assertEqual(state['messages'], [])

    def test_running_out_of_tool_rounds_rolls_back(self):
        calls = [_tool_call('get_draft', {}, f'call_{i}') for i in range(assistant.MAX_TOOL_ROUNDS)]
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(*calls)):
            with self.assertRaises(assistant.AssistantError):
                assistant.run_turn(self.product, state, 'loop forever')
        self.assertEqual(state['messages'], [])

    def test_empty_reply_is_stored_as_okay(self):
        state = assistant.new_state()
        with mock.patch.object(assistant, '_client', return_value=_fake_client(_text(''))):
            reply = assistant.run_turn(self.product, state, 'hello')
        self.assertEqual(reply, 'Okay.')
        self.assertEqual(state['messages'][-1]['content'], 'Okay.')

    def test_old_session_format_keeps_draft_and_restarts_conversation(self):
        old = {'messages': [{'role': 'assistant', 'content': [{'type': 'text', 'text': 'Hi'}]}],
               'draft': [{'type': 'bom'}]}
        state = assistant.load_state(old)
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['draft'], [{'type': 'bom'}])
        self.assertEqual(state['format'], assistant.STATE_FORMAT)


@override_settings(BOM_ASSISTANT_API_KEY='test-key')
class AssistantViewTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.product = Product.objects.create(product_code='TABLE-01', product_name='Coffee Table')
        cls.hinge = Resource.objects.create(
            resource_name='Hinge', category='Hardware', unit='nos', rate=Decimal('50'),
        )

    def setUp(self):
        admin = User.objects.create_user(username='admin1', password='x', is_staff=True)
        self.client.force_login(admin, backend='django.contrib.auth.backends.ModelBackend')

    def _turn(self, text, *responses):
        with mock.patch.object(assistant, '_client', return_value=_fake_client(*responses)):
            return self.client.post(
                reverse('bom:assistant_turn', args=[self.product.pk]),
                data={'text': text}, content_type='application/json',
            )

    def _stage_hinges(self):
        return self._turn(
            'eight hinges',
            _tool_call('stage_material', {'resource_id': self.hinge.pk, 'quantity': 8}),
            _text('Added 8 hinges.'),
        )

    def test_turn_returns_reply_and_draft(self):
        data = self._stage_hinges().json()
        self.assertEqual(data['reply'], 'Added 8 hinges.')
        self.assertEqual(len(data['draft']), 1)

        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertEqual(page.context['assistant_initial']['log'],
                         [{'role': 'user', 'text': 'eight hinges'},
                          {'role': 'assistant', 'text': 'Added 8 hinges.'}])

    def test_voice_is_english_only(self):
        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertContains(page, "recognition.lang = 'en-IN'")
        self.assertNotContains(page, 'ta-IN')

    def test_rate_limit_shows_busy_message_not_500(self):
        self._stage_hinges()
        response = self._turn('two more', _rate_limit_error())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['reply'], assistant.BUSY_MESSAGE)
        self.assertEqual(len(data['draft']), 1)   # draft survives the failed turn

    def test_commit_writes_draft_and_clears_it(self):
        BOMItem.objects.create(product=self.product, resource=self.hinge, quantity=Decimal('2'))
        self._stage_hinges()
        self.client.post(reverse('bom:assistant_commit', args=[self.product.pk]))
        self.assertEqual(BOMItem.objects.get().quantity, Decimal('8'))   # upserted, not duplicated
        self.assertNotIn(str(self.product.pk), self.client.session.get('bom_assistant', {}))

    def test_commit_with_stale_row_writes_nothing(self):
        self._stage_hinges()
        Resource.objects.filter(pk=self.hinge.pk).update(active=False)
        self.client.post(reverse('bom:assistant_commit', args=[self.product.pk]))
        self.assertFalse(BOMItem.objects.exists())

    def test_remove_row_and_reset(self):
        self._stage_hinges()
        data = self.client.post(
            reverse('bom:assistant_remove_row', args=[self.product.pk]),
            data={'index': 0}, content_type='application/json',
        ).json()
        self.assertEqual(data['draft'], [])
        self.client.post(reverse('bom:assistant_reset', args=[self.product.pk]))
        self.assertNotIn(str(self.product.pk), self.client.session.get('bom_assistant', {}))

    def test_empty_text_is_rejected(self):
        response = self.client.post(
            reverse('bom:assistant_turn', args=[self.product.pk]),
            data={'text': '  '}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(BOM_ASSISTANT_API_KEY='')
    def test_hidden_when_api_key_unset(self):
        page = self.client.get(reverse('bom:list', args=[self.product.pk]))
        self.assertNotContains(page, 'Voice Assistant')
        self.assertNotContains(page, 'assistant-panel')
        response = self.client.post(
            reverse('bom:assistant_turn', args=[self.product.pk]),
            data={'text': 'hi'}, content_type='application/json',
        )
        self.assertEqual(response.status_code, 503)


# ── AI BOM reviewer ──────────────────────────────────────────────────

import json as _json
from unittest import mock as _mock

from django.test import override_settings

from apps.bom import reviewer, reviewer_llm
from apps.bom.models import BOMItem


def _bom(resource, qty):
    return {'type': 'bom', 'resource': resource, 'quantity': Decimal(str(qty))}


def _dim(resource, part, w, b, l, unit='ft', pieces=2):
    return {'type': 'dimension', 'resource': resource, 'part_name': part,
            'width': Decimal(str(w)), 'breadth': Decimal(str(b)), 'height': Decimal('0'),
            'length': Decimal(str(l)), 'width_unit': unit, 'breadth_unit': unit,
            'height_unit': 'in', 'length_unit': unit, 'pieces': pieces}


@override_settings(BOM_ASSISTANT_API_KEY='')
class _ReviewerFixtures(TestCase):
    """Four wardrobes that all use hinges, screws and handles, plus ply
    side panels — the 'learned' data."""

    @classmethod
    def setUpTestData(cls):
        cls.hinge = Resource.objects.create(resource_name='Hinge', category='Hardware',
                                            unit='nos', rate=Decimal('87.65'))
        cls.screw = Resource.objects.create(resource_name='Screw 1 inch', category='Hardware',
                                            unit='nos', rate=Decimal('1.23'))
        cls.handle = Resource.objects.create(resource_name='Handle', category='Hardware',
                                             unit='nos', rate=Decimal('45.67'))
        cls.ply = Resource.objects.create(resource_name='Plywood 18mm', category='Wood and Plywood',
                                          material_type='sheet', unit='sqft', rate=Decimal('98.76'))
        cls.wardrobes = []
        for i, hinges in enumerate([4, 4, 6, 4], start=1):
            p = Product.objects.create(product_code=f'WRD-{i}', product_name=f'3-Door Wardrobe {i}')
            BOMItem.objects.create(product=p, resource=cls.hinge, quantity=hinges)
            BOMItem.objects.create(product=p, resource=cls.screw, quantity=40)
            BOMItem.objects.create(product=p, resource=cls.handle, quantity=3)
            WoodPart.objects.create(product=p, resource=cls.ply, part_name='Side Panel',
                                    width=2, breadth=6, length=6, pieces=2,
                                    width_unit='ft', breadth_unit='ft', length_unit='ft')
            cls.wardrobes.append(p)

    def full_list(self):
        return [_bom(self.hinge, 4), _bom(self.screw, 40), _bom(self.handle, 3),
                _dim(self.ply, 'Side Panel', 2, 6, 6)]


class ReviewerStatisticsTests(_ReviewerFixtures):

    def test_identical_list_raises_nothing(self):
        self.assertEqual(reviewer.review(self.full_list(), '3-Door Wardrobe New'), [])

    def test_missing_material_found_from_similar_products(self):
        lines = [_bom(self.hinge, 4), _bom(self.handle, 3)]
        findings = reviewer.review(lines, '3-Door Wardrobe New')
        missing = [f for f in findings if f.kind == 'missing']
        self.assertEqual([f.resource_id for f in missing], [self.screw.pk])
        self.assertEqual(missing[0].suggested, '40')
        self.assertIn('Did you forget', missing[0].message_en)
        self.assertTrue(missing[0].message_ta)

    def test_single_reference_flags_what_was_removed_from_the_copy(self):
        ref = reviewer.Reference(1, 'Shoe Rack', 3.0, bom={self.screw.pk: Decimal('12')})
        findings = reviewer.missing_materials([_bom(self.hinge, 2)], [ref])
        self.assertEqual(findings[0].resource_id, self.screw.pk)
        self.assertIn('Shoe Rack', findings[0].message_en)

    def test_companion_rule(self):
        findings = reviewer.companion_rules([_bom(self.hinge, 4)], reviewer.product_profiles())
        self.assertIn(self.screw.pk, {f.resource_id for f in findings})
        self.assertEqual(findings[0].kind, 'companion')

    def test_quantity_typed_twelve_times_too_big(self):
        lines = self.full_list()
        lines[0] = _bom(self.hinge, 48)
        findings = [f for f in reviewer.review(lines, '3-Door Wardrobe New') if f.kind == 'quantity']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].suggested, '4')
        self.assertEqual(findings[0].current, '48')
        self.assertIn('different unit', findings[0].message_en)

    def test_quantity_within_range_is_fine(self):
        lines = self.full_list()
        lines[0] = _bom(self.hinge, 6)
        self.assertEqual(reviewer.review(lines, '3-Door Wardrobe New'), [])

    def test_measurement_over_twelve_feet(self):
        lines = self.full_list()
        lines[3] = _dim(self.ply, 'Side Panel', 2, 6, 72)
        findings = reviewer.review(lines, '3-Door Wardrobe New')
        self.assertEqual([(f.kind, f.line_index) for f in findings], [('dimension', 0)])
        self.assertIn('12 feet', findings[0].message_en)

    def test_measurement_far_from_same_part(self):
        lines = self.full_list()
        lines[3] = _dim(self.ply, 'Side Panel', 2, 6, 6, unit='in')   # inches instead of feet
        findings = reviewer.review(lines, '3-Door Wardrobe New')
        self.assertEqual(findings[0].kind, 'dimension')

    def test_findings_never_contain_rates(self):
        lines = [_bom(self.hinge, 48)]
        text = _json.dumps([f.to_dict() for f in reviewer.review(lines, '3-Door Wardrobe New')])
        for rate in ('87.65', '1.23', '45.67', '98.76'):
            self.assertNotIn(rate, text)

    def test_dismissed_and_upheld_suggestion_is_suppressed(self):
        from apps.carpenter.models import BOMSubmission, SubmissionFinding
        for product in self.wardrobes[:3]:
            submission = BOMSubmission.objects.create(product=product)
            SubmissionFinding.objects.create(
                submission=submission, kind='missing', resource=self.screw, message='x',
                carpenter_response='dismissed', admin_outcome='rejected',
            )
        lines = [_bom(self.hinge, 4), _bom(self.handle, 3)]
        findings = reviewer.review(lines, '3-Door Wardrobe New')
        self.assertNotIn(self.screw.pk, {f.resource_id for f in findings})

    def test_record_outcomes_labels_findings(self):
        from apps.carpenter.models import BOMSubmission, SubmissionFinding
        submission = BOMSubmission.objects.create(product=self.wardrobes[0])
        missing = SubmissionFinding.objects.create(submission=submission, kind='missing',
                                                   resource=self.screw, message='x')
        ignored = SubmissionFinding.objects.create(submission=submission, kind='missing',
                                                   resource=self.handle, message='x')
        qty = SubmissionFinding.objects.create(submission=submission, kind='quantity',
                                               resource=self.hinge, message='x', current_value='48')
        reviewer.record_outcomes(submission, [_bom(self.hinge, 4), _bom(self.screw, 40)])
        for finding, expected in ((missing, 'confirmed'), (ignored, 'rejected'), (qty, 'confirmed')):
            finding.refresh_from_db()
            self.assertEqual(finding.admin_outcome, expected)


def _llm_client(content):
    message = _mock.Mock(content=content)
    response = _mock.Mock(choices=[_mock.Mock(message=message)])
    client = _mock.Mock()
    client.chat.completions.create.return_value = response
    return client


@override_settings(BOM_ASSISTANT_API_KEY='test-key')
class ReviewerLLMTests(_ReviewerFixtures):

    def _run(self, content, lines=None):
        lines = lines or self.full_list()
        refs = reviewer.find_similar_products('3-Door Wardrobe New', lines)
        client = _llm_client(content)
        with _mock.patch.object(reviewer_llm, '_client', return_value=client):
            return reviewer_llm.ai_findings('3-Door Wardrobe New', lines, refs, [], []), client

    def test_valid_reply_becomes_ai_findings(self):
        lines = [_bom(self.hinge, 4), _bom(self.screw, 40)]
        reply = _json.dumps({'findings': [
            {'kind': 'missing', 'material': 'Handle', 'suggested_value': '3',
             'question_en': 'A 3-door wardrobe needs handles. Did you forget them?',
             'question_ta': 'கைப்பிடி?', 'reason': 'doors need handles'},
            {'kind': 'quantity', 'material': 'Hinge', 'suggested_value': '6',
             'question_en': 'Three doors usually need 6 hinges. Is 4 right?', 'question_ta': ''},
        ]})
        findings, _ = self._run(reply, lines)
        self.assertEqual([(f.kind, f.resource_id, f.source) for f in findings],
                         [('missing', self.handle.pk, 'ai'), ('quantity', self.hinge.pk, 'ai')])
        self.assertEqual(findings[1].current, '4')
        self.assertEqual(findings[1].message_ta, findings[1].message_en)   # Tamil falls back

    def test_unknown_material_is_dropped(self):
        reply = _json.dumps({'findings': [
            {'kind': 'missing', 'material': 'Gold leaf', 'question_en': 'Gold leaf?'},
        ]})
        self.assertEqual(self._run(reply)[0], [])

    def test_bad_json_returns_nothing(self):
        self.assertEqual(self._run('Sure! Here are my thoughts...')[0], [])

    def test_fenced_json_is_accepted(self):
        reply = '```json\n{"findings": [{"kind": "other", "material": "", ' \
                '"question_en": "Is the polish included?"}]}\n```'
        self.assertEqual(self._run(reply)[0][0].kind, 'other')

    def test_provider_error_returns_nothing(self):
        client = _mock.Mock()
        client.chat.completions.create.side_effect = RuntimeError('429')
        with _mock.patch.object(reviewer_llm, '_client', return_value=client):
            self.assertEqual(reviewer_llm.ai_findings('x', self.full_list(), [], [], []), [])

    def test_payload_never_contains_rates(self):
        _, client = self._run('{"findings": []}', [_bom(self.hinge, 48)])
        sent = _json.dumps(client.chat.completions.create.call_args.kwargs['messages'])
        for rate in ('87.65', '1.23', '45.67', '98.76'):
            self.assertNotIn(rate, sent)
        self.assertNotIn('rate', sent.replace('accurate', ''))

    def test_review_merges_without_duplicates(self):
        lines = [_bom(self.hinge, 4), _bom(self.handle, 3)]
        reply = _json.dumps({'findings': [
            {'kind': 'missing', 'material': 'Screw 1 inch', 'question_en': 'Screws?'},
        ]})
        with _mock.patch.object(reviewer_llm, '_client', return_value=_llm_client(reply)):
            findings = reviewer.review(lines, '3-Door Wardrobe New', use_ai=True)
        self.assertEqual([(f.resource_id, f.source) for f in findings], [(self.screw.pk, 'stats')])


# ── Sheet materials are Width × Length (no Breadth) ─────────────────

from apps.bom.services import LineError, clean_dimension_line


class SheetDimensionLineTests(TestCase):
    def setUp(self):
        self.ply = Resource.objects.create(
            resource_name='Plywood 18mm', category='Wood and Plywood',
            material_type='sheet', unit='sqft', rate=Decimal('90'),
        )
        self.teak = Resource.objects.create(
            resource_name='Teak', category='Wood and Plywood',
            material_type='solid_wood', unit='cft', rate=Decimal('4000'),
        )

    def test_sheet_line_needs_no_breadth(self):
        line = clean_dimension_line(self.ply.pk, 'Top', '2', '', '4', '1',
                                    width_unit='ft', length_unit='ft')
        self.assertEqual(line['breadth'], 0)
        self.assertEqual(line['length'], Decimal('4'))

    def test_sheet_line_ignores_a_sent_breadth(self):
        line = clean_dimension_line(self.ply.pk, 'Top', '2', '9', '4', '1')
        self.assertEqual(line['breadth'], 0)

    def test_solid_wood_still_needs_breadth(self):
        with self.assertRaises(LineError):
            clean_dimension_line(self.teak.pk, 'Leg', '2', '', '30', '4')

    def test_sheet_line_needs_length(self):
        with self.assertRaises(LineError):
            clean_dimension_line(self.ply.pk, 'Top', '2', '', '', '1')
