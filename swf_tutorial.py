"""Resume the pinned client's tutorial without changing its artwork or actions.

Base.tutorialCheck originally restarts at step zero on every load, even after
the tree was harvested or the house was built. The server supplies a safe
checkpoint in privateState.startingTutorialStep. This derivative reads it and
restores the input locks that the completed lessons normally release.

The audited changes occupy 866 bytes across six native methods. Progress
restores the input locks and map listener that native objective events and a
removed GUI hover target can leave disabled. Repeated tree-disappearance
callbacks safely ignore a tile that was already cleared. Stack/local/scope
contracts, artwork, native actions and completed-player behavior stay intact.
Apply this after the private-economy patch, if enabled.
"""

import hashlib
import struct
import zlib

from swf_localization import decode_swf, encode_tag, iter_tags
from swf_private_economy import PRIVATE_ABC_SHA256, SOURCE_ABC_SHA256


TUTORIAL_CHECK_OFFSET = 723409
ORIGINAL_TUTORIAL_CHECK = bytes.fromhex(
    'd0302110090000aeaab39327ae64271f82d56001660b2c9598014ff206015d3d'
    '6001662166b90766f88301463d012400ab2a120b0000296001660b669d012400'
    'ab12ef0000d0262ad661f901d2080229d0262ad6618d08d2080229d024002ad6'
    '61d160d2080229d12ad682d5d2080229102e000009d0262ad661a42cd2080229'
    '0910090000732ac129d0a0c6d1c6d0262ad6618d08d2080229104d0000091048'
    '0000d1d62400d21a0600002400102600002401d21a0600002401101900002403'
    'd21a0600002402100c000010060000240310020000240308021bc4ffff039bffff'
    '9bffffa7ffffc4ffffd05dfb0c4afb0c002ad661e401d2080229d0d066e4014f'
    '2e015dfb0cd066e40146fb0c0160fb0c66e528d066ef6f4f1502600166284fe5'
    '7c00100900009774a0752075c62674103c000060712cde89014f7401d0272ad6'
    '618d08d2080229d066ab04668f0666b54bd066822913160000d066822e4f6900'
    'd066822e603b6679d066e0664f150247'
)

# Existing constant-pool entries: Base=1, Main=11, Player=33, privateState=193,
# startingTutorialStep=12369, tutorialMode=249, mapLocked=1037, tabsLocked=5668.
# The completed_tutorial/townID checks and native telemetry are retained.
# int(undefined) is zero; values outside 0..30 fall back to the introduction.
# Resume checkpoints >=3 need map input; checkpoints >=2 need the bottom bar.
# All branches target instruction boundaries and keep the original constructor
# at 0xea and completed-player path at 0x134. Peak operand stack remains three.
_RESUME_PREFIX = bytes.fromhex(
    'd0306001660b2c9598014ff206015d3d6001662166b90766f88301463d012400ab'
    '120f01006001660b669d012400ab120101006001662166c10166d16073d5'
    'd12400150b0000d1241e17040000100300002400d5d02661f901'
    'd0d12403ad618d08d0d12402ad61a42cd0d161d16010780000'
)

# The guided missions at steps 15..31 follow the seven opening lessons. Their
# native phase transition removes the large host/ENTER_FRAME handler, updates
# the player's local tutorial state and restores the objectives UI. A resumed
# constructor otherwise recreates that host and hides the objectives again.
# Recreate its host/listener cleanup after attaching the fresh tutorial, then
# restore the player's current checkpoint through completarTutorial. The
# native endTutorial also touches countdownTimer, which is not constructed yet
# during a resumed load. Skip that premature timer access and retain the saved
# step instead of replaying step 15. Restore bClosedPopupNewTown as its native
# close callback does: UpdateGame otherwise suppresses mission checks during
# tutorialMode, leaving the guided objectives button absent after a reload.
# No resources, XP or new-town celebration are awarded/replayed.
# The original jump at 0x123 now returns to this Label in unused prefix space.
_RESUME_POST_CONSTRUCTOR = bytes.fromhex(
    '09d1240f15370000d066e401d6d266e8052761ca0cd22061948501d2d266c510'
    '4f6701d22068c510d2601d6668d2669b724f3902d02661c059d0d14fd36b01'
    'd1240315b80000d04fb1020010af0000'
)
RESUMABLE_TUTORIAL_CHECK = (
    _RESUME_PREFIX + _RESUME_POST_CONSTRUCTOR
    + b'\x02' * (0xea - len(_RESUME_PREFIX) - len(_RESUME_POST_CONSTRUCTOR))
    + ORIGINAL_TUTORIAL_CHECK[0xea:0x123] + bytes.fromhex('104bffff')
    + ORIGINAL_TUTORIAL_CHECK[0x127:]
)

