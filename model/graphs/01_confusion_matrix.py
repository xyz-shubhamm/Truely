"""
Graph 01: Confusion Matrix Heatmaps
Side-by-side comparison of Default Threshold (0.5) vs Fixed Threshold (0.52)
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path(__file__).resolve().parent.parent.parent
METRICS_PATH = ROOT / 'artifacts' / 'personal_model_metrics.json'
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def load_metrics():
    with open(METRICS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def plot_confusion_matrices():
    metrics = load_metrics()
    
    # Default threshold confusion matrix (estimated from validation metrics)
    # We don't have exact CM for default, so we derive from metrics
    default = metrics['validation_default']
    fixed = metrics['validation_fixed']
    
    # Fixed CM is available directly
    cm_fixed = np.array([
        [fixed['confusion_matrix']['tn'], fixed['confusion_matrix']['fp']],
        [fixed['confusion_matrix']['fn'], fixed['confusion_matrix']['tp']]
    ])
    
    # For default threshold, we estimate from precision/recall
    # precision = TP/(TP+FP), recall = TP/(TP+FN)
    # We know total validation size = 6036 (20% of 30179)
    # From train_model.py output: TN+FP+FN+TP = 6036
    total = 6036
    fraud_total = int(total * metrics['fraud_ratio'])
    legit_total = total - fraud_total
    
    # Default: recall=0.894, precision=0.948
    recall_d = default['recall']
    precision_d = default['precision']
    tp_d = int(fraud_total * recall_d)
    fn_d = fraud_total - tp_d
    fp_d = int(tp_d * (1 - precision_d) / precision_d) if precision_d > 0 else 0
    tn_d = legit_total - fp_d
    
    cm_default = np.array([[tn_d, fp_d], [fn_d, tp_d]])
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    labels = ['Genuine', 'Fraudulent']
    
    # Default
    sns.heatmap(cm_default, annot=True, fmt='d', cmap='Blues', 
                xticklabels=labels, yticklabels=labels, ax=axes[0],
                cbar_kws={'label': 'Count'})
    axes[0].set_title(f'Default Threshold (0.5)\nAcc={default["accuracy"]:.3f} | F1={default["f1"]:.3f} | Rec={default["recall"]:.3f}', 
                      fontsize=12, fontweight='bold')
    axes[0].set_xlabel('Predicted')
    axes[0].set_ylabel('Actual')
    
    # Fixed
    sns.heatmap(cm_fixed, annot=True, fmt='d', cmap='Oranges', 
                xticklabels=labels, yticklabels=labels, ax=axes[1],
                cbar_kws={'label': 'Count'})
    axes[1].set_title(f'Fixed Threshold (0.52)\nAcc={fixed["accuracy"]:.3f} | F1={fixed["f1"]:.3f} | Rec={fixed["recall"]:.3f}', 
                      fontsize=12, fontweight='bold')
    axes[1].set_xlabel('Predicted')
    axes[1].set_ylabel('Actual')
    
    fig.suptitle('Confusion Matrix Comparison: Default vs Fixed Threshold', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '01_confusion_matrix.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    plot_confusion_matrices()

