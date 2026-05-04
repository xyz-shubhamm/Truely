"""
Graph 08: Heuristic Signal Weights and Coverage
Radar/bar chart of the 12 heuristic signals used in the ensemble.
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

# Heuristic signals from ml_service/app.py
SIGNALS = [
    ('Upfront Payment Request', 0.85),
    ('Money Transfer Demand', 0.80),
    ('Sexual/Inappropriate Content', 0.90),
    ('Sensitive Data Collection', 0.75),
    ('Aggressive Earnings Pitch', 0.70),
    ('MLM Recruitment Pattern', 0.65),
    ('Personal Contact Channel', 0.45),
    ('Placeholder Content', 0.85),
    ('Thin Job Detail', 0.35),
    ('Urgency Pressure', 0.30),
    ('Suspicious Reward Language', 0.20),
    ('Cash Lure Payment Pattern', 0.30),
]

def main():
    names = [s[0] for s in SIGNALS]
    weights = [s[1] for s in SIGNALS]
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # Horizontal bar chart
    y_pos = np.arange(len(names))
    colors = plt.cm.RdYlGn_r(np.array(weights))
    bars = axes[0].barh(y_pos, weights, color=colors, edgecolor='black', height=0.6)
    axes[0].set_yticks(y_pos)
    axes[0].set_yticklabels(names, fontsize=9)
    axes[0].invert_yaxis()
    axes[0].set_xlabel('Heuristic Weight', fontsize=11)
    axes[0].set_title('Heuristic Signal Weights', fontsize=13, fontweight='bold')
    axes[0].set_xlim(0, 1.0)
    axes[0].grid(True, axis='x', alpha=0.3)
    
    for bar, w in zip(bars, weights):
        axes[0].text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2, 
                     f'{w:.2f}', va='center', fontsize=9)
    
    # Radar chart (spider plot)
    angles = np.linspace(0, 2 * np.pi, len(names), endpoint=False).tolist()
    weights_radar = weights + [weights[0]]
    angles += angles[:1]
    
    ax2 = plt.subplot(122, polar=True)
    ax2.plot(angles, weights_radar, 'o-', linewidth=2, color='purple')
    ax2.fill(angles, weights_radar, alpha=0.25, color='purple')
    ax2.set_xticks(angles[:-1])
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.0)
    ax2.set_title('Heuristic Coverage Radar', fontsize=13, fontweight='bold', pad=20)
    ax2.grid(True)
    
    fig.suptitle('Heuristic Engine: Signal Weights & Coverage', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '08_heuristic_signals.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

