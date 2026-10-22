"""Persist safe re-entry points for the pinned client's native tutorial.

The original movie keeps selections, walking orders, resource drops and store
placement only in memory. Saving its literal current step would resume some
lessons without the state needed to finish them. ``startingTutorialStep`` is
therefore a checkpoint, while ``completed_tutorial`` remains a separate flag.
These helpers never grant rewards or change the village's map.
"""


TUTORIAL_STEP_KEY = 'startingTutorialStep'
TUTORIAL_COMPLETE_STEP = 31
MAX_TUTORIAL_STEP = 45


class TutorialError(ValueError):
    """The client sent an invalid tutorial step."""


def _parse_step(value):
    if isinstance(value, str):
        value = value.strip()
        if not value or not value.isascii() or not value.isdigit() or len(value) > 2:
            raise TutorialError('Etapa do tutorial inválida.')
        value = int(value)
    if type(value) is not int or not 0 <= value <= MAX_TUTORIAL_STEP:
        raise TutorialError('Etapa do tutorial inválida.')
    return value


def _checkpoint(step):
    # Re-enter through the selection/control that reconstructs transient state.
    if step == 2:
        return 1  # Select the town hall before training.
    if 4 <= step <= 7:
        return 3  # Select a villager before moving/cutting.
    if 9 <= step <= 10:
        return 8  # Open the store before choosing/placing a house.
    if 12 <= step <= 13:
        return 11  # Select a knight before ordering the tutorial battle.
    if step == 16:
        return 15  # Open Arthur's mission before its transient information panel.
    if 18 <= step <= 19:
        return 17  # Reopen the store before choosing/placing the farm land.
    if step == 21:
        return 20  # Open Arthur's second mission before confirming its panel.
    if step == 23:
        return 22  # Select the town hall before training another villager.
    if 25 <= step <= 26:
        return 24  # Select a villager before ordering work on the farm.
    if step == 29:
        return 28  # Open Arthur's wood mission before confirming its panel.
    return step


def _stored_step(state):
    try:
        return _checkpoint(_parse_step(state.get(TUTORIAL_STEP_KEY, 0)))
    except TutorialError:
        return 0


def _completed(player):
    value = player.get('completed_tutorial', 0)
    if value is True:
        return True
    try:
        return _parse_step(value) > 0
    except TutorialError:
        return False


def _set_integer(mapping, key, value):
    if type(mapping.get(key)) is int and mapping[key] == value:
        return False
    mapping[key] = value
    return True


def _apply_checkpoint(save, step):
    state = save.setdefault('privateState', {})
    player = save.setdefault('playerInfo', {})
    was_completed = _completed(player)
    done = was_completed or step >= TUTORIAL_COMPLETE_STEP
    if done:
        step = max(step, TUTORIAL_COMPLETE_STEP)
    changed = _set_integer(state, TUTORIAL_STEP_KEY, step)
    changed = _set_integer(player, 'completed_tutorial', int(done)) or changed
    if done and not was_completed:
        changed = _set_integer(state, 'dragonNestActive', 1) or changed
    return changed


def record_tutorial_step(save, step):
    """Record a monotonic checkpoint; repeated or delayed events grant nothing.

    Step 15 ends the first seven lessons, followed by Arthur's mission chain.
    Step 31 reaches its final three-tree objective and releases the account,
    matching the original server policy. Later legacy events are still accepted
    without reopening the tutorial. Invalid values never change the save.
    """
    step = _checkpoint(_parse_step(step))
    current = _stored_step(save.get('privateState', {}))
    return _apply_checkpoint(save, max(current, step))


def _home_items(save):
    maps = save.get('maps', [])
    if not isinstance(maps, list) or not maps or not isinstance(maps[0], dict):
        return None
    items = maps[0].get('items', [])
    if not isinstance(items, list):
        return None
    return [item for item in items if isinstance(item, (list, tuple)) and len(item) >= 3]


def prepare_tutorial(save):
    """Normalize a load checkpoint and recover conservative legacy progress.

    Existing saves did not retain tutorial steps. The exact tutorial tree and
    house positions distinguish completed objectives from the seed's scenery.
    Moving enemy units are checked by type, rather than their old coordinates.
    Only tutorial metadata changes; XP, levels, resources and items are retained.
    """
    state = save.get('privateState', {})
    player = save.get('playerInfo', {})
    step = _stored_step(state)
    items = _home_items(save)
    if not _completed(player) and step < TUTORIAL_COMPLETE_STEP and items is not None:
        has_villager = any(item[0] in (500, 501) for item in items)
        has_tutorial_tree = any(tuple(item[:3]) == (19, 50, 58) for item in items)
        has_tutorial_house = any(tuple(item[:3]) == (1, 55, 55) for item in items)
        if step == 3 and not has_villager:
            # Training advances the native UI before its queued buy is sent.
            # A reload in that gap must reopen training, not select empty land.
            step = 1
        if has_villager:
            step = max(step, 3 if has_tutorial_tree else 8)
        if has_tutorial_house:
            step = max(step, 11)
        if step >= 11 and not any(item[0] == 525 for item in items):
            step = max(step, 14)
    return _apply_checkpoint(save, step)
