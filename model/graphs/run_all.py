"""
Master runner: Executes all graph generation scripts sequentially.
Usage: python model/graphs/run_all.py
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

GRAPH_DIR = Path(__file__).resolve().parent

scripts = [
    '01_confusion_matrix.py',
    '02_roc_pr_curves.py',
    '03_threshold_validation_curves.py',
    '04_metrics_comparison.py',
    '05_failure_analysis.py',
    '06_edge_case_testing.py',
    '07_autonomous_correction.py',
    '08_heuristic_signals.py',
    '09_system_architecture.py',
    '10_data_flow.py',
    '11_model_comparison_table.py',
    '12_overall_summary.py',
]

def main():
    print('=' * 60)
    print('CheckMate Graph Generation Pipeline')
    print('=' * 60)
    
    success = 0
    failed = 0
    
    for script in scripts:
        path = GRAPH_DIR / script
        if not path.exists():
            print(f'\n[SKIP] {script} not found')
            failed += 1
            continue
        
        print(f'\n[RUNNING] {script} ...')
        try:
            result = subprocess.run(
                [sys.executable, str(path)],
                cwd=str(GRAPH_DIR),
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print(f'[SUCCESS] {script}')
                if result.stdout:
                    print(result.stdout.strip())
                success += 1
            else:
                print(f'[FAILED] {script} (exit {result.returncode})')
                if result.stderr:
                    print(result.stderr.strip()[:500])
                failed += 1
        except Exception as exc:
            print(f'[ERROR] {script}: {exc}')
            failed += 1
    
    print('\n' + '=' * 60)
    print(f'Complete: {success} succeeded, {failed} failed')
    print(f'Output directory: {GRAPH_DIR / "outputs"}')
    print('=' * 60)
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    raise SystemExit(main())

