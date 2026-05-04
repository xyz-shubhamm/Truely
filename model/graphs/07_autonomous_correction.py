"""
Graph 07: Autonomous Self-Correction Loop
Shows hypothetical error reduction across iterations (based on autonomous_correction.py logic).
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    # Simulated iteration data based on autonomous_correction.py behavior
    # Starting from the fixed threshold confusion matrix: TN=5779, FP=11, FN=27, TP=219
    # Total errors initially = 38
    iterations = [1, 2, 3, 4, 5]
    
    # Simulated error counts after each partial_fit pass on failure cases
    # The loop gives 3 passes per iteration, errors should drop
    total_errors = [38, 32, 27, 23, 20]
    false_positives = [11, 9, 7, 6, 5]
    false_negatives = [27, 23, 20, 17, 15]
    f1_scores = [0.920, 0.925, 0.930, 0.935, 0.940]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Error reduction
    axes[0].plot(iterations, total_errors, marker='o', color='red', lw=2, label='Total Errors')
    axes[0].plot(iterations, false_positives, marker='s', color='orange', lw=2, label='False Positives')
    axes[0].plot(iterations, false_negatives, marker='^', color='blue', lw=2, label='False Negatives')
    axes[0].set_xlabel('Iteration', fontsize=11)
    axes[0].set_ylabel('Error Count', fontsize=11)
    axes[0].set_title('Error Reduction Over Iterations', fontsize=13, fontweight='bold')
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xticks(iterations)
    
    # F1 improvement
    axes[1].plot(iterations, f1_scores, marker='D', color='green', lw=2, label='F1 Score')
    axes[1].set_xlabel('Iteration', fontsize=11)
    axes[1].set_ylabel('F1 Score', fontsize=11)
    axes[1].set_title('F1 Score Improvement', fontsize=13, fontweight='bold')
    axes[1].legend(fontsize=10)
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xticks(iterations)
    axes[1].set_ylim(0.90, 0.95)
    
    fig.suptitle('Autonomous Self-Correction Loop Performance', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '07_autonomous_correction.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

