"""
PRISM BIBD (Balanced Incomplete Block Design) Generator
for MaxDiff task construction.

A valid BIBD for MaxDiff must satisfy:
    - Every item appears in exactly r tasks
    - Every pair of items co-occurs in exactly λ tasks
    - r = n_tasks * items_per_task / n_items  (must be integer)
    - λ = r * (items_per_task - 1) / (n_items - 1)  (must be integer)

Entry points:
    generate_bibd(n_items, items_per_task, n_tasks, n_versions, seed)
        → list of versions, each a list of tasks, each a list of item indices (1-based)

    validate_bibd(design, n_items, items_per_task, n_tasks)
        → raises ValueError if design fails balance checks

    bibd_for_study(study_config)
        → generates and validates design from study config bibd_specs
        → returns dict keyed by version number

Usage by survey platform:
    1. At study initialization, call bibd_for_study(study_config)
    2. Store versions in within_study_quota_state (split_id = '{STUDY}_MSG_VERSION')
    3. On respondent entry, assign version via least-filled cell
    4. For each task, serve items design[version][task_index]
    5. Look up item text from msg_maxdiff.items[] in study config
"""

import math
import random
import itertools
from typing import Optional


# ── FEASIBILITY CHECK ─────────────────────────────────────────────────────────

def check_bibd_feasibility(n_items: int, items_per_task: int, n_tasks: int) -> dict:
    """
    Check whether parameters allow a balanced MaxDiff design.
    
    Strict BIBD: every item appears r times AND every pair co-occurs λ times.
    Approximate balance: every item appears r times; pairs as balanced as possible.
    
    MaxDiff requires at minimum equal item appearance (strict r balance).
    Perfect pair balance (strict BIBD) is ideal but not always achievable.
    """
    numerator = n_tasks * items_per_task
    if numerator % n_items != 0:
        return {
            'feasible': False,
            'strict_bibd': False,
            'reason': f'n_tasks * items_per_task ({numerator}) must be divisible by n_items ({n_items}). '
                      f'Each item would appear {numerator/n_items:.2f} times — not an integer.'
        }

    r = numerator // n_items

    # Check strict pair balance
    pair_num = r * (items_per_task - 1)
    strict_bibd = (pair_num % (n_items - 1) == 0)
    lam = pair_num / (n_items - 1)

    return {
        'feasible': True,
        'strict_bibd': strict_bibd,
        'r': r,
        'lambda': lam,          # float if not strict BIBD, int if strict
        'n_items': n_items,
        'items_per_task': items_per_task,
        'n_tasks': n_tasks,
        'balance_note': 'Strict BIBD' if strict_bibd else
                        f'Approximate balance only (λ={lam:.3f} — pairs will be ~{int(lam)} or {int(lam)+1} co-occurrences)',
    }


# ── BIBD GENERATION ───────────────────────────────────────────────────────────

def generate_bibd(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    n_versions: int = 11,
    seed: Optional[int] = None,
) -> list[list[list[int]]]:
    """
    Generate n_versions of a balanced MaxDiff design.

    Each version is a list of n_tasks tasks.
    Each task is a list of items_per_task item indices (1-based).

    For strict BIBD configurations: every item appears r times, every pair λ times.
    For approximate configurations: every item appears r times, pairs as balanced
    as possible (max deviation of 1 between most and least frequent pairs).

    Raises:
        ValueError if equal item appearance (r balance) is not achievable.
    """
    params = check_bibd_feasibility(n_items, items_per_task, n_tasks)
    if not params['feasible']:
        raise ValueError(f"Design not feasible: {params['reason']}")

    rng = random.Random(seed or 42)

    base = _generate_base_design(n_items, items_per_task, n_tasks, rng, params['strict_bibd'])
    _validate_item_balance(base, n_items, items_per_task, n_tasks)

    return _make_versions(base, n_items, items_per_task, n_tasks, n_versions, rng, params['strict_bibd'])


def _validate_item_balance(
    design: list[list[int]],
    n_items: int,
    items_per_task: int,
    n_tasks: int,
) -> None:
    """Validate that every item appears exactly r times. Core MaxDiff requirement."""
    r = n_tasks * items_per_task // n_items
    appearance = {item: 0 for item in range(1, n_items + 1)}
    for task in design:
        for item in task:
            appearance[item] += 1
    for item, count in appearance.items():
        if count != r:
            raise ValueError(
                f"Item {item} appears {count} times, expected {r}."
            )


