"""
Unit tests for BIBD generator.
"""

import pytest
import itertools
from bibd import (
    check_bibd_feasibility, generate_bibd, validate_bibd,
    bibd_for_study, format_design_dat
)


class TestFeasibility:
    def test_al_config_feasible(self):
        r = check_bibd_feasibility(11, 4, 11)
        assert r['feasible'] == True
        assert r['r'] == 4
        assert r['strict_bibd'] == False   # 11,4,11 is approximate only
        assert abs(r['lambda'] - 1.2) < 0.001

    def test_infeasible_non_integer_r(self):
        r = check_bibd_feasibility(10, 4, 11)
        assert r['feasible'] == False
        assert 'divisible' in r['reason']

    def test_other_feasible_strict(self):
        # 7 items, 3 per task, 7 tasks: classic Fano plane — strict BIBD
        r = check_bibd_feasibility(7, 3, 7)
        assert r['feasible'] == True
        assert r['strict_bibd'] == True
        assert r['r'] == 3
        assert r['lambda'] == 1

    def test_11_5_11_strict(self):
        # 11 items, 5 per task, 11 tasks: strict BIBD
        r = check_bibd_feasibility(11, 5, 11)
        assert r['feasible'] == True
        assert r['strict_bibd'] == True
        assert r['r'] == 5
        assert r['lambda'] == 2

    def test_15_items_5_per_task(self):
        r = check_bibd_feasibility(15, 5, 21)
        assert r['feasible'] == True
        assert r['r'] == 7


class TestGenerate:
    def test_al_config_generates(self):
        versions = generate_bibd(11, 4, 11, n_versions=11, seed=42)
        assert len(versions) == 11
        for v in versions:
            assert len(v) == 11
            for task in v:
                assert len(task) == 4

    def test_all_versions_valid(self):
        versions = generate_bibd(11, 4, 11, n_versions=11, seed=42)
        for i, v in enumerate(versions):
            validate_bibd(v, 11, 4, 11)  # raises if invalid

    def test_versions_differ(self):
        versions = generate_bibd(11, 4, 11, n_versions=11, seed=42)
        # Not all versions should be identical
        unique = set(
            tuple(tuple(task) for task in sorted(map(sorted, v)))
            for v in versions
        )
        assert len(set(tuple(sorted(v[0])) for v in versions)) > 1

    def test_seed_reproducible(self):
        v1 = generate_bibd(11, 4, 11, n_versions=3, seed=99)
        v2 = generate_bibd(11, 4, 11, n_versions=3, seed=99)
        assert v1 == v2

    def test_different_seed_different_result(self):
        v1 = generate_bibd(11, 4, 11, n_versions=1, seed=1)
        v2 = generate_bibd(11, 4, 11, n_versions=1, seed=2)
        assert v1 != v2

    def test_7_item_config(self):
        versions = generate_bibd(7, 3, 7, n_versions=7, seed=42)
        assert len(versions) == 7
        for v in versions:
            validate_bibd(v, 7, 3, 7)

    def test_infeasible_raises(self):
        with pytest.raises(ValueError, match="not feasible"):
            generate_bibd(10, 4, 11)


