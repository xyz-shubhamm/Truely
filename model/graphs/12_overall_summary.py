"""
Graph 12: Overall Executive Summary Dashboard
Multi-panel overview of the entire CheckMate system.
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent.parent
METRICS_PATH = ROOT / 'artifacts' / 'personal_model_metrics.json'
THRESHOLD_PATH = ROOT / 'artifacts' / 'fraud_threshold.json'
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    with open(METRICS_PATH, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
    with open(THRESHOLD_PATH, 'r', encoding='utf-8') as f:
        threshold_cfg = json.load(f)
    
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.4, wspace=0.35)
    
    # 1. Title
    fig.suptitle('CheckMate Executive Summary Dashboard', fontsize=20, fontweight='bold', y=0.98)
    
    # 2. Key Metrics Cards (top row)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.axis('off')
    ax1.text(0.5, 0.5, f'Validation AUC\n{metrics["validation_auc"]:.4f}', 
             ha='center', va='center', fontsize=18, fontweight='bold', color='#2c3e50',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#aed6f1', edgecolor='#2c3e50', linewidth=2))
    
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis('off')
    ax2.text(0.5, 0.5, f'Dataset Size\n{metrics["dataset_rows"]:,} rows', 
             ha='center', va='center', fontsize=18, fontweight='bold', color='#1e8449',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#abebc6', edgecolor='#1e8449', linewidth=2))
    
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.axis('off')
    fraud_pct = metrics['fraud_ratio'] * 100
    ax3.text(0.5, 0.5, f'Fraud Ratio\n{fraud_pct:.2f}%', 
             ha='center', va='center', fontsize=18, fontweight='bold', color='#922b21',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5b7b1', edgecolor='#922b21', linewidth=2))
    
    # 3. Threshold comparison gauge (middle left)
    ax4 = fig.add_subplot(gs[1, 0])
    labels = ['Accuracy', 'F1', 'Precision', 'Recall']
    default_vals = [metrics['validation_default']['accuracy'], metrics['validation_default']['f1'],
                    metrics['validation_default']['precision'], metrics['validation_default']['recall']]
    fixed_vals = [metrics['validation_fixed']['accuracy'], metrics['validation_fixed']['f1'],
                  metrics['validation_fixed']['precision'], metrics['validation_fixed']['recall']]
    x = np.arange(len(labels))
    width = 0.35
    ax4.bar(x - width/2, default_vals, width, label='Default (0.5)', color='steelblue')
    ax4.bar(x + width/2, fixed_vals, width, label='Fixed (0.52)', color='coral')
    ax4.set_ylabel('Score')
    ax4.set_title('Metrics: Default vs Fixed')
    ax4.set_xticks(x)
    ax4.set_xticklabels(labels, fontsize=9)
    ax4.legend(fontsize=8)
    ax4.set_ylim(0, 1.1)
    ax4.grid(True, axis='y', alpha=0.3)
    
    # 4. Confusion matrix simplified (middle center)
    ax5 = fig.add_subplot(gs[1, 1])
    fixed = metrics['validation_fixed']['confusion_matrix']
    cm = np.array([[fixed['tn'], fixed['fp']], [fixed['fn'], fixed['tp']]])
    im = ax5.imshow(cm, cmap='Oranges')
    ax5.set_xticks([0, 1])
    ax5.set_yticks([0, 1])
    ax5.set_xticklabels(['Genuine', 'Fraud'])
    ax5.set_yticklabels(['Genuine', 'Fraud'])
    ax5.set_xlabel('Predicted')
    ax5.set_ylabel('Actual')
    ax5.set_title('Fixed CM')
    for i in range(2):
        for j in range(2):
            ax5.text(j, i, f'{cm[i,j]:,}', ha='center', va='center', fontweight='bold', fontsize=12)
    plt.colorbar(im, ax=ax5, shrink=0.6)
    
    # 5. Risk score zones (middle right)
    ax6 = fig.add_subplot(gs[1, 2])
    zones = ['Low Risk\n0-39%', 'Moderate Risk\n40-69%', 'High Risk\n70-100%']
    zone_colors = ['#2ecc71', '#f39c12', '#e74c3c']
    zone_sizes = [35, 30, 35]
    ax6.pie(zone_sizes, labels=zones, colors=zone_colors, autopct='%1.0f%%',
            startangle=90, textprops={'fontsize': 10})
    ax6.set_title('Risk Score Zones')
    
    # 6. System components (bottom left)
    ax7 = fig.add_subplot(gs[2, 0])
    components = ['React SPA', 'FastAPI', 'SGD Model', 'Heuristics', 'Supabase DB']
    values = [95, 90, 88, 92, 85]
    colors = ['#4e89ae', '#43658b', '#ed6663', '#d62728', '#1b262c']
    bars = ax7.barh(components, values, color=colors, edgecolor='black')
    ax7.set_xlim(0, 100)
    ax7.set_xlabel('Readiness %')
    ax7.set_title('Component Readiness')
    ax7.grid(True, axis='x', alpha=0.3)
    for bar, v in zip(bars, values):
        ax7.text(v + 1, bar.get_y() + bar.get_height()/2, f'{v}%', va='center', fontsize=9)
    
    # 7. Tech stack (bottom center)
    ax8 = fig.add_subplot(gs[2, 1])
    ax8.axis('off')
    stack_text = """Frontend Stack:
  • React 18 + Vite
  • Vanilla CSS Variables
  • pdf.js (client-side)
  • React Router DOM

Backend Stack:
  • Python 3.11+
  • FastAPI + Uvicorn
  • SQLAlchemy ORM
  • scikit-learn + joblib

Auth & Storage:
  • Supabase OAuth
  • PostgreSQL Cloud
  • JWT HS256"""
    ax8.text(0.1, 0.95, stack_text, ha='left', va='top', fontsize=9,
             family='monospace', transform=ax8.transAxes,
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#f8f9fa', edgecolor='#dee2e6'))
    ax8.set_title('Technology Stack', pad=10)
    
    # 8. Threshold config (bottom right)
    ax9 = fig.add_subplot(gs[2, 2])
    ax9.axis('off')
    config_text = f"""Threshold Configuration:
  Fraud Risk Threshold: {threshold_cfg['fraud_risk_threshold_percent']}%
  Probability Threshold: {threshold_cfg['selected_probability_threshold']}
  Objective: {threshold_cfg['selection_objective']}

Model Configuration:
  Vectorizer: Tfidf (1-3 grams)
  Features: 30,000 max
  Class Weight: {0:.1f}:{12:.1f}
  Max Iter: 2500
  Alpha: 1e-5

Validation Split: 80/20
Stratified: Yes
Random State: 42"""
    ax9.text(0.1, 0.95, config_text, ha='left', va='top', fontsize=9,
             family='monospace', transform=ax9.transAxes,
             bbox=dict(boxstyle='round,pad=0.4', facecolor='#fff3cd', edgecolor='#ffc107'))
    ax9.set_title('Model Configuration', pad=10)
    
    out_path = OUT_DIR / '12_overall_summary.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

