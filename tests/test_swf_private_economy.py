"""Keep the private-server cash entry point confined to its audited method."""

import hashlib
from pathlib import Path
import struct
import unittest

from swf_localization import decode_swf, encode_tag, iter_tags, localize_swf
from swf_private_economy import (
    GOTO_CASH_OFFSET, ORIGINAL_GOTO_CASH, PRIVATE_GOTO_CASH,
    PRIVATE_ABC_SHA256, private_treasury_swf,
)


class PrivateEconomySwfTests(unittest.TestCase):
    def test_only_cash_method_changes_after_existing_localization(self):
        source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        localized = localize_swf(source)
        derivative = private_treasury_swf(localized)
        old_body, old_offset = decode_swf(localized)
        new_body, new_offset = decode_swf(derivative)
        old_tags = list(iter_tags(old_body, old_offset))
        new_tags = list(iter_tags(new_body, new_offset))
        self.assertEqual(old_body[:old_offset], new_body[:new_offset])
        self.assertEqual(len(old_body), len(new_body))
        self.assertEqual(len(old_tags), len(new_tags))
        changed = 0
        for (code, old, old_long), (new_code, new, new_long) in zip(old_tags, new_tags):
            self.assertEqual((code, old_long), (new_code, new_long))
            if code != 82:
                self.assertEqual(old, new)
                continue
            changed += 1
            abc_offset = old.index(b'\0', 4) + 1
            self.assertEqual(old[:abc_offset], new[:abc_offset])
            begin = abc_offset + GOTO_CASH_OFFSET
            end = begin + len(ORIGINAL_GOTO_CASH)
            self.assertEqual(old[:begin], new[:begin])
            self.assertEqual(old[end:], new[end:])
            self.assertEqual(old[begin:end], ORIGINAL_GOTO_CASH)
            self.assertEqual(new[begin:end], PRIVATE_GOTO_CASH)
            self.assertEqual(hashlib.sha256(new[abc_offset:]).hexdigest(), PRIVATE_ABC_SHA256)
        self.assertEqual(changed, 1)
        self.assertEqual(source, Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes())
        self.assertEqual(private_treasury_swf(derivative), derivative)

    def test_replacement_uses_existing_u30_pools_and_preserves_stack_contract(self):
        # A tiny instruction reader verifies the replacement actually resolves
        # the declared FlashVar and opens the same tab without ExternalInterface
        # or the old shrinkScreenForShare call.
        code = PRIVATE_GOTO_CASH
        cursor = 0
        stack = 0
        peak = 0
        operations = []

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
            args = []
            if opcode == 0xd0:  # getlocal_0
                stack += 1
            elif opcode == 0x30:  # pushscope
                stack -= 1
            elif opcode in (0x5d, 0x2c):  # findpropstrict / pushstring
                args = [u30()]
                stack += 1
            elif opcode == 0x66:  # getproperty, dynamic multiname needs a name.
                args = [u30()]
                stack -= int(args[0] == 74)
            elif opcode in (0x46, 0x4a, 0x4f):
                args = [u30(), u30()]
                stack -= args[1] + int(opcode == 0x4f)
            elif opcode == 0x47:
                self.assertEqual(cursor, len(code))
                self.assertEqual(stack, 0)
            else:
                self.assertIn(opcode, (0x2b, 0x02))  # swap / NOP
            self.assertGreaterEqual(stack, 0)
            peak = max(peak, stack)
            operations.append((opcode, args))
        self.assertEqual(peak, 3)
        self.assertIn((0x2c, [15718]), operations)  # gocash
        self.assertIn((0x2c, [209]), operations)  # _self
        self.assertIn((0x4f, [2731, 2]), operations)  # navigateToURL
        self.assertEqual(len(PRIVATE_GOTO_CASH), len(ORIGINAL_GOTO_CASH))

    def test_unknown_or_missing_bytecode_is_rejected_before_any_patch(self):
        source = Path('assets/flash/SocialEmpires0926bsec.swf').read_bytes()
        body, header_length = decode_swf(source)
        tags = []
        without_abc = []
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
                private_treasury_swf(altered)


if __name__ == '__main__':
    unittest.main()
