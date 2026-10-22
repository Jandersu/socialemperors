"""Guard the bytecode bridge used to resume the native tutorial."""

import hashlib
from pathlib import Path
import struct
import unittest

from swf_localization import decode_swf, encode_tag, iter_tags, localize_swf
from swf_private_economy import patch_private_economy
from swf_tutorial import (
    ORIGINAL_TUTORIAL_CHECK, ORIGINAL_TUTORIAL_NEXT_STEP_PREFIX,
    ORIGINAL_REMOVE_ELEMENT_PREFIX, REMOVE_ELEMENT_OFFSET, SAFE_REMOVE_ELEMENT_PREFIX,
    ORIGINAL_TUTORIAL_NEXT_STEP_INPUT, RESTORED_TUTORIAL_NEXT_STEP_INPUT,
    TUTORIAL_NEXT_STEP_INPUT_OFFSET,
    ORIGINAL_TUTORIAL_TREE_TARGETS, SAFE_TUTORIAL_TREE_TARGETS, TUTORIAL_TREE_TARGETS_OFFSET,
    ORIGINAL_TUTORIAL_CHOP_TREE, RECONCILED_TUTORIAL_CHOP_TREE, TUTORIAL_CHOP_TREE_OFFSET,
    ORIGINAL_TUTORIAL_RESOURCE_INIT, WAIT_FOR_TUTORIAL_RESOURCE_INIT, TUTORIAL_RESOURCE_INIT_OFFSET,
    PRIVATE_RESUMABLE_ABC_SHA256,
    RESUMABLE_ABC_SHA256, RESUMABLE_TUTORIAL_CHECK, TUTORIAL_CHECK_OFFSET,
    RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX, TUTORIAL_NEXT_STEP_OFFSET,
    _RESUME_PREFIX,
    patch_tutorial,
)