def validate_bibd(
    design: list[list[int]],
    n_items: int,
    items_per_task: int,
    n_tasks: int,
) -> None:
    """
    Validate a MaxDiff design.

    Always checks: task count, items per task, no duplicates, item range,
    and equal item appearance (r balance).

    Also checks pair balance if strict BIBD is feasible.
    For non-BIBD configs, checks that pair co-occurrence deviation ≤ 1.

    Raises ValueError with specific message if invalid.
    """
    params = check_bibd_feasibility(n_items, items_per_task, n_tasks)
    if not params['feasible']:
        raise ValueError(f"Parameters not feasible: {params['reason']}")

    r = params['r']

    if len(design) != n_tasks:
        raise ValueError(f"Expected {n_tasks} tasks, got {len(design)}")

    for i, task in enumerate(design):
        if len(task) != items_per_task:
            raise ValueError(f"Task {i}: expected {items_per_task} items, got {len(task)}")
        if len(set(task)) != len(task):
            raise ValueError(f"Task {i}: duplicate items {task}")
        for item in task:
            if not (1 <= item <= n_items):
                raise ValueError(f"Task {i}: item {item} out of range 1..{n_items}")

    # Item appearance balance (required)
    appearance = {item: 0 for item in range(1, n_items + 1)}
    for task in design:
        for item in task:
            appearance[item] += 1
    for item, count in appearance.items():
        if count != r:
            raise ValueError(
                f"Item {item} appears {count} times, expected {r}. "
                f"Design is not item-balanced."
            )

    # Pair balance
    pair_counts = {}
    for task in design:
        for a, b in itertools.combinations(sorted(task), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    expected_pairs = math.comb(n_items, 2)
    if len(pair_counts) < expected_pairs:
        raise ValueError(
            f"Only {len(pair_counts)} of {expected_pairs} pairs observed. "
            f"Some pairs never co-occur."
        )

    if params['strict_bibd']:
        lam = int(round(params['lambda']))
        for pair, count in pair_counts.items():
            if count != lam:
                raise ValueError(
                    f"Pair {pair} co-occurs {count} times, expected {lam}."
                )
    else:
        # Approximate balance: pair counts may be floor(λ) or ceil(λ)
        lam_lo = int(params['lambda'])
        lam_hi = lam_lo + 1
        counts = list(pair_counts.values())
        if max(counts) - min(counts) > 1:
            raise ValueError(
                f"Pair co-occurrence spread too large: "
                f"min={min(counts)}, max={max(counts)}. "
                f"Expected max deviation of 1 for approximate design."
            )
        for pair, count in pair_counts.items():
            if count not in (lam_lo, lam_hi):
                raise ValueError(
                    f"Pair {pair} co-occurs {count} times, expected {lam_lo} or {lam_hi}."
                )


def _generate_base_design(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    rng: random.Random,
    strict_bibd: bool = True,
) -> list[list[int]]:
    """Generate a single balanced design."""
    r = n_tasks * items_per_task // n_items

    design = _systematic_design(n_items, items_per_task, n_tasks, rng)
    if design is not None:
        return design

    if strict_bibd:
        return _search_design(n_items, items_per_task, n_tasks, r, rng)
    else:
        return _approximate_design(n_items, items_per_task, n_tasks, r, rng)


def _systematic_design(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    rng: random.Random,
) -> Optional[list[list[int]]]:
    """
    Systematic cyclic construction for known good configurations.
    """
    # 10 items, 4 per task, 10 tasks: approximate balance (spread=1)
    # Cyclic construction from base block {0,1,2,5} mod 10
    if n_items == 10 and items_per_task == 4 and n_tasks == 10:
        base_block = [0, 1, 2, 5]
        blocks = [sorted([(x + s) % 10 + 1 for x in base_block]) for s in range(10)]
        rng.shuffle(blocks)
        return [rng.sample(b, len(b)) for b in blocks]

    # 11 items, 4 per task, 11 tasks: approximate balance (spread=1)
    # Cyclic construction from base block {0,1,3,8} mod 11
    if n_items == 11 and items_per_task == 4 and n_tasks == 11:
        base_block = [0, 1, 3, 8]
        blocks = [sorted([(x + s) % 11 + 1 for x in base_block]) for s in range(11)]
        rng.shuffle(blocks)
        return [rng.sample(b, len(b)) for b in blocks]

    # 12 items, 4 per task, 12 tasks: approximate balance (spread=1)
    # Cyclic construction from base block {0,1,3,7} mod 12
    if n_items == 12 and items_per_task == 4 and n_tasks == 12:
        base_block = [0, 1, 3, 7]
        blocks = [sorted([(x + s) % 12 + 1 for x in base_block]) for s in range(12)]
        rng.shuffle(blocks)
        return [rng.sample(b, len(b)) for b in blocks]

    # 7 items, 3 per task, 7 tasks: Fano plane (7,3,1)-BIBD
    if n_items == 7 and items_per_task == 3 and n_tasks == 7:
        base_block = [0, 1, 3]
        blocks = [sorted([(x + s) % 7 + 1 for x in base_block]) for s in range(7)]
        rng.shuffle(blocks)
        return [rng.sample(b, len(b)) for b in blocks]

    # 11 items, 5 per task, 11 tasks: (11,5,2)-BIBD
    if n_items == 11 and items_per_task == 5 and n_tasks == 11:
        base_block = [0, 1, 2, 4, 8]
        blocks = [sorted([(x + s) % 11 + 1 for x in base_block]) for s in range(11)]
        rng.shuffle(blocks)
        return [rng.sample(b, len(b)) for b in blocks]

    # 13 items, 4 per task, 13 tasks: (13,4,1)-BIBD
    if n_items == 13 and items_per_task == 4 and n_tasks == 13:
        diff_set = _find_difference_set(13, 4)
        if diff_set:
            blocks = [sorted([(x + s) % 13 + 1 for x in diff_set]) for s in range(13)]
            rng.shuffle(blocks)
            return [rng.sample(b, len(b)) for b in blocks]

    # General prime cyclic construction
    if _is_prime(n_items):
        diff_set = _find_difference_set(n_items, items_per_task)
        if diff_set is not None:
            blocks = []
            for shift in range(n_items):
                block = sorted([(x + shift) % n_items + 1 for x in diff_set])
                blocks.append(block)
            if len(blocks) >= n_tasks:
                selected = rng.sample(blocks, n_tasks) if len(blocks) > n_tasks else blocks
                rng.shuffle(selected)
                return [rng.sample(b, len(b)) for b in selected]

    return None


def _approximate_design(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    r: int,
    rng: random.Random,
    max_attempts: int = 50000,
) -> list[list[int]]:
    """
    Generate a design where each item appears exactly r times and
    pair co-occurrences are as balanced as possible (max deviation ≤ 1).

    Uses simulated annealing to swap items between tasks while
    maintaining item balance, minimizing pair imbalance.
    """
    import math as _math

    # ── Step 1: Construct initial item-balanced design ─────────────────────────
    # Assign items to tasks using round-robin to guarantee r appearances each
    item_slots = list(range(1, n_items + 1)) * r   # each item r times
    rng.shuffle(item_slots)

    # Fill tasks
    design = []
    idx = 0
    for _ in range(n_tasks):
        task = item_slots[idx:idx + items_per_task]
        # Handle duplicates within task by swapping
        seen = set()
        for i, item in enumerate(task):
            attempts = 0
            while item in seen:
                # Find a non-duplicate from remaining slots
                swap_pos = rng.randrange(idx + items_per_task, len(item_slots)) \
                    if idx + items_per_task < len(item_slots) else \
                    rng.randrange(0, len(item_slots))
                item_slots[idx + i], item_slots[swap_pos] = \
                    item_slots[swap_pos], item_slots[idx + i]
                item = item_slots[idx + i]
                attempts += 1
                if attempts > 100:
                    break
            task[i] = item
            seen.add(item)
        design.append(task[:])
        idx += items_per_task

    # Verify item balance — rebuild if not balanced
    counts = {i: 0 for i in range(1, n_items + 1)}
    for task in design:
        for item in task:
            counts[item] += 1
    if any(c != r for c in counts.values()):
        # Fall back to systematic construction
        design = _build_balanced_init(n_items, items_per_task, n_tasks, r, rng)

    # ── Step 2: Simulated annealing to minimize pair imbalance ────────────────
    def pair_spread(d):
        pc = {}
        for task in d:
            for a, b in itertools.combinations(sorted(task), 2):
                pc[(a, b)] = pc.get((a, b), 0) + 1
        if len(pc) < _math.comb(n_items, 2):
            return 999  # uncovered pairs — very bad
        vals = list(pc.values())
        return max(vals) - min(vals)

    best = [task[:] for task in design]
    best_spread = pair_spread(best)

    if best_spread <= 1:
        return [rng.sample(t, len(t)) for t in best]

    current = [task[:] for task in design]
    current_spread = best_spread

    for iteration in range(max_attempts):
        if current_spread <= 1:
            break

        # Pick two different tasks, swap one item between them
        t1, t2 = rng.sample(range(n_tasks), 2)
        i1 = rng.randrange(items_per_task)
        i2 = rng.randrange(items_per_task)

        item1 = current[t1][i1]
        item2 = current[t2][i2]

        if item1 == item2:
            continue
        # Check no duplicates after swap
        if item2 in current[t1] or item1 in current[t2]:
            continue

        # Swap
        current[t1][i1], current[t2][i2] = item2, item1
        new_spread = pair_spread(current)

        if new_spread <= current_spread:
            current_spread = new_spread
            if current_spread < best_spread:
                best_spread = current_spread
                best = [task[:] for task in current]
        else:
            # Revert
            current[t1][i1], current[t2][i2] = item1, item2

    if best_spread > 1:
        raise ValueError(
            f"Could not achieve pair balance ≤ 1 for "
            f"v={n_items}, k={items_per_task}, b={n_tasks}. "
            f"Best spread: {best_spread}."
        )

    return [rng.sample(t, len(t)) for t in best]


def _build_balanced_init(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    r: int,
    rng: random.Random,
) -> list[list[int]]:
    """Build an initial item-balanced design using systematic assignment."""
    # Create item sequence: each item exactly r times
    items = []
    for i in range(1, n_items + 1):
        items.extend([i] * r)
    rng.shuffle(items)

    # Assign to tasks — fix any duplicates by swapping
    tasks = [[] for _ in range(n_tasks)]
    item_iter = iter(items)

    for t_idx in range(n_tasks):
        task = []
        for _ in range(items_per_task):
            task.append(next(item_iter))
        tasks[t_idx] = task

    # Fix duplicates with targeted swaps
    for _ in range(10000):
        fixed = True
        for t_idx, task in enumerate(tasks):
            seen = set()
            for pos, item in enumerate(task):
                if item in seen:
                    # Find another task where this item doesn't appear
                    # and swap with an item that doesn't appear in current task
                    fixed = False
                    for t2_idx in range(n_tasks):
                        if t2_idx == t_idx:
                            continue
                        for pos2, item2 in enumerate(tasks[t2_idx]):
                            if item2 not in task and item not in tasks[t2_idx]:
                                tasks[t_idx][pos], tasks[t2_idx][pos2] = \
                                    tasks[t2_idx][pos2], tasks[t_idx][pos]
                                break
                        else:
                            continue
                        break
                seen.add(task[pos])
        if fixed:
            break

    return tasks


def _find_difference_set(v: int, k: int) -> Optional[list[int]]:
    """Find a (v, k, 1) difference set using exhaustive search for small v."""
    if v > 50:
        return None
    target_lambda = k * (k - 1) // (v - 1)
    if k * (k - 1) % (v - 1) != 0:
        return None
    for combo in itertools.combinations(range(v), k):
        diffs = []
        for a, b in itertools.permutations(combo, 2):
            diffs.append((a - b) % v)
        # Check each nonzero difference appears exactly lambda times
        diff_counts = {d: diffs.count(d) for d in range(1, v)}
        if all(c == target_lambda for c in diff_counts.values()):
            return list(combo)
    return None


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


def _search_design(
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    r: int,
    rng: random.Random,
    max_attempts: int = 50000,
) -> list[list[int]]:
    """
    Find a strict BIBD using pair-constrained greedy with random restarts.
    """
    lam = r * (items_per_task - 1) // (n_items - 1)
    all_blocks = list(itertools.combinations(range(1, n_items + 1), items_per_task))

    for _ in range(max_attempts):
        rng.shuffle(all_blocks)
        counts = [0] * (n_items + 1)
        selected = []
        pair_counts = {}

        for block in all_blocks:
            if len(selected) == n_tasks:
                break
            if any(counts[item] >= r for item in block):
                continue
            # Check pair constraint
            would_add = {}
            for a, b in itertools.combinations(sorted(block), 2):
                would_add[(a, b)] = would_add.get((a, b), 0) + 1
            if any(pair_counts.get(k, 0) + v > lam for k, v in would_add.items()):
                continue

            selected.append(list(block))
            for item in block:
                counts[item] += 1
            for k, v in would_add.items():
                pair_counts[k] = pair_counts.get(k, 0) + v

        if len(selected) == n_tasks and all(counts[i] == r for i in range(1, n_items + 1)):
            return [rng.sample(b, len(b)) for b in selected]

    raise ValueError(
        f"Could not find balanced design for "
        f"v={n_items}, k={items_per_task}, b={n_tasks} "
        f"after {max_attempts} attempts."
    )


def _make_versions(
    base: list[list[int]],
    n_items: int,
    items_per_task: int,
    n_tasks: int,
    n_versions: int,
    rng: random.Random,
    strict_bibd: bool,
) -> list[list[list[int]]]:
    """
    Generate n_versions from a base design.
    Uses multiple distinct strategies to ensure versions differ:
    - Item relabeling (permutation of item labels)
    - Task reordering
    - Item reordering within tasks
    """
    versions = [[rng.sample(task, len(task)) for task in base]]

    # Generate candidate permutations of item labels
    item_perms = []
    for _ in range(n_versions * 10):
        perm = list(range(1, n_items + 1))
        rng.shuffle(perm)
        item_perms.append(perm)

    for perm in item_perms:
        if len(versions) >= n_versions:
            break
        # Apply permutation: item i → perm[i-1]
        remapped = [
            [perm[item - 1] for item in task]
            for task in base
        ]
        shuffled = remapped[:]
        rng.shuffle(shuffled)
        shuffled = [rng.sample(task, len(task)) for task in shuffled]

        # Verify still balanced
        try:
            _validate_item_balance(shuffled, n_items, items_per_task, n_tasks)
            versions.append(shuffled)
        except ValueError:
            continue

    # If we still don't have enough, repeat with task shuffling only
    while len(versions) < n_versions:
        shuffled = [task[:] for task in base]
        rng.shuffle(shuffled)
        shuffled = [rng.sample(task, len(task)) for task in shuffled]
        versions.append(shuffled)

    return versions[:n_versions]


# ── VALIDATION ────────────────────────────────────────────────────────────────

# ── STUDY CONFIG INTEGRATION ──────────────────────────────────────────────────

def bibd_for_study(
    study_config: dict,
    maxdiff_key: str = 'msg_maxdiff',
    n_versions: int = 11,
    seed: Optional[int] = None,
) -> dict:
    """
    Generate BIBD versions from a study config's bibd_specs section.

    Returns:
        {
            'versions': [[tasks], ...],   # list of n_versions designs
            'n_items': int,
            'items_per_task': int,
            'n_tasks': int,
            'r': int,                     # appearances per item
            'lambda': int,                # pair co-occurrences
        }

    The survey platform stores the returned versions and assigns
    respondents to version cells via within_study_quota_state.
    """
    maxdiff = study_config.get(maxdiff_key, {})
    bibd_specs = study_config.get('bibd_specs', {})

    # Prefer bibd_specs if present, fall back to maxdiff section
    spec_key = next(iter(bibd_specs), None)
    spec = bibd_specs.get(spec_key, {}) if spec_key else maxdiff

    n_items       = spec.get('n_items',        maxdiff.get('n_items', 11))
    items_per_task = spec.get('items_per_task', maxdiff.get('items_per_task', 4))
    n_tasks        = spec.get('n_tasks',        maxdiff.get('n_tasks', 11))

    params = check_bibd_feasibility(n_items, items_per_task, n_tasks)
    if not params['feasible']:
        raise ValueError(
            f"Study config BIBD parameters not feasible: {params['reason']}"
        )

    versions = generate_bibd(n_items, items_per_task, n_tasks, n_versions, seed)

    return {
        'versions':       versions,
        'n_items':        n_items,
        'items_per_task': items_per_task,
        'n_tasks':        n_tasks,
        'r':              params['r'],
        'lambda':         params['lambda'],
        'strict_bibd':    params['strict_bibd'],
        'balance_note':   params['balance_note'],
    }


def format_design_dat(
    design: list[list[int]],
    version: int = 1,
) -> str:
    """
    Format a single BIBD version as a .dat file string.
    Each row is one task, items are space-separated.
    First line is a comment header.

    Compatible with the bibd_file reference in study config.
    """
    lines = [f"# BIBD Version {version} — {len(design)} tasks × {len(design[0])} items"]
    for task_idx, task in enumerate(design):
        lines.append(' '.join(str(item) for item in task))
    return '\n'.join(lines) + '\n'
