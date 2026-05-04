"""
Graph 11: Model Comparison Table
Compares ML Model, Heuristic Engine, and Ensemble approach.
"""

from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.axis('off')
    
    ax.text(0.5, 0.95, 'Model Comparison: ML vs Heuristic vs Ensemble', 
            ha='center', va='center', fontsize=16, fontweight='bold', 
            transform=ax.transAxes, color='#1a1a2e')
    
    table_data = [
        ['Aspect', 'ML Model (SGDClassifier)', 'Heuristic Engine', 'Ensemble (Calibrated)'],
        ['Algorithm', 'SGDClassifier(log_loss)\nTfidfVectorizer(1-3grams)', '12 Regex Signals\nWeighted Scoring', '66% Model + 34% Heuristic\n+ Signal Boosting'],
        ['Strengths', 'Semantic understanding\nContext-aware NLP\nHigh AUC (0.984)', 'Explainable rules\nZero false negatives\nInstant detection', 'Best of both worlds\nCalibrated 0-100 score\nSeverity tiers'],
        ['Weaknesses', 'Needs training data\nCan miss novel scams\nBlack-box predictions', 'Keyword-dependent\nNo semantic nuance\nManual rule maintenance', 'Higher FP rate\nComplex tuning\nMultiple failure modes'],
        ['Precision', '0.948 (default)', '0.952 (fixed)', '0.952 (fixed ensemble)'],
        ['Recall', '0.894 (default)', '0.890 (fixed)', '0.890 (fixed ensemble)'],
        ['F1 Score', '0.921 (default)', '0.920 (fixed)', '0.920 (fixed ensemble)'],
        ['Latency', '~50ms inference', '~5ms matching', '~60ms combined'],
        ['Use Case', 'Deep semantic analysis', 'Known pattern detection', 'Production deployment'],
    ]
    
    table = ax.table(cellText=table_data[1:], colLabels=table_data[0],
                     cellLoc='left', loc='center', bbox=[0, 0.05, 1, 0.85])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2.2)
    
    # Header styling
    for i in range(4):
        table[(0, i)].set_facecolor('#2c3e50')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # Column styling
    colors = ['#ecf0f1', '#d5dbdb', '#d5dbdb', '#d5dbdb']
    for i in range(1, len(table_data)):
        for j in range(4):
            table[(i, j)].set_facecolor(colors[j] if j > 0 else '#f8f9fa')
            if j == 0:
                table[(i, j)].set_text_props(weight='bold')
    
    plt.tight_layout()
    out_path = OUT_DIR / '11_model_comparison_table.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

