"""
Graph 05: Failure Analysis
Breakdown of False Positives vs False Negatives and error magnitude distribution.
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
SUMMARY_PATH = ROOT / 'artifacts' / 'top_100_failure_cases_summary.json'
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    with open(SUMMARY_PATH, 'r', encoding='utf-8') as f:
        summary = json.load(f)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Pie chart: FP vs FN
    labels = ['False Positives', 'False Negatives']
    sizes = [summary['false_positive_count'], summary['false_negative_count']]
    colors = ['#ff9999', '#66b3ff']
    explode = (0.05, 0.1)
    
    axes[0].pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
                shadow=True, startangle=90, textprops={'fontsize': 11})
    axes[0].set_title(f'Error Type Distribution\nTotal Errors: {summary["total_errors"]}', 
                      fontsize=13, fontweight='bold')
    
    # Bar chart: Total vs Errors
    categories = ['Total Rows', 'Total Errors', 'Top 100 Analyzed']
    values = [summary['total_rows'], summary['total_errors'], summary['top_100_count']]
    bars = axes[1].bar(categories, values, color=['#2ca02c', '#d62728', '#ff7f0e'], edgecolor='black')
    axes[1].set_ylabel('Count', fontsize=11)
    axes[1].set_title('Dataset vs Error Overview', fontsize=13, fontweight='bold')
    axes[1].grid(True, axis='y', alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        axes[1].annotate(f'{int(height):,}', xy=(bar.get_x() + bar.get_width() / 2, height),
                         xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=10)
    
    fig.suptitle('Failure Analysis: Model Error Breakdown', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '05_failure_analysis.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