# Native objective events invoke nextStep directly, rather than unlockTabs or
# unlockMap. Without this bridge a fresh tutorial reaches the walking lesson
# with mapLocked still true. The prefix preserves the step-10 pan/early return,
# advances currentStep, synchronizes both locks, and hides both arrow markers.
# Local 1 retains the new step for the input restoration after popup creation.
TUTORIAL_NEXT_STEP_OFFSET = 1086832
ORIGINAL_TUTORIAL_NEXT_STEP_PREFIX = bytes.fromhex(
    'd03021100b0000c202d2d7c30275a2d674ab82d5d066b003240aab2a12060000'
    '29d06689349612070000d04fe197010047d02ad782d5d3080366fe4e2401a082'
    'd6d1d261fe4ed066e80566af292761ca0cd066e8056682542761ca0c'
)
RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX = bytes.fromhex(
    'd030d066b003240aab120f0000d066893411070000d04fe197010047'
    'd02a66b0032401a02ad561b0036001660bd066b0032403ad618d08'
    '6001660bd066b0032402ad61a42cd066e80566af292761ca0c'
    'd066e8056682542761ca0c02'
)

# GuiManager.mouseOver removes the map's CLICK listener. Its mouseOut normally
# restores it during the tutorial, but that event can be lost when the hovered
# training/store control disappears. Restore through native enableMap (not a
# raw flag) after the new lesson's popup and UI changes, for steps >=3. This
# matches the tutorial exception already present in GuiManager.mouseOut.
# The original mayor/null check is preserved and its branch still targets
# native animation at 0x1f0 or skips it at 0x1fb. Everything else is unchanged.
TUTORIAL_NEXT_STEP_INPUT_OFFSET = TUTORIAL_NEXT_STEP_OFFSET + 0x1d8
ORIGINAL_TUTORIAL_NEXT_STEP_INPUT = bytes.fromhex(
    'd066c510100b0000d2d7c202add69402c4d27020130b0000'
)
RESTORED_TUTORIAL_NEXT_STEP_INPUT = bytes.fromhex(
    'd12403150800006001660b4fb10200d066c51020130b0000'
)

# The native guard only compares the tile with numeric sentinel -1. A second
# disappearance callback can see null/undefined instead, pass that comparison
# through numeric conversion and dereference `.mc`. Ignore only absent tiles;
# the native -1 check, cleanup, removal command and all valid-item actions stay.
REMOVE_ELEMENT_OFFSET = 728062
ORIGINAL_REMOVE_ELEMENT_PREFIX = bytes.fromhex(
    'd03021100d000091d2d3c204c205850802d6c20382630421826305'
)
SAFE_REMOVE_ELEMENT_PREFIX = bytes.fromhex(
    'd030d066b001d1664a20ab120c0000470202020202020202020202'
)

# Natural resources restore their worker lists during MapInitializer.Init.
# The original timer bypasses that wait in tutorialMode, so loaded deposits can
# expire while their workers are still uninitialized. That path emits harvest
# commands and an automatically collected XP token for every idle deposit.
# Always retain the native NORMAL-mode initialization wait. After the map has
# restored its contained units, native timers/worker harvesting run unchanged.
# Only the tutorial bypass is skipped; the following game-mode and initialized
# checks, activation updates, collection and cleanup are the original bytecode.
TUTORIAL_RESOURCE_INIT_OFFSET = 885626
ORIGINAL_TUTORIAL_RESOURCE_INIT = bytes.fromhex(
    '6001660b66f901962a120e000029'
)
WAIT_FOR_TUTORIAL_RESOURCE_INIT = bytes.fromhex('100a0000') + b'\x02' * 10

# The final lesson highlights three specific seed trees. Old saves can already
# have harvested them. Skip absent/non-tree references before placing the icons
# and reconcile the counter after entering step 31, without respawning targets
# or emitting resource/XP commands. Keep the original outer clickItem branches.
TUTORIAL_TREE_TARGETS_OFFSET = 909839
ORIGINAL_TUTORIAL_TREE_TARGETS = bytes.fromhex(
    '242b24365602242c24365602242d2436560256038008630c60fb0c4fb7720024'
    '0074630e103c0000096001660b66b001620c620e66b10a240166b10a601c6643'
    'a2620c620e66b10a240066b10aa066b10a80442a630d6690014fa5820100620e'
    '9174630e620e620c661615baffff6001660b66e4014f921d00'
)
SAFE_TUTORIAL_TREE_TARGETS = bytes.fromhex(
    '60fb0c4fb77200242b74630e096001660b66b0012436601c6643a2620ea0664a2a'
    'b244121700002a661266252413140c00006690014fa58201001001000029c20e'
    '620e242e15c3ffff6001660b66e4014f921d0060fb0c4fd66900240374630e'
) + b'\x02' * 25

