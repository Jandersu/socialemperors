"""Route the pinned client's cash button to the local, free treasury.

Only Base.gotoCash's 52-byte method body changes. The existing ABC pools,
method metadata, all other code, fonts and source SWF stay intact. The
replacement uses Flash's native navigateToURL and requires no browser script
access. Its destination is the server-owned `gocash` FlashVar.
"""

import hashlib
import struct
import zlib

from swf_localization import decode_swf, encode_tag, iter_tags


SOURCE_ABC_SHA256 = '33200dc98911057fa76e2efc5b669ddcaacb9aff0b3385276f61698cac250d16'
PRIVATE_ABC_SHA256 = '65a2c43bc5c61e173f4eeda76e0f9a22fb5636b99cd59d855e9ad28e01bd489f'
GOTO_CASH_OFFSET = 748359
ORIGINAL_GOTO_CASH = bytes.fromhex(
    'd030607110090000977885a6d31dafa9ac2c8b89014f7401d0264fa40601'
    '60ed0166fd03120b000060ed012cbc67274faf030247'
)
# Validated constant-pool indexes in the pinned movie: URLRequest=219,
# getStage=72, loaderInfo=264, parameters=262, dynamic-name=74,
# navigateToURL=2731; strings gocash=15718 and _self=209. Each operand is
# U30, not a fixed byte width. The highest stack depth is three (unchanged).
#
# new URLRequest(this.getStage().loaderInfo.parameters['gocash']);
# navigateToURL(request, '_self'); return;
PRIVATE_GOTO_CASH = bytes.fromhex(
    'd0305ddb01d04648006688026686022ce67a664a4adb0101'
    '5dab152b2cd1014fab1502'
) + b'\x02' * 16 + b'\x47'  # NOP padding retains every ABC offset.


def patch_private_economy(data):
    """Return a validated derivative without activating external payments."""
    body, header_length = decode_swf(data)
    tags = []
    abc_count = 0
    for code, payload, long_length in iter_tags(body, header_length):
        if code == 82:  # DoABC: flags, NUL-terminated name, ABC bytecode.
            abc_count += 1
            offset = payload.index(b'\0', 4) + 1
            abc = payload[offset:]
            checksum = hashlib.sha256(abc).hexdigest()
            if checksum == SOURCE_ABC_SHA256:
                end = GOTO_CASH_OFFSET + len(ORIGINAL_GOTO_CASH)
                if abc[GOTO_CASH_OFFSET:end] != ORIGINAL_GOTO_CASH:
                    raise ValueError('Pinned cash navigation method does not match its audited body')
                if len(PRIVATE_GOTO_CASH) != len(ORIGINAL_GOTO_CASH):
                    raise ValueError('Cash navigation replacement must retain its original code length')
                abc = abc[:GOTO_CASH_OFFSET] + PRIVATE_GOTO_CASH + abc[end:]
                if hashlib.sha256(abc).hexdigest() != PRIVATE_ABC_SHA256:
                    raise ValueError('Unexpected derivative cash navigation bytecode')
                payload = payload[:offset] + abc
            elif checksum != PRIVATE_ABC_SHA256:
                raise ValueError('Unsupported game bytecode for private treasury navigation')
        tags.append(encode_tag(code, payload, long_length))
    if abc_count != 1:
        raise ValueError('Expected the pinned game movie with exactly one DoABC tag')
    patched = body[:header_length] + b''.join(tags)
    header = data[:4] + struct.pack('<I', len(patched) + 8)
    return header + (zlib.compress(patched) if data[:3] == b'CWS' else patched)


# A descriptive alias is useful to callers examining the game derivative.
private_treasury_swf = patch_private_economy
