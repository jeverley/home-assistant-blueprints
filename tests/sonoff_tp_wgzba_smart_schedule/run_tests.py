"""Run the blueprint's simulator tests.

    python3 tests/sonoff_tp_wgzba_smart_schedule/run_tests.py [-k text] [--blueprint path]

Runs every test_* function in the test_*.py files next to this one and
reports each as passed or failed. A test fails on a failed assertion or any
error, so a broken blueprint or simulator never passes silently. Exits with
1 if any test failed. --blueprint runs the tests against another copy of the
blueprint (for example an older version from git, to compare).
"""
import argparse
import importlib.util
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('-k', default='', help='only tests whose name contains this')
    p.add_argument('--blueprint', help='the blueprint file to test (default: the one in the repository)')
    p.add_argument('-v', action='store_true', help='show the traceback of each failure')
    args = p.parse_args()
    sys.path.insert(0, str(HERE))
    import sim
    if args.blueprint:
        sim.BLUEPRINT = Path(args.blueprint).resolve()
        sim.World.__init__.__defaults__ = tuple(
            sim.BLUEPRINT if isinstance(d, Path) else d for d in sim.World.__init__.__defaults__)
    failed = passed = 0
    t0 = time.time()
    for path in sorted(HERE.glob('test_*.py')):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for name in [n for n in dir(mod) if n.startswith('test_') and args.k in n]:
            start = time.time()
            try:
                getattr(mod, name)()
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f'FAIL  {path.stem}.{name} ({time.time() - start:.1f}s): {type(e).__name__}: {e}'[:300])
                if args.v:
                    traceback.print_exc()
            else:
                passed += 1
                print(f'ok    {path.stem}.{name} ({time.time() - start:.1f}s)')
    print(f'\n{passed} passed, {failed} failed in {time.time() - t0:.0f}s')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
