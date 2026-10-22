"""Localize SWF glyph text while retaining fonts, artwork and ActionScript.

The structures follow Adobe's SWF 19 specification, DefineFont2/3 and
DefineText/DefineText2: https://open-flash.github.io/mirrors/swf-spec-19.pdf
Only explicitly catalogued display strings are rewritten.
"""

import struct


class _Bits:
    def __init__(self, data, offset=0):
        self.data = data
        self.position = offset * 8

    def unsigned(self, count):
        value = 0
        for _ in range(count):
            value = value << 1 | ((self.data[self.position // 8] >> (7 - self.position % 8)) & 1)
            self.position += 1
        return value

    def signed(self, count):
        value = self.unsigned(count)
        return value - (1 << count) if count and value & (1 << (count - 1)) else value

    def align(self):
        self.position = (self.position + 7) // 8 * 8
        return self.position // 8


def _rect_end(data, offset):
    return offset + ((data[offset] >> 3) * 4 + 12) // 8


def _matrix_end(data, offset):
    bits = _Bits(data, offset)
    for _ in range(2):
        if bits.unsigned(1):
            width = bits.unsigned(5)
            bits.signed(width)
            bits.signed(width)
    width = bits.unsigned(5)
    bits.signed(width)
    bits.signed(width)
    return bits.align()


def _tags(data, offset):
    while offset + 2 <= len(data):
        header = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        code, size = header >> 6, header & 63
        if size == 63:
            size = struct.unpack_from('<I', data, offset)[0]
            offset += 4
        if offset + size > len(data):
            raise ValueError('Truncated SWF tag')
        payload = data[offset:offset + size]
        offset += size
        yield code, payload
        if code == 39:
            yield from _tags(payload, 4)
        if code == 0:
            break


def build_font_maps(body):
    """Read existing Unicode glyph maps; never replace a font or its outlines."""
    fonts = {}
    for code, data in _tags(body, _rect_end(body, 0) + 4):
        if code not in (48, 75):
            continue
        font_id = struct.unpack_from('<H', data)[0]
        flags = data[2]
        offset = 5 + data[4]
        count = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        table = offset
        wide = bool(flags & 8)
        width = 4 if wide else 2
        position = struct.unpack_from('<I' if wide else '<H', data, table + count * width)[0]
        offset = table + position
        codes = list(struct.unpack_from('<' + 'H' * count, data, offset)) if flags & 4 else list(data[offset:offset + count])
        offset += count * (2 if flags & 4 else 1)
        advances = list(struct.unpack_from('<' + 'h' * count, data, offset + 6)) if flags & 128 else None
        fonts[font_id] = {
            'codes': codes,
            'indices': {chr(value): index for index, value in enumerate(codes)},
            'advances': advances,
            'scale': 20480 if code == 75 else 1024,
        }
    return fonts


def read_static_text(payload, fonts, tag_type=11):
    """Decode text records for localization and verification of real assets."""
    offset = _matrix_end(payload, _rect_end(payload, 2))
    header_end = offset
    glyph_bits, advance_bits = payload[offset:offset + 2]
    offset += 2
    font_id = height = None
    x = y = 0
    records = []
    while payload[offset]:
        start = offset
        flags = payload[offset]
        offset += 1
        if flags & 8:
            font_id = struct.unpack_from('<H', payload, offset)[0]
            offset += 2
        color = None
        if flags & 4:
            color_size = 4 if tag_type == 33 else 3
            color = payload[offset:offset + color_size]
            offset += color_size
        if flags & 1:
            x = struct.unpack_from('<h', payload, offset)[0]
            offset += 2
        if flags & 2:
            y = struct.unpack_from('<h', payload, offset)[0]
            offset += 2
        if flags & 8:
            height = struct.unpack_from('<H', payload, offset)[0]
            offset += 2
        prefix = payload[start:offset]
        count = payload[offset]
        offset += 1
        bits = _Bits(payload, offset)
        glyphs = [(bits.unsigned(glyph_bits), bits.signed(advance_bits)) for _ in range(count)]
        offset = bits.align()
        font = fonts[font_id]
        records.append({
            'text': ''.join(chr(font['codes'][index]) for index, _ in glyphs),
            'font_id': font_id, 'height': height, 'x': x, 'y': y,
            'flags': flags, 'color': color, 'glyphs': glyphs, 'prefix': prefix,
        })
        x += sum(advance for _, advance in glyphs)
    if offset + 1 != len(payload):
        raise ValueError('Invalid SWF static text length')
    return header_end, glyph_bits, advance_bits, records


def _encode_glyphs(glyphs, glyph_bits, advance_bits):
    result = bytearray()
    pending = width = 0
    for index, advance in glyphs:
        for value, count in ((index, glyph_bits), (advance, advance_bits)):
            pending = pending << count | (value & ((1 << count) - 1))
            width += count
            while width >= 8:
                width -= 8
                result.append((pending >> width) & 255)
                pending &= (1 << width) - 1
    if width:
        result.append(pending << (8 - width))
    return bytes(result)


def localize_static_text(payload, fonts, catalog, tag_type=11):
    """Rewrite catalogued glyph runs and fit them inside their original width.

    Text remains in the original embedded font. Longer labels reduce their
    font size rather than overlapping characters or changing button geometry.
    Unchanged records retain their resolved style, position and glyph advances.
    """
    header, glyph_bits, advance_bits, records = read_static_text(payload, fonts, tag_type)
    changed = False
    for record in records:
        source = record['text']
        translated = catalog.get(source, source)
        if translated == source or not translated or len(translated) > 255:
            continue
        font = fonts[record['font_id']]
        if font['advances'] is None or any(letter not in font['indices'] for letter in translated):
            continue
        indices = [font['indices'][letter] for letter in translated]
        old_width = sum(advance for _, advance in record['glyphs'])
        natural = sum(font['advances'][index] for index in indices) * record['height'] / font['scale']
        if old_width <= 0 or natural <= 0:
            continue
        height = max(1, int(record['height'] * min(1, old_width / natural)))
        glyphs = [(index, round(font['advances'][index] * height / font['scale'])) for index in indices]
        while height > 1 and sum(advance for _, advance in glyphs) > old_width:
            height -= 1
            glyphs = [(index, round(font['advances'][index] * height / font['scale'])) for index in indices]
        new_width = sum(advance for _, advance in glyphs)
        x = record['x'] + max(0, old_width - new_width) // 2
        record.update(x=x, height=height, glyphs=glyphs)
        changed = True
    if not changed:
        return payload
    glyph_bits = max(glyph_bits, max(index.bit_length() for record in records for index, _ in record['glyphs']))
    advance_bits = max(advance_bits, max(abs(advance).bit_length() + 1 for record in records for _, advance in record['glyphs']))
    result = bytearray(payload[:header] + bytes([glyph_bits, advance_bits]))
    for record in records:
        # Resolve every run explicitly: changed advances and heights must not
        # propagate to an untouched run through SWF's inherited text state.
        flags = record['flags'] | 8 | 1 | 2
        prefix = bytes([flags]) + struct.pack('<H', record['font_id'])
        if flags & 4:
            prefix += record['color']
        prefix += struct.pack('<hhH', record['x'], record['y'], record['height'])
        result += prefix + bytes([len(record['glyphs'])])
        result += _encode_glyphs(record['glyphs'], glyph_bits, advance_bits)
    result.append(0)
    return bytes(result)
