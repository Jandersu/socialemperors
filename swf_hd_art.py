"""Fit higher-resolution textures into two verified legacy bitmap shapes.

Only the three allowlisted fill matrices change. Shape bounds, edge records,
placements and hit areas retain their original bytes. Exported BitmapData
classes are deliberately excluded because their dimensions are visible to AS3.
"""

import struct

from swf_static_text import _Bits, _rect_end


HD_SCALE = 4
HD_BITMAP_IDS = frozenset((31, 220))
# shape ID -> (fill index, bitmap ID, original 16.16 scale coefficients)
HD_SHAPE_FILLS = {
    32: (0, 31, (1310720, 1310720)),
    33: (1, 31, (1404320, 1404320)),
    221: (1, 220, (1310720, 1310720)),
}


def read_matrix(data, offset=0):
    """Return exact fixed-point coefficients, translation and next byte offset."""
    bits = _Bits(data, offset)
    scale = (65536, 65536)
    if bits.unsigned(1):
        width = bits.unsigned(5)
        scale = (bits.signed(width), bits.signed(width))
    skew = (0, 0)
    if bits.unsigned(1):
        width = bits.unsigned(5)
        skew = (bits.signed(width), bits.signed(width))
    width = bits.unsigned(5)
    translation = (bits.signed(width), bits.signed(width))
    return (*scale, *skew, *translation), bits.align()


def encode_matrix(matrix):
    """Encode a SWF MATRIX without rounding its signed fixed-point values."""
    fields = []

    def signed_pair(values):
        width = max(((value if value >= 0 else ~value).bit_length() + 1 for value in values), default=0)
        if width > 31:
            raise ValueError('SWF matrix coefficient exceeds its signed field')
        fields.append((width, 5))
        fields.extend((value & ((1 << width) - 1), width) for value in values)

    for values, defaults in ((matrix[:2], (65536, 65536)), (matrix[2:4], (0, 0))):
        present = tuple(values) != defaults
        fields.append((int(present), 1))
        if present:
            signed_pair(values)
    signed_pair(matrix[4:6])
    result = bytearray()
    pending = count = 0
    for value, width in fields:
        pending = pending << width | value
        count += width
        while count >= 8:
            count -= 8
            result.append((pending >> count) & 255)
            pending &= (1 << count) - 1
    if count:
        result.append(pending << (8 - count))
    return bytes(result)


def _fill_end(data, offset, rgba):
    """Read one DefineShape fill style; never search arbitrary bitmap bytes."""
    kind = data[offset]
    offset += 1
    bitmap_id = matrix_start = None
    matrix = None
    if kind == 0:  # Solid RGB / RGBA.
        offset += 4 if rgba else 3
    elif kind in (0x10, 0x12, 0x13):  # Linear, radial, focal gradient.
        _, offset = read_matrix(data, offset)
        count = data[offset] & 15
        offset += 1 + count * (5 if rgba else 4) + (2 if kind == 0x13 else 0)
    elif kind in (0x40, 0x41, 0x42, 0x43):
        bitmap_id = struct.unpack_from('<H', data, offset)[0]
        matrix_start = offset + 2
        matrix, offset = read_matrix(data, matrix_start)
    else:
        raise ValueError(f'Unsupported SWF fill style {kind:#x}')
    if offset > len(data):
        raise ValueError('Truncated SWF fill style')
    return offset, kind, bitmap_id, matrix_start, matrix


def upgrade_shape_bitmap_fill(payload, tag_code):
    """Shrink the verified texture matrix by four while keeping shape geometry."""
    shape_id = struct.unpack_from('<H', payload)[0]
    if shape_id not in HD_SHAPE_FILLS:
        return payload
    if tag_code not in (2, 22, 32, 83):
        raise ValueError('HD bitmap fill requires a supported DefineShape tag')
    target_index, expected_bitmap, expected_scale = HD_SHAPE_FILLS[shape_id]
    offset = _rect_end(payload, 2)
    if tag_code == 83:  # DefineShape4 adds edge bounds and stroke flags.
        offset = _rect_end(payload, offset) + 1
    count = payload[offset]
    offset += 1
    if count == 255:
        count = struct.unpack_from('<H', payload, offset)[0]
        offset += 2
    if target_index >= count:
        raise ValueError(f'Missing HD bitmap fill for SWF shape {shape_id}')
    for index in range(count):
        end, kind, bitmap_id, start, matrix = _fill_end(payload, offset, tag_code in (32, 83))
        if index == target_index:
            if kind != 0x41 or bitmap_id != expected_bitmap or matrix[:2] != expected_scale or matrix[2:4] != (0, 0):
                raise ValueError(f'Unexpected original HD bitmap fill for SWF shape {shape_id}')
            if any(value % HD_SCALE for value in matrix[:4]):
                raise ValueError('HD bitmap matrix cannot be scaled without rounding')
            scaled = tuple(value // HD_SCALE for value in matrix[:4]) + matrix[4:]
            return payload[:start] + encode_matrix(scaled) + payload[end:]
        offset = end
    raise ValueError(f'Missing HD bitmap fill for SWF shape {shape_id}')
