"""
Graph 04: Metrics Comparison Bar Chart + Table
Default Threshold (0.5) vs Fixed Threshold (0.52)
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
METRICS_PATH = ROOT / 'artifacts' / 'personal_model_metrics.json'
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    with open(METRICS_PATH, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
    
    default = metrics['validation_default']
    fixed = metrics['validation_fixed']
    
    labels = ['Accuracy', 'F1 Score', 'Precision', 'Recall']
    default_vals = [default['accuracy'], default['f1'], default['precision'], default['recall']]
    fixed_vals = [fixed['accuracy'], fixed['f1'], fixed['precision'], fixed['recall']]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(12, 7))
    bars1 = ax.bar(x - width/2, default_vals, width, label=f'Default (0.5)', color='steelblue', edgecolor='black')
    bars2 = ax.bar(x + width/2, fixed_vals, width, label=f'Fixed (0.52)', color='coral', edgecolor='black')
    
    ax.set_ylabel('Score', fontsize=12)
    ax.set_title('Metrics Comparison: Default vs Fixed Threshold', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=11)
    ax.grid(True, axis='y', alpha=0.3)
    
    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f'{height:.3f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=10)
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f'{height:.3f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=10)
    
    # Add table below
    table_data = [
        ['Metric', 'Default (0.5)', f'Fixed (0.52)'],
        ['Accuracy', f'{default["accuracy"]:.4f}', f'{fixed["accuracy"]:.4f}'],
        ['F1 Score', f'{default["f1"]:.4f}', f'{fixed["f1"]:.4f}'],
        ['Precision', f'{default["precision"]:.4f}', f'{fixed["precision"]:.4f}'],
        ['Recall', f'{default["recall"]:.4f}', f'{fixed["recall"]:.4f}'],
        ['AUC', f'{metrics["validation_auc"]:.4f}', f'{metrics["validation_auc"]:.4f}'],
    ]
    
    table = ax.table(cellText=table_data[1:], colLabels=table_data[0], 
                     cellLoc='center', loc='bottom', bbox=[0, -0.45, 1, 0.3])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    
    # Style header
    for i in range(3):
        table[(0, i)].set_facecolor('#40466e')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.35)
    
    out_path = OUT_DIR / '04_metrics_comparison.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