def execute_resume_prefix(step, completed=0, town=0, *, next_step=False, moving=False):
    """Execute the bridge's AVM2 subset up to the unchanged native path.

    This exercises branch offsets, public property indexes, operand-stack
    balance and lock restoration together, rather than matching hex alone.
    The actual constructor/actions remain the original SWF and are exercised
    by the browser integration check.
    """
    code = RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX if next_step else RESUMABLE_TUTORIAL_CHECK
    main = {157: town, 1037: True, 5668: True}
    base = {11: main, 33: {953: {16888: completed}, 193: {12369: step}}}
    instance = ({432: step, 6665: moving, 744: {5295: {1610: True}, 10754: {1610: True}}}
                if next_step else {})
    constants = {1: base}
    locals_ = [instance, None, None]
    stack = []
    calls = []
    cursor = peak = 0

    def u30():
        nonlocal cursor
        value = shift = 0
        while True:
            byte = code[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7

    def as_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    while cursor not in ((len(code),) if next_step else (0xea, 0x134)):
        opcode = code[cursor]
        cursor += 1
        if 0xd0 <= opcode <= 0xd2:
            stack.append(locals_[opcode - 0xd0])
        elif opcode == 0x30:
            stack.pop()
        elif opcode == 0x60:
            stack.append(constants[u30()])
        elif opcode == 0x66:
            name = u30()
            stack.append(stack.pop().get(name))
        elif opcode == 0x2c:
            stack.append(u30())
        elif opcode == 0x5d:
            stack.append(u30())
        elif opcode in (0x46, 0x4f):
            name, count = u30(), u30()
            args = [stack.pop() for _ in range(count)]
            stack.pop()
            if opcode == 0x46:
                assert name == 61 and count == 1
                stack.append(as_int(args[0]))
            else:
                assert (name, count) in ((882, 1), (19425, 0))
                calls.append(name)
        elif opcode == 0x24:
            stack.append(int.from_bytes(code[cursor:cursor + 1], 'little', signed=True))
            cursor += 1
        elif opcode in (0xab, 0xad, 0xa0):
            right, left = stack.pop(), stack.pop()
            stack.append(left + right if opcode == 0xa0 else (left == right if opcode == 0xab else left < right))
        elif opcode in (0x10, 0x11, 0x12, 0x15, 0x17):
            offset = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
            cursor += 3
            if opcode == 0x10:
                take = True
            elif opcode in (0x11, 0x12):
                take = bool(stack.pop())
                if opcode == 0x12:
                    take = not take
            else:
                right, left = stack.pop(), stack.pop()
                take = left < right if opcode == 0x15 else left > right
            if take:
                cursor += offset
        elif opcode == 0x73:
            stack.append(as_int(stack.pop()))
        elif opcode == 0xd5:
            locals_[1] = stack.pop()
        elif opcode in (0x26, 0x27):
            stack.append(opcode == 0x26)
        elif opcode == 0x2a:
            stack.append(stack[-1])
        elif opcode == 0x47:
            break
        elif opcode == 0x61:
            name, value = u30(), stack.pop()
            stack.pop()[name] = value
        elif opcode != 0x02:
            raise AssertionError(f'Unexpected bridge opcode {opcode:#x}')
        peak = max(peak, len(stack))
        assert len(stack) <= 3
    assert not stack
    if next_step:
        instance['main'] = main
        instance['calls'] = calls
    return instance, cursor, peak


def execute_input_restoration(step, mayor):
    """Run the post-popup window with a map disabled by the old GUI hover."""
    code = RESTORED_TUTORIAL_NEXT_STEP_INPUT
    main = {3680: False}
    locals_ = [{2117: mayor}, step]
    constants = {1: {11: main}}
    stack, calls = [], []
    cursor = peak = 0

    def u30():
        nonlocal cursor
        value = shift = 0
        while True:
            byte = code[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7

    while cursor < len(code):
        opcode = code[cursor]
        cursor += 1
        if opcode in (0xd0, 0xd1):
            stack.append(locals_[opcode - 0xd0])
        elif opcode == 0x24:
            stack.append(code[cursor])
            cursor += 1
        elif opcode in (0x15, 0x13):
            jump = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
            cursor += 3
            right, left = stack.pop(), stack.pop()
            if left < right if opcode == 0x15 else left == right:
                cursor += jump
        elif opcode == 0x60:
            stack.append(constants[u30()])
        elif opcode == 0x66:
            name = u30()
            stack.append(stack.pop()[name])
        elif opcode == 0x4f:
            name, count = u30(), u30()
            assert (name, count) == (305, 0)  # Native enableMap reinstalls CLICK.
            stack.pop()[3680] = True
            calls.append(name)
        elif opcode == 0x20:
            stack.append(None)
        else:
            raise AssertionError(f'Unexpected input-restoration opcode {opcode:#x}')
        peak = max(peak, len(stack))
        assert len(stack) <= 3
    assert not stack
    assert cursor in (len(code), len(code) + 11)
    return main, calls, cursor, peak


def execute_resume_post_constructor(step):
    """Run the resumed-load hook after the unchanged constructor attached UI.

    Timers are deliberately absent: the phase cleanup must not call the native
    endTutorial method before countdownTimer has been created during loading.
    """
    code = RESUMABLE_TUTORIAL_CHECK
    mayor = {'host': 'native'}
    update = object()
    tutorial = {744: {1610: True}, 17044: 'voice', 2117: mayor, 14619: update}
    main = {228: tutorial, 3680: False, 11456: False}
    constants = {29: {104: 'enterFrame'}}
    locals_ = [main, step, None]  # Native constructor path killed local 2.
    stack, calls = [], []
    cursor, peak = len(_RESUME_PREFIX), 0

    def u30():
        nonlocal cursor
        value = shift = 0
        while True:
            byte = code[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7

    while cursor != 0x170:  # Continue through the original native return.
        opcode = code[cursor]
        cursor += 1
        if opcode in (0xd0, 0xd1, 0xd2):
            stack.append(locals_[opcode - 0xd0])
        elif opcode == 0xd6:
            locals_[2] = stack.pop()
        elif opcode == 0x24:
            stack.append(code[cursor])
            cursor += 1
        elif opcode == 0x60:
            stack.append(constants[u30()])
        elif opcode == 0x66:
            name = u30()
            stack.append(stack.pop()[name])
        elif opcode in (0x61, 0x68):
            name, value = u30(), stack.pop()
            stack.pop()[name] = value
        elif opcode == 0x20:
            stack.append(None)
        elif opcode in (0x26, 0x27):
            stack.append(opcode == 0x26)
        elif opcode in (0x10, 0x15):
            jump = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
            cursor += 3
            take = True
            if opcode == 0x15:
                right, left = stack.pop(), stack.pop()
                take = left < right
            if take:
                cursor += jump
        elif opcode == 0x4f:
            name, count = u30(), u30()
            args = [stack.pop() for _ in range(count)][::-1]
            receiver = stack.pop()
            if (name, count) == (103, 1):
                assert receiver is tutorial and args == [mayor]
            elif (name, count) == (57, 2):
                assert receiver is tutorial and args == ['enterFrame', update]
            elif (name, count) == (13779, 1):
                assert receiver is main and args == [step]
            elif (name, count) == (305, 0):
                assert receiver is main
                main[3680] = True
            else:
                raise AssertionError(f'Unexpected resumed-load UI call {name}')
            calls.append((name, args))
        elif opcode != 0x09:
            raise AssertionError(f'Unexpected resumed-load opcode {opcode:#x}')
        peak = max(peak, len(stack))
        assert len(stack) <= 3
    assert not stack
    return main, tutorial, mayor, calls, peak


def execute_resource_initialization_guard(*, patched, tutorial, initialized, mode=1, activation=3.24):
    """Run the real native tick prelude up to its first collection action.

    In normal mode the collection path at 0x98 must wait until contained units
    have been initialized, including during the tutorial. Native animation and
    the inactive-element early return remain outside the replacement window.
    """
    source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
    body, offset = decode_swf(source)
    payload = next(payload for tag, payload, _ in iter_tags(body, offset) if tag == 82)
    abc = payload[payload.index(b'\0', 4) + 1:]
    method_offset = TUTORIAL_RESOURCE_INIT_OFFSET - 0x6a
    code = abc[method_offset:method_offset + 0x98]
    if patched:
        end = 0x6a + len(ORIGINAL_TUTORIAL_RESOURCE_INIT)
        code = code[:0x6a] + WAIT_FOR_TUTORIAL_RESOURCE_INIT + code[end:]
    element = {280: activation}
    main = {249: tutorial, 9479: initialized, 166: mode}
    constants = {1: {11: main}, 2: {331: 1}}
    locals_ = [element] + [None] * 18
    stack, calls = [], []
    cursor = peak = 0
    returned = False

    def u30():
        nonlocal cursor
        value = shift = 0
        while True:
            byte = code[cursor]
            cursor += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7

    while cursor < len(code):
        opcode = code[cursor]
        cursor += 1
        if 0xd0 <= opcode <= 0xd3:
            stack.append(locals_[opcode - 0xd0])
        elif 0xd4 <= opcode <= 0xd7:
            locals_[opcode - 0xd4] = stack.pop()
        elif opcode == 0x30:
            stack.pop()
        elif opcode == 0x24:
            stack.append(code[cursor])
            cursor += 1
        elif opcode in (0x20, 0x21):
            stack.append(None)
        elif opcode == 0x80:
            u30()  # Native initialization casts null values to local types.
        elif opcode == 0x82:
            pass
        elif opcode == 0x63:
            locals_[u30()] = stack.pop()
        elif opcode == 0x60:
            stack.append(constants[u30()])
        elif opcode == 0x66:
            name = u30()
            stack.append(stack.pop()[name])
        elif opcode == 0x4f:
            name, count = u30(), u30()
            assert (name, count) == (3431, 0)  # Native controlAnimation only.
            assert stack.pop() is element
            calls.append(name)
        elif opcode == 0x96:
            stack.append(not stack.pop())
        elif opcode == 0x2a:
            stack.append(stack[-1])
        elif opcode == 0x29:
            stack.pop()
        elif opcode == 0xab:
            right, left = stack.pop(), stack.pop()
            stack.append(left == right)
        elif opcode in (0x10, 0x11, 0x12):
            jump = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
            cursor += 3
            take = True
            if opcode != 0x10:
                take = bool(stack.pop())
                if opcode == 0x12:
                    take = not take
            if take:
                cursor += jump
        elif opcode == 0x47:
            returned = True
            break
        elif opcode != 0x02:
            raise AssertionError(f'Unexpected native tick guard opcode {opcode:#x}')
        peak = max(peak, len(stack))
        assert len(stack) <= 3
    assert not stack
    return returned, cursor, calls, peak


class BuildingReference(dict):
    """A typed native tile reference, distinct from a lookalike plain object."""


class FinalTreeVm:
    """Execute both final-lesson windows with native display-call stand-ins.

    The VM supports only the audited AVM2 subset. An attempted resource command,
    unexpected method or stack/scope mistake fails immediately. The authoritative
    save and the display tiles are separate, as in the loaded client.
    """

    UNDEFINED = object()
    TARGETS = (43, 44, 45)
    WIDTH = 100

    def __init__(self, tiles):
        self.tiles = {54 * self.WIDTH + x: tile for x, tile in tiles.items()}
        self.tutorial = {432: 30}
        self.main = {176: self.tiles, 228: self.tutorial, 249: True}
        self.gui = {146: {1664: {}}, 944: {}, 1549: {}}
        self.lexical = {2053: None}
        self.constants = {
            1: {11: self.main, 40: self.gui, 27: {}, 63: {}},
            28: {67: self.WIDTH}, 1659: {5221: 'TUTORIAL_COMPLETED'},
            19: {}, 114: {},
        }
        self.calls = []
        self.icons = []
        self.counts = []
        self.backward_targets = []
        self.peak = 0

    @staticmethod
    def tree(item_id=19):
        return BuildingReference({18: {37: item_id}, 144: {}})

    def call(self, name, receiver, args):
        self.calls.append((name, args))
        if name == 14647:  # Native addCounterTrees creates its display counter.
            self.lexical[2053] = {1476: {345: '0'}}
        elif name == 16677:  # addIconoTutorial is display-only.
            self.icons.append(receiver)
        elif name == 3730:  # Native nextStep, outside this audited window.
            receiver[432] += 1
        elif name == 13526:
            self.run(RECONCILED_TUTORIAL_CHOP_TREE)
        elif name == 20:  # TextFieldUtil.setHTML(field, count).
            self.assert_equal(len(args), 2)
            args[0][345] = args[1]
            self.counts.append(int(args[1]))
        elif name == 103:
            self.assert_equal(args, [self.lexical[2053]])
        elif name == 177:
            self.assert_equal(args, [{'event': 'TUTORIAL_COMPLETED'}])
        else:
            # Exactly the original finalization calls; no command/reward API.
            self.assert_equal(len(args), 1 if name == 3614 else 0)
            if name not in (5356, 13503, 17977, 23348, 3614, 12054):
                raise AssertionError(f'Unexpected native finalization call {name}')

    @staticmethod
    def assert_equal(actual, expected):
        if actual != expected:
            raise AssertionError((actual, expected))

    def run(self, code):
        locals_ = [self.tutorial] + [None] * 14
        stack = []
        cursor = iterations = 0

        def u30():
            nonlocal cursor
            value = shift = 0
            while True:
                byte = code[cursor]
                cursor += 1
                value |= (byte & 127) << shift
                if not byte & 128:
                    return value
                shift += 7

        while cursor < len(code):
            iterations += 1
            if iterations > 1000:
                raise AssertionError('Final tutorial bytecode did not terminate')
            opcode = code[cursor]
            cursor += 1
            if 0xd0 <= opcode <= 0xd3:
                stack.append(locals_[opcode - 0xd0])
            elif 0xd4 <= opcode <= 0xd7:
                locals_[opcode - 0xd4] = stack.pop()
            elif opcode == 0x30:
                stack.pop()
            elif opcode in (0x62, 0x63):
                local = u30()
                if opcode == 0x62:
                    stack.append(locals_[local])
                else:
                    locals_[local] = stack.pop()
            elif opcode == 0xc2:
                locals_[u30()] += 1
            elif opcode == 0x60:
                name = u30()
                stack.append(self.lexical[name] if name in self.lexical else self.constants[name])
            elif opcode in (0x5e, 0x5d):
                name = u30()
                self.assert_equal(name, 2053 if opcode == 0x5e else 29)
                stack.append(self.lexical if opcode == 0x5e else {'constructor': 'Event'})
            elif opcode == 0x66:
                name = u30()
                if name == 74:
                    name = stack.pop()
                receiver = stack.pop()
                if not isinstance(receiver, dict):
                    raise AssertionError(f'Dereferenced absent/untyped tile {receiver!r}')
                stack.append(receiver.get(name, self.UNDEFINED))
            elif opcode == 0xb2:
                self.assert_equal(u30(), 68)  # istype BuildingReference
                stack.append(isinstance(stack.pop(), BuildingReference))
            elif opcode in (0x61, 0x68):
                name, value = u30(), stack.pop()
                stack.pop()[name] = value
            elif opcode == 0x24:
                stack.append(int.from_bytes(code[cursor:cursor + 1], 'little', signed=True))
                cursor += 1
            elif opcode == 0x2c:
                self.assert_equal(u30(), 1)
                stack.append('')
            elif opcode == 0x20:
                stack.append(None)
            elif opcode in (0x26, 0x27):
                stack.append(opcode == 0x26)
            elif opcode == 0x74:
                stack.append(int(stack.pop()))
            elif opcode == 0x2a:
                stack.append(stack[-1])
            elif opcode == 0x29:
                stack.pop()
            elif opcode == 0x2b:
                stack[-2:] = [stack[-1], stack[-2]]
            elif opcode in (0xa0, 0xa1, 0xa2):
                right, left = stack.pop(), stack.pop()
                if opcode == 0xa0:
                    stack.append(str(left) + str(right) if isinstance(left, str) or isinstance(right, str) else left + right)
                else:
                    stack.append(left - right if opcode == 0xa1 else left * right)
            elif opcode in (0x10, 0x12, 0x13, 0x14, 0x15):
                jump = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
                cursor += 3
                if jump < 0:
                    target = cursor + jump
                    self.backward_targets.append((code, target))
                    # Ruffle's AVM2 verifier requires a Label at a backward
                    # target that has not already been reached by a jump.
                    # Both newly introduced loops enter by falling through.
                    if not 0 <= target < len(code) or code[target] != 0x09:
                        raise AssertionError('Final tutorial backward branch requires a Label target')
                if opcode == 0x10:
                    take = True
                elif opcode == 0x12:
                    take = not stack.pop()
                else:
                    right, left = stack.pop(), stack.pop()
                    take = (left == right if opcode == 0x13 else left != right if opcode == 0x14 else left < right)
                if take:
                    cursor += jump
            elif opcode == 0x4f:
                name, count = u30(), u30()
                args = [stack.pop() for _ in range(count)][::-1]
                self.call(name, stack.pop(), args)
            elif opcode == 0x4a:
                name, count = u30(), u30()
                self.assert_equal((name, count), (29, 1))
                event_name = stack.pop()
                self.assert_equal(stack.pop(), {'constructor': 'Event'})
                stack.append({'event': event_name})
            elif opcode == 0x47:
                break
            elif opcode not in (0x02, 0x09):  # NOP / verifier-visible Label
                raise AssertionError(f'Unexpected final-lesson opcode {opcode:#x}')
            self.peak = max(self.peak, len(stack))
            if len(stack) > 5:
                raise AssertionError('Final-lesson stack exceeds native contract')
        self.assert_equal(stack, [])
        return locals_

    def finalization_count(self, name):
        return sum(called == name for called, _ in self.calls)


class TutorialSwfTests(unittest.TestCase):
    def test_normal_map_resource_ticks_wait_for_workers_initialization_even_in_the_tutorial(self):
        for tutorial in (False, True):
            with self.subTest(tutorial=tutorial):
                waiting = execute_resource_initialization_guard(
                    patched=True, tutorial=tutorial, initialized=False,
                )
                self.assertEqual(waiting[:3], (True, 0x98, [3431]))
                ready = execute_resource_initialization_guard(
                    patched=True, tutorial=tutorial, initialized=True,
                )
                self.assertEqual(ready[:3], (False, 0x98, [3431]))
                self.assertLessEqual(waiting[3], 3)
                self.assertLessEqual(ready[3], 3)
        # This is the original tutorial-only bypass responsible for premature
        # zero-worker resource collection during map initialization.
        self.assertEqual(execute_resource_initialization_guard(
            patched=False, tutorial=True, initialized=False,
        )[:3], (False, 0x98, [3431]))

    def test_resource_tick_guard_preserves_other_modes_initialized_play_and_inactive_elements(self):
        for tutorial in (False, True):
            for mode in range(7):
                for initialized in (False, True):
                    with self.subTest(tutorial=tutorial, mode=mode, initialized=initialized):
                        original = execute_resource_initialization_guard(
                            patched=False, tutorial=tutorial, initialized=initialized, mode=mode,
                        )
                        patched = execute_resource_initialization_guard(
                            patched=True, tutorial=tutorial, initialized=initialized, mode=mode,
                        )
                        if mode != 1 or initialized or not tutorial:
                            self.assertEqual(patched[:3], original[:3])
                        self.assertEqual(patched[0], mode == 1 and not initialized)
                        inactive = execute_resource_initialization_guard(
                            patched=True, tutorial=tutorial, initialized=initialized, mode=mode, activation=0,
                        )
                        self.assertEqual(inactive[:3], (True, 0x6a, [3431]))

    def test_resume_steps_restore_native_input_locks_and_reject_invalid_checkpoints(self):
        for step in range(31):
            with self.subTest(step=step):
                state, path, peak = execute_resume_prefix(step)
                self.assertEqual(path, 0xea)
                self.assertEqual(state, {249: True, 12369: step, 1037: step < 3, 5668: step < 2})
                self.assertEqual(peak, 3)
        for invalid in (-1, 31, 45, 1000, None, 'invalid'):
            with self.subTest(invalid=invalid):
                state, path, _ = execute_resume_prefix(invalid)
                self.assertEqual(path, 0xea)
                self.assertEqual(state, {249: True, 12369: 0, 1037: True, 5668: True})

    def test_completed_players_and_other_maps_keep_the_original_path(self):
        for completed, town in ((1, 0), (1, 1), (0, 1)):
            with self.subTest(completed=completed, town=town):
                state, path, _ = execute_resume_prefix(8, completed, town)
                self.assertEqual(path, 0x134)
                self.assertEqual(state, {})
        self.assertEqual(RESUMABLE_TUTORIAL_CHECK[0xea:0x123], ORIGINAL_TUTORIAL_CHECK[0xea:0x123])
        self.assertEqual(RESUMABLE_TUTORIAL_CHECK[0x127:], ORIGINAL_TUTORIAL_CHECK[0x127:])

    def test_resumed_mission_phase_removes_only_the_intro_host_without_accessing_unbuilt_timers(self):
        for step in (0, 3, 14, 15, 20, 30):
            with self.subTest(step=step):
                main, tutorial, mayor, calls, peak = execute_resume_post_constructor(step)
                self.assertEqual(main[3680], step >= 3)
                self.assertEqual(main[11456], step >= 15)
                self.assertNotIn(9041, main)  # No newTownTimer popup replay.
                self.assertEqual(tutorial[744][1610], step < 15)
                self.assertEqual(tutorial[17044], 'voice' if step < 15 else None)
                self.assertEqual(tutorial[2117], mayor if step < 15 else None)
                expected_calls = [103, 57, 13779] if step >= 15 else []
                if step >= 3:
                    expected_calls.append(305)
                self.assertEqual([name for name, _ in calls], expected_calls)
                self.assertEqual([args for name, args in calls if name == 13779], [[step]] if step >= 15 else [])
                self.assertLessEqual(peak, 3)
        # The back-edge from the completed native constructor must land on the
        # new hook's Label, preserving Ruffle's backward-branch verifier rule.
        jump = RESUMABLE_TUTORIAL_CHECK[0x123:0x127]
        self.assertEqual(jump[0], 0x10)
        target = 0x127 + int.from_bytes(jump[1:], 'little', signed=True)
        self.assertEqual(target, len(_RESUME_PREFIX))
        self.assertEqual(RESUMABLE_TUTORIAL_CHECK[target], 0x09)

    def test_fresh_progression_restores_locks_and_map_listener_after_ui_changes(self):
        for step in (*range(10), *range(11, 31)):
            with self.subTest(step=step):
                state, path, peak = execute_resume_prefix(step, next_step=True)
                self.assertEqual(path, len(RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX))
                self.assertEqual(state[432], step + 1)
                self.assertEqual(state['main'][1037], step + 1 < 3)
                self.assertEqual(state['main'][5668], step + 1 < 2)
                self.assertFalse(state[744][5295][1610])
                self.assertFalse(state[744][10754][1610])
                self.assertEqual(state['calls'], [])
                self.assertLessEqual(peak, 3)
                # Native UI/popup code runs between these two windows. It may
                # leave mapEnabled false after a hovered control disappears.
                main, calls, _, _ = execute_input_restoration(state[432], None)
                self.assertEqual(main[3680], step + 1 >= 3)
                self.assertEqual(calls, [305] if step + 1 >= 3 else [])

    def test_map_listener_restore_keeps_both_native_mayor_animation_paths(self):
        for step in (1, 2, 3, 4, 10, 12, 19, 24, 25, 27, 31):
            for mayor in (None, {'native': 'mayor'}):
                with self.subTest(step=step, mayor=mayor):
                    main, calls, path, peak = execute_input_restoration(step, mayor)
                    self.assertEqual(main[3680], step >= 3)
                    self.assertEqual(calls, [305] if step >= 3 else [])
                    self.assertEqual(path, len(RESTORED_TUTORIAL_NEXT_STEP_INPUT) + (11 if mayor is None else 0))
                    self.assertLessEqual(peak, 3)

    def test_house_placement_still_pans_before_advancing(self):
        state, path, _ = execute_resume_prefix(10, next_step=True)
        self.assertLess(path, len(RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX))
        self.assertEqual(state[432], 10)
        self.assertEqual(state['calls'], [19425])  # Native doPan, then return.
        state, path, _ = execute_resume_prefix(10, next_step=True, moving=True)
        self.assertEqual(path, len(RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX))
        self.assertEqual(state[432], 11)
        self.assertFalse(state['main'][1037])
        self.assertFalse(state['main'][5668])
        self.assertEqual(state['calls'], [])

    def test_disappearing_tree_ignores_absent_tiles_and_keeps_native_sentinel_guard(self):
        source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        body, offset = decode_swf(source)
        payload = next(payload for code, payload, _ in iter_tags(body, offset) if code == 82)
        abc = payload[payload.index(b'\0', 4) + 1:]
        # Continue through the untouched sentinel check up to the first action.
        native_guard = abc[REMOVE_ELEMENT_OFFSET + 0x1b:REMOVE_ELEMENT_OFFSET + 0x29]
        code = SAFE_REMOVE_ELEMENT_PREFIX + native_guard
        for tile in (None, 'missing', -1, {298: 'existing tree'}, 0):
            with self.subTest(tile=tile):
                tile_array = {} if tile == 'missing' else {7: tile}
                local = [{176: tile_array}, 7]
                stack, cursor = [], 0
                returned = False

                def u30():
                    nonlocal cursor
                    value = shift = 0
                    while True:
                        byte = code[cursor]
                        cursor += 1
                        value |= (byte & 127) << shift
                        if not byte & 128:
                            return value
                        shift += 7

                while cursor < len(code):
                    opcode = code[cursor]
                    cursor += 1
                    if opcode in (0xd0, 0xd1):
                        stack.append(local[opcode - 0xd0])
                    elif opcode == 0x30:
                        stack.pop()
                    elif opcode == 0x66:
                        name = u30()
                        if name == 74:
                            name = stack.pop()
                        stack.append(stack.pop().get(name))
                    elif opcode == 0x20:
                        stack.append(None)
                    elif opcode == 0xab:
                        right, left = stack.pop(), stack.pop()
                        stack.append(left == right)
                    elif opcode == 0x24:
                        stack.append(code[cursor])
                        cursor += 1
                    elif opcode in (0x12, 0x0c):
                        jump = int.from_bytes(code[cursor:cursor + 3], 'little', signed=True)
                        cursor += 3
                        if opcode == 0x12:
                            take = not stack.pop()
                        else:  # Native ifnlt, preserving the numeric -1 sentinel.
                            right, left = stack.pop(), stack.pop()
                            take = not (isinstance(left, (int, float)) and left < right)
                        if take:
                            cursor += jump
                    elif opcode == 0x47:
                        returned = True
                        break
                    else:
                        self.assertEqual(opcode, 0x02)
                    self.assertLessEqual(len(stack), 3)
                self.assertEqual(stack, [])
                self.assertEqual(returned, tile in (None, 'missing', -1))

    def test_final_lesson_reconciles_three_two_one_or_zero_remaining_targets(self):
        for remaining in range(4):
            with self.subTest(remaining=remaining):
                tiles = {x: FinalTreeVm.tree() for x in FinalTreeVm.TARGETS[:remaining]}
                vm = FinalTreeVm(tiles)
                before = dict(vm.tiles)
                locals_ = vm.run(SAFE_TUTORIAL_TREE_TARGETS)
                self.assertEqual(vm.tutorial[432], 31)
                self.assertEqual(len(vm.icons), remaining)
                self.assertEqual(vm.counts, [3 - remaining])
                self.assertEqual(locals_[14], 3)
                self.assertEqual(vm.tiles, before)
                self.assertLessEqual(vm.peak, 5)
                self.assertEqual(vm.finalization_count(12054), int(remaining == 0))
                self.assertEqual(vm.finalization_count(177), int(remaining == 0))
                self.assertEqual(vm.main[249], remaining != 0)
                if remaining:
                    self.assertEqual(vm.lexical[2053][1476][345], str(3 - remaining))
                else:
                    self.assertIsNone(vm.lexical[2053])

    def test_final_lesson_skips_null_undefined_sentinel_and_non_tree_tiles(self):
        invalid_tiles = (
            None, FinalTreeVm.UNDEFINED, -1, 0,
            FinalTreeVm.tree(item_id=1), {18: {37: 19}, 144: {}},
        )
        for invalid in invalid_tiles:
            with self.subTest(tile=invalid):
                vm = FinalTreeVm({43: invalid, 44: FinalTreeVm.tree(), 45: FinalTreeVm.tree()})
                before = dict(vm.tiles)
                vm.run(SAFE_TUTORIAL_TREE_TARGETS)
                self.assertEqual(len(vm.icons), 2)
                self.assertEqual(vm.counts, [1])
                self.assertEqual(vm.tiles, before)
                self.assertEqual(vm.finalization_count(12054), 0)

    def test_chop_count_waits_for_tile_removal_and_duplicate_callbacks_do_not_overcount(self):
        vm = FinalTreeVm({x: FinalTreeVm.tree() for x in FinalTreeVm.TARGETS})
        vm.run(SAFE_TUTORIAL_TREE_TARGETS)
        for _ in range(3):
            vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
            self.assertEqual(vm.lexical[2053][1476][345], '0')
            self.assertEqual(vm.finalization_count(12054), 0)
        for harvested, x in enumerate(FinalTreeVm.TARGETS, start=1):
            # Both native paths call onDisappeared synchronously before this
            # callback. A repeat before the next tile clears must not add one.
            del vm.tiles[54 * FinalTreeVm.WIDTH + x]
            vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
            self.assertEqual(vm.counts[-1], harvested)
            if harvested < 3:
                vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
                self.assertEqual(vm.counts[-1], harvested)
                self.assertEqual(vm.finalization_count(12054), 0)
        self.assertIsNone(vm.lexical[2053])
        self.assertFalse(vm.main[249])
        for native_call in (103, 5356, 13503, 17977, 23348, 3614, 12054, 177):
            self.assertEqual(vm.finalization_count(native_call), 1, native_call)
        final_calls = list(vm.calls)
        for _ in range(3):
            vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
        self.assertEqual(vm.calls, final_calls)

    def test_previously_consumed_targets_need_only_the_remaining_real_harvests(self):
        vm = FinalTreeVm({44: FinalTreeVm.tree(), 45: FinalTreeVm.tree()})
        vm.run(SAFE_TUTORIAL_TREE_TARGETS)
        self.assertEqual(vm.counts, [1])
        for x in (44, 45):
            del vm.tiles[54 * FinalTreeVm.WIDTH + x]
            vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
        self.assertEqual(vm.counts, [1, 2, 3])
        self.assertEqual(vm.finalization_count(177), 1)
        self.assertEqual(vm.finalization_count(12054), 1)

    def test_chop_callback_outside_the_final_counter_is_a_no_op(self):
        vm = FinalTreeVm({})
        vm.main[249] = False
        vm.run(RECONCILED_TUTORIAL_CHOP_TREE)
        self.assertEqual(vm.calls, [])
        self.assertFalse(vm.main[249])
        self.assertIsNone(vm.lexical[2053])

    def test_new_final_lesson_loops_require_labels_even_when_nop_would_execute_identically(self):
        vm = FinalTreeVm({x: FinalTreeVm.tree() for x in FinalTreeVm.TARGETS})
        vm.run(SAFE_TUTORIAL_TREE_TARGETS)
        for code in (SAFE_TUTORIAL_TREE_TARGETS, RECONCILED_TUTORIAL_CHOP_TREE):
            with self.subTest(window_length=len(code)):
                targets = {target for window, target in vm.backward_targets if window == code}
                self.assertEqual(len(targets), 1)
                target = targets.pop()
                self.assertEqual(code[target], 0x09)
                broken = bytearray(code)
                broken[target] = 0x02  # Same execution effect, invalid AVM2 loop.
                fixture = FinalTreeVm({x: FinalTreeVm.tree() for x in FinalTreeVm.TARGETS})
                if code == RECONCILED_TUTORIAL_CHOP_TREE:
                    fixture.call(14647, fixture.constants[1659], [])
                with self.assertRaisesRegex(AssertionError, 'backward branch requires a Label'):
                    fixture.run(bytes(broken))

    def test_patch_only_changes_the_audited_method_and_composes_with_localization_and_treasury(self):
        source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        private = patch_private_economy(localize_swf(source))
        for original, expected_hash in ((source, RESUMABLE_ABC_SHA256), (private, PRIVATE_RESUMABLE_ABC_SHA256)):
            with self.subTest(expected_hash=expected_hash):
                derivative = patch_tutorial(original)
                old_body, old_offset = decode_swf(original)
                new_body, new_offset = decode_swf(derivative)
                self.assertEqual(old_body[:old_offset], new_body[:new_offset])
                self.assertEqual(len(old_body), len(new_body))
                old_tags = list(iter_tags(old_body, old_offset))
                new_tags = list(iter_tags(new_body, new_offset))
                self.assertEqual(len(old_tags), len(new_tags))
                abc_count = 0
                for (code, old, old_long), (new_code, new, new_long) in zip(old_tags, new_tags):
                    self.assertEqual((code, old_long), (new_code, new_long))
                    if code != 82:
                        self.assertEqual(old, new)
                        continue
                    abc_count += 1
                    abc_offset = old.index(b'\0', 4) + 1
                    previous_end = 0
                    for offset, original_code, replacement in (
                            (TUTORIAL_CHECK_OFFSET, ORIGINAL_TUTORIAL_CHECK, RESUMABLE_TUTORIAL_CHECK),
                            (REMOVE_ELEMENT_OFFSET, ORIGINAL_REMOVE_ELEMENT_PREFIX, SAFE_REMOVE_ELEMENT_PREFIX),
                            (TUTORIAL_RESOURCE_INIT_OFFSET, ORIGINAL_TUTORIAL_RESOURCE_INIT,
                             WAIT_FOR_TUTORIAL_RESOURCE_INIT),
                            (TUTORIAL_TREE_TARGETS_OFFSET, ORIGINAL_TUTORIAL_TREE_TARGETS,
                             SAFE_TUTORIAL_TREE_TARGETS),
                            (TUTORIAL_CHOP_TREE_OFFSET, ORIGINAL_TUTORIAL_CHOP_TREE,
                             RECONCILED_TUTORIAL_CHOP_TREE),
                            (TUTORIAL_NEXT_STEP_OFFSET, ORIGINAL_TUTORIAL_NEXT_STEP_PREFIX,
                             RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX),
                            (TUTORIAL_NEXT_STEP_INPUT_OFFSET, ORIGINAL_TUTORIAL_NEXT_STEP_INPUT,
                             RESTORED_TUTORIAL_NEXT_STEP_INPUT)):
                        begin = abc_offset + offset
                        end = begin + len(original_code)
                        self.assertEqual(old[previous_end:begin], new[previous_end:begin])
                        self.assertEqual(old[begin:end], original_code)
                        self.assertEqual(new[begin:end], replacement)
                        previous_end = end
                    self.assertEqual(old[previous_end:], new[previous_end:])
                    self.assertEqual(hashlib.sha256(new[abc_offset:]).hexdigest(), expected_hash)
                self.assertEqual(abc_count, 1)
                self.assertEqual(patch_tutorial(derivative), derivative)
        self.assertEqual(source, Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes())

    def test_unknown_or_missing_bytecode_is_rejected(self):
        source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        body, header_length = decode_swf(source)
        tags, without_abc = [], []
        for code, payload, long_length in iter_tags(body, header_length):
            if code == 82:
                payload = payload[:-1] + bytes([payload[-1] ^ 1])
            else:
                without_abc.append(encode_tag(code, payload, long_length))
            tags.append(encode_tag(code, payload, long_length))
        for suffix in (b''.join(tags), b''.join(without_abc)):
            movie_body = body[:header_length] + suffix
            altered = b'FWS' + source[3:4] + struct.pack('<I', len(movie_body) + 8) + movie_body
            with self.assertRaises(ValueError):
                patch_tutorial(altered)


if __name__ == '__main__':
    unittest.main()