class TestValidate:
    def test_valid_design_passes(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        validate_bibd(versions[0], 11, 4, 11)  # should not raise

    def test_wrong_task_count(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        with pytest.raises(ValueError, match="tasks"):
            validate_bibd(versions[0][:10], 11, 4, 11)

    def test_wrong_items_per_task(self):
        bad = [[1, 2, 3]] * 11  # 3 items not 4
        with pytest.raises(ValueError):
            validate_bibd(bad, 11, 4, 11)

    def test_duplicate_item_in_task(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        bad = [task[:] for task in versions[0]]
        bad[0] = [1, 1, 2, 3]  # duplicate
        with pytest.raises(ValueError, match="duplicate"):
            validate_bibd(bad, 11, 4, 11)

    def test_item_out_of_range(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        bad = [task[:] for task in versions[0]]
        bad[0] = [1, 2, 3, 12]  # 12 > n_items=11
        with pytest.raises(ValueError, match="out of range"):
            validate_bibd(bad, 11, 4, 11)

    def test_unbalanced_appearances(self):
        # Manually construct an unbalanced design
        bad = [
            [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4],
            [5, 6, 7, 8], [5, 6, 7, 8], [5, 6, 7, 8], [5, 6, 7, 8],
            [9, 10, 11, 1], [9, 10, 11, 2], [9, 10, 11, 3],
        ]
        with pytest.raises(ValueError, match="balanced"):
            validate_bibd(bad, 11, 4, 11)


class TestBalance:
    """Verify statistical properties of generated designs."""

    def test_each_item_appears_r_times(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        for v in versions:
            counts = {i: 0 for i in range(1, 12)}
            for task in v:
                for item in task:
                    counts[item] += 1
            assert all(c == 4 for c in counts.values()), \
                f"Item appearances not equal: {counts}"

    def test_pair_cooccurrence_deviation_le_1(self):
        """For approximate designs, pairs co-occur at most 1 apart."""
        versions = generate_bibd(11, 4, 11, seed=42)
        for v_idx, v in enumerate(versions):
            pair_counts = {}
            for task in v:
                for a, b in itertools.combinations(sorted(task), 2):
                    pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
            assert len(pair_counts) == 55, \
                f"Version {v_idx}: only {len(pair_counts)} of 55 pairs observed"
            counts = list(pair_counts.values())
            spread = max(counts) - min(counts)
            assert spread <= 1, \
                f"Version {v_idx}: pair spread={spread}, expected ≤ 1"

    def test_strict_bibd_exact_pair_balance(self):
        """For strict BIBD configs, every pair co-occurs exactly λ times."""
        versions = generate_bibd(7, 3, 7, seed=42)
        for v in versions:
            pair_counts = {}
            for task in v:
                for a, b in itertools.combinations(sorted(task), 2):
                    pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
            assert all(c == 1 for c in pair_counts.values())

    def test_versions_collectively_balanced(self):
        """Each item appears r times in every version."""
        n_versions = 11
        versions = generate_bibd(11, 4, 11, n_versions=n_versions, seed=42)
        for v_idx, v in enumerate(versions):
            counts = {item: 0 for item in range(1, 12)}
            for task in v:
                for item in task:
                    counts[item] += 1
            assert all(c == 4 for c in counts.values())


class TestStudyConfig:
    AL_CONFIG = {
        'msg_maxdiff': {
            'n_items': 11,
            'items_per_task': 4,
            'n_tasks': 11,
        },
        'bibd_specs': {
            'AL_MSG_MAXDIFF': {
                'n_items': 11,
                'items_per_task': 4,
                'n_tasks': 11,
                'bibd_file': 'AL_MSG_Design.dat',
            }
        }
    }

    def test_bibd_for_study_al(self):
        result = bibd_for_study(self.AL_CONFIG, n_versions=11, seed=42)
        assert result['n_items'] == 11
        assert result['items_per_task'] == 4
        assert result['n_tasks'] == 11
        assert result['r'] == 4
        assert abs(result['lambda'] - 1.2) < 0.001
        assert len(result['versions']) == 11

    def test_all_versions_valid(self):
        result = bibd_for_study(self.AL_CONFIG, n_versions=11, seed=42)
        for v in result['versions']:
            validate_bibd(v, 11, 4, 11)

    def test_different_config(self):
        # 7,3,7 is a strict BIBD (Fano plane)
        config = {
            'msg_maxdiff': {'n_items': 7, 'items_per_task': 3, 'n_tasks': 7},
            'bibd_specs': {}
        }
        result = bibd_for_study(config, n_versions=5, seed=42)
        assert result['n_items'] == 7
        assert result['strict_bibd'] == True
        for v in result['versions']:
            validate_bibd(v, 7, 3, 7)


class TestFormatDat:
    def test_format_output(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        dat = format_design_dat(versions[0], version=1)
        lines = dat.strip().split('\n')
        assert lines[0].startswith('#')
        assert len(lines) == 12  # 1 header + 11 tasks
        for line in lines[1:]:
            items = list(map(int, line.split()))
            assert len(items) == 4

    def test_all_versions_formattable(self):
        versions = generate_bibd(11, 4, 11, seed=42)
        for i, v in enumerate(versions):
            dat = format_design_dat(v, version=i + 1)
            assert len(dat) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