# Both native harvesting paths clear the tile synchronously through
# onDisappeared before calling chopTree (collect: 0x116a -> 0x1182;
# tick: 0x8d2 -> 0x91b). Recompute 3 minus the remaining real target trees,
# rather than blindly incrementing for any tree. Duplicate callbacks therefore
# cannot overcount, and previously consumed targets count as already finished.
# Keep the same counter removal, ability update, timers, dragon spawn and
# TUTORIAL_COMPLETED dispatch. Peak stack remains <=5, with the same two locals.
# Both new backward loops begin with AVM2 Label (0x09), as required by the
# runtime's verifier for loop targets that have no earlier incoming branch.
TUTORIAL_CHOP_TREE_OFFSET = 1085377
ORIGINAL_TUTORIAL_CHOP_TREE = bytes.fromhex(
    'd03024001009000097d3a89790307375d7d56085102013c000005d3d60851066'
    'c40b66d902463d0173d5601360851066c40b2c01d12401a0a04f1402d124020f'
    '9700006001662810090000a1ae28b3d0d3d1937066920166800d6085104f6701'
    '5e8510206185106001661b4fec29006001660b2761f9016001663f4fbf690060'
    '0110090000ac57931fa8c485972a662866b0074fb98c010060016628668d0c4f'
    'b4b6010060016628264f9e1c0160724f965e006001660b66e40120131b0000d0'
    '65006001660b66e40141015d1d60fb0c66e5284a1d014fb1010147'
)
RECONCILED_TUTORIAL_CHOP_TREE = bytes.fromhex(
    'd03060851012bf00006001660bd4242bd5240009d066b0012436601c6643a2d1a0'
    '664a2ab24412110000661266252413140800002401a01001000029c201d1242e'
    '15ceffff24032ba1d5601360851066c40b2c01d1a04f1402d1240315680000'
    '60016628d5d166920166800d6085104f67015e8510206185106001661b4fec29'
    '00d02761f9016001663f4fbf6900d166b0074fb98c0100d1668d0c4fb4b601'
    '00d1264f9e1c0160724f965e00d066e4012013130000d066e4015d1d60fb0c'
    '66e5284a1d014fb1010147'
) + b'\x02' * 18

RESUMABLE_ABC_SHA256 = 'ceeaf745ad76689d6ea6c6986e0a26b85754d5ee3134c2c89bcfa16dc93f7402'
PRIVATE_RESUMABLE_ABC_SHA256 = '8bfeb3c31396925540b776c1dd5216546f006a91a886d72ceec16f8712d8c0b1'
_DERIVATIVES = {
    SOURCE_ABC_SHA256: RESUMABLE_ABC_SHA256,
    PRIVATE_ABC_SHA256: PRIVATE_RESUMABLE_ABC_SHA256,
}
_AUDITED_REPLACEMENTS = (
    (TUTORIAL_CHECK_OFFSET, ORIGINAL_TUTORIAL_CHECK, RESUMABLE_TUTORIAL_CHECK),
    (REMOVE_ELEMENT_OFFSET, ORIGINAL_REMOVE_ELEMENT_PREFIX, SAFE_REMOVE_ELEMENT_PREFIX),
    (TUTORIAL_RESOURCE_INIT_OFFSET, ORIGINAL_TUTORIAL_RESOURCE_INIT, WAIT_FOR_TUTORIAL_RESOURCE_INIT),
    (TUTORIAL_TREE_TARGETS_OFFSET, ORIGINAL_TUTORIAL_TREE_TARGETS, SAFE_TUTORIAL_TREE_TARGETS),
    (TUTORIAL_CHOP_TREE_OFFSET, ORIGINAL_TUTORIAL_CHOP_TREE, RECONCILED_TUTORIAL_CHOP_TREE),
    (TUTORIAL_NEXT_STEP_OFFSET, ORIGINAL_TUTORIAL_NEXT_STEP_PREFIX, RESUMABLE_TUTORIAL_NEXT_STEP_PREFIX),
    (TUTORIAL_NEXT_STEP_INPUT_OFFSET, ORIGINAL_TUTORIAL_NEXT_STEP_INPUT, RESTORED_TUTORIAL_NEXT_STEP_INPUT),
)


def patch_tutorial(data):
    """Return an audited tutorial derivative; reject any unknown client movie."""
    body, header_length = decode_swf(data)
    tags = []
    abc_count = 0
    for code, payload, long_length in iter_tags(body, header_length):
        if code == 82:
            abc_count += 1
            offset = payload.index(b'\0', 4) + 1
            abc = payload[offset:]
            checksum = hashlib.sha256(abc).hexdigest()
            expected = _DERIVATIVES.get(checksum)
            if expected:
                for begin, original, replacement in _AUDITED_REPLACEMENTS:
                    end = begin + len(original)
                    if abc[begin:end] != original:
                        raise ValueError('Pinned tutorial method does not match its audited body')
                    if len(replacement) != len(original):
                        raise ValueError('Tutorial replacement must retain its original code length')
                    abc = abc[:begin] + replacement + abc[end:]
                if hashlib.sha256(abc).hexdigest() != expected:
                    raise ValueError('Unexpected derivative tutorial bytecode')
                payload = payload[:offset] + abc
            elif checksum not in _DERIVATIVES.values():
                raise ValueError('Unsupported game bytecode for tutorial checkpoints')
        tags.append(encode_tag(code, payload, long_length))
    if abc_count != 1:
        raise ValueError('Expected the pinned game movie with exactly one DoABC tag')
    patched = body[:header_length] + b''.join(tags)
    header = data[:4] + struct.pack('<I', len(patched) + 8)
    return header + (zlib.compress(patched) if data[:3] == b'CWS' else patched)
