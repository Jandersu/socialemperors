"""Tutorial checkpoints survive reload without replaying village rewards."""

import copy
import json
from pathlib import Path
import unittest

from tutorial import (
    TUTORIAL_STEP_KEY, TutorialError, prepare_tutorial, record_tutorial_step,
)


class TutorialTests(unittest.TestCase):
    def setUp(self):
        self.save = json.loads(Path('villages/initial.json').read_text(encoding='utf-8'))
        # Reproduce saves created before tutorial checkpoints were persisted.
        self.save['privateState'].pop(TUTORIAL_STEP_KEY, None)

    def assert_only_tutorial_metadata_changed(self, before):
        actual = copy.deepcopy(self.save)
        expected = copy.deepcopy(before)
        for village in (actual, expected):
            village['playerInfo'].pop('completed_tutorial', None)
            village['privateState'].pop(TUTORIAL_STEP_KEY, None)
            village['privateState'].pop('dragonNestActive', None)
        self.assertEqual(actual, expected)

    def add_villager(self):
        self.save['maps'][0]['items'].append([500, 54, 54, 0, 0, 0, [], {}])

    def remove_tutorial_tree(self):
        items = self.save['maps'][0]['items']
        items[:] = [item for item in items if item[:3] != [19, 50, 58]]

    def test_seed_load_adds_checkpoint_once_without_changing_progress(self):
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 0)
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 0)
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_training_cutting_placement_and_battle_resume_through_safe_controls(self):
        stages = (
            (2, 1), (5, 3), (7, 3), (9, 8), (10, 8), (12, 11), (13, 11),
            (16, 15), (18, 17), (19, 17), (21, 20), (23, 22), (25, 24),
            (26, 24), (27, 27), (29, 28), (30, 30),
        )
        for requested, expected in stages:
            with self.subTest(step=requested):
                village = copy.deepcopy(self.save)
                self.assertTrue(record_tutorial_step(village, requested))
                self.assertEqual(village['privateState'][TUTORIAL_STEP_KEY], expected)
                self.assertEqual(village['playerInfo']['completed_tutorial'], 0)

    def test_delayed_and_repeated_events_do_not_regress_checkpoint_or_award_xp(self):
        before = copy.deepcopy(self.save)
        self.assertTrue(record_tutorial_step(self.save, 8))
        self.assertFalse(record_tutorial_step(self.save, 8))
        self.assertFalse(record_tutorial_step(self.save, 5))
        self.assertFalse(record_tutorial_step(self.save, '2'))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 8)
        self.assert_only_tutorial_metadata_changed(before)

    def test_native_end_and_legacy_end_finish_once_without_rewards(self):
        for ending in (31, '31', 45):
            with self.subTest(step=ending):
                self.setUp()
                self.save['privateState']['dragonNestActive'] = 0
                before = copy.deepcopy(self.save)
                self.assertTrue(record_tutorial_step(self.save, ending))
                self.assertEqual(self.save['playerInfo']['completed_tutorial'], 1)
                self.assertEqual(self.save['privateState']['dragonNestActive'], 1)
                self.assertFalse(record_tutorial_step(self.save, ending))
                self.assertFalse(record_tutorial_step(self.save, 0))
                self.assertFalse(prepare_tutorial(self.save))
                self.assert_only_tutorial_metadata_changed(before)

    def test_first_seven_lessons_leave_the_mission_chain_pending_without_rewards(self):
        self.save['privateState']['dragonNestActive'] = 0
        before = copy.deepcopy(self.save)
        self.assertTrue(record_tutorial_step(self.save, 15))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 15)
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 0)
        self.assertEqual(self.save['privateState']['dragonNestActive'], 0)
        self.assertFalse(record_tutorial_step(self.save, 16))
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_arthur_mission_checkpoints_stay_monotonic_until_the_final_tree_objective(self):
        self.save['privateState']['dragonNestActive'] = 0
        before = copy.deepcopy(self.save)
        for step in (15, 17, 20, 22, 24, 27, 28, 30):
            with self.subTest(step=step):
                self.assertTrue(record_tutorial_step(self.save, step))
                self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], step)
                self.assertEqual(self.save['playerInfo']['completed_tutorial'], 0)
                self.assertFalse(record_tutorial_step(self.save, 15))
                self.assertFalse(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState']['dragonNestActive'], 0)
        self.assertTrue(record_tutorial_step(self.save, 31))
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 1)
        self.assertEqual(self.save['privateState']['dragonNestActive'], 1)
        self.assert_only_tutorial_metadata_changed(before)

    def test_invalid_events_are_rejected_before_mutating_any_field(self):
        before = copy.deepcopy(self.save)
        for invalid in (None, True, False, 1.0, -1, 46, '', '3.5', 'abc', '١٥', [], {}):
            with self.subTest(value=invalid), self.assertRaises(TutorialError):
                record_tutorial_step(self.save, invalid)
            self.assertEqual(self.save, before)

    def test_malformed_saved_checkpoints_are_normalized_without_marking_done(self):
        for invalid in (None, True, False, 1.0, -1, 46, '3.5', 'bad', [], {}):
            with self.subTest(value=invalid):
                village = copy.deepcopy(self.save)
                village['privateState'][TUTORIAL_STEP_KEY] = invalid
                self.assertTrue(prepare_tutorial(village))
                self.assertIs(type(village['privateState'][TUTORIAL_STEP_KEY]), int)
                self.assertEqual(village['privateState'][TUTORIAL_STEP_KEY], 0)
                self.assertEqual(village['playerInfo']['completed_tutorial'], 0)
                self.assertFalse(prepare_tutorial(village))

    def test_villager_with_existing_tree_resumes_selection_without_training_again(self):
        self.add_villager()
        self.save['privateState'][TUTORIAL_STEP_KEY] = 6
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 3)
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_reload_between_training_ui_and_queued_purchase_reopens_training(self):
        record_tutorial_step(self.save, 3)
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 1)
        self.assert_only_tutorial_metadata_changed(before)
        # Once the actual purchase arrives, load recovery selects that worker.
        self.add_villager()
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 3)

    def test_legacy_missing_tree_resumes_building_and_retains_existing_level_four(self):
        self.add_villager()
        self.remove_tutorial_tree()
        self.save['maps'][0].update(xp=151, level=4, wood=2930, food=550, coins=400)
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 8)
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 0)
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_missing_tree_without_a_trained_villager_does_not_skip_training(self):
        self.remove_tutorial_tree()
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 0)

    def test_only_the_tutorial_house_proves_construction_was_completed(self):
        self.add_villager()
        self.remove_tutorial_tree()
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 8)
        self.save['maps'][0]['items'].append([1, 55, 55, 0, 0, 0, [], {}])
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 11)
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_moved_tutorial_enemies_keep_battle_available_until_they_are_gone(self):
        self.save['privateState'][TUTORIAL_STEP_KEY] = 11
        items = self.save['maps'][0]['items']
        for item in items:
            if item[0] == 525:
                item[1:3] = [48, 49]
        self.assertFalse(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 11)
        items[:] = [item for item in items if item[0] != 525]
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 14)
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 0)
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_no_enemy_in_an_unstarted_save_is_not_evidence_of_a_completed_battle(self):
        items = self.save['maps'][0]['items']
        items[:] = [item for item in items if item[0] != 525]
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 0)

    def test_existing_completion_flag_is_retained_and_has_a_finished_checkpoint(self):
        self.save['playerInfo']['completed_tutorial'] = True
        self.save['privateState']['dragonNestActive'] = 0
        before = copy.deepcopy(self.save)
        self.assertTrue(prepare_tutorial(self.save))
        self.assertIs(type(self.save['playerInfo']['completed_tutorial']), int)
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 1)
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 31)
        self.assertEqual(self.save['privateState']['dragonNestActive'], 0)
        self.assertFalse(record_tutorial_step(self.save, 3))
        self.assertFalse(prepare_tutorial(self.save))
        self.assert_only_tutorial_metadata_changed(before)

    def test_end_checkpoint_repairs_a_missing_completion_flag(self):
        self.save['privateState'][TUTORIAL_STEP_KEY] = '31'
        self.save['privateState']['dragonNestActive'] = 0
        self.assertTrue(prepare_tutorial(self.save))
        self.assertEqual(self.save['playerInfo']['completed_tutorial'], 1)
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 31)
        self.assertEqual(self.save['privateState']['dragonNestActive'], 1)
        self.assertFalse(prepare_tutorial(self.save))

    def test_reloading_or_replaying_the_finish_keeps_a_disabled_dragon_disabled(self):
        record_tutorial_step(self.save, 31)
        self.save['privateState']['dragonNestActive'] = 0
        before = copy.deepcopy(self.save)
        self.assertFalse(record_tutorial_step(self.save, 31))
        self.assertFalse(prepare_tutorial(self.save))
        self.assertEqual(self.save, before)

    def test_missing_map_evidence_does_not_claim_the_tutorial_battle_is_over(self):
        self.save['privateState'][TUTORIAL_STEP_KEY] = 11
        self.save['maps'] = []
        self.assertFalse(prepare_tutorial(self.save))
        self.assertEqual(self.save['privateState'][TUTORIAL_STEP_KEY], 11)


if __name__ == '__main__':
    unittest.main()
