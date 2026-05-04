"""
Graph 10: End-to-End Data Flow Diagram
Shows the complete request-response lifecycle.
"""

from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    fig, ax = plt.subplots(figsize=(18, 10))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    ax.text(9, 9.5, 'CheckMate End-to-End Data Flow', ha='center', va='center',
            fontsize=18, fontweight='bold', color='#1a1a2e')
    
    def draw_step(x, y, w, h, title, details, color, text_color='white'):
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", 
                             facecolor=color, edgecolor='black', linewidth=1.5)
        ax.add_patch(box)
        ax.text(x + w/2, y + h - 0.25, title, ha='center', va='top',
                fontsize=10, fontweight='bold', color=text_color)
        ax.text(x + w/2, y + h/2 - 0.1, details, ha='center', va='center',
                fontsize=8, color=text_color, wrap=True)
    
    def draw_arrow(x1, y1, x2, y2, label=''):
        arrow = FancyArrowPatch((x1, y1), (x2, y2),
                                arrowstyle='->', mutation_scale=18, 
                                linewidth=1.5, color='#333333')
        ax.add_patch(arrow)
        if label:
            mid_x, mid_y = (x1+x2)/2, (y1+y2)/2
            ax.text(mid_x, mid_y+0.15, label, ha='center', va='bottom', 
                    fontsize=8, style='italic', color='#444444',
                    bbox=dict(boxstyle='round,pad=0.15', facecolor='white', edgecolor='none', alpha=0.85))
    
    # Row 1: User Journey
    draw_step(0.5, 7, 2.5, 1.8, '1. User Landing', 'Homepage CTA\n"Get Started"', '#4e89ae')
    draw_step(3.5, 7, 2.5, 1.8, '2. Google OAuth', '/login → Supabase\nJWT Token Issued', '#0f4c75')
    draw_step(6.5, 7, 2.5, 1.8, '3. Dashboard', '/check-job\nText or PDF Input', '#4e89ae')
    draw_step(9.5, 7, 2.5, 1.8, '4. Submit', 'POST /api/predict\nJSON + Bearer Token', '#43658b')
    draw_step(12.5, 7, 2.5, 1.8, '5. Loading', '1s Minimum Delay\nFrosted Glass Overlay', '#ffa372')
    draw_step(15.5, 7, 2, 1.8, '6. Report', '/report\nRisk Score + Flags', '#ed6663')
    
    # Ar Row 1
    draw_arrow(3, 7.9, 3.5, 7.9)
    draw_arrow(6, 7.9, 6.5, 7.9)
    draw_arrow(9, 7.9, 9.5, 7.9)
    draw_arrow(12, 7.9, 12.5, 7.9)
    draw_arrow(15, 7.9, 15.5, 7.9)
    
    # Row 2: Backend Processing (below)
    draw_step(4, 4, 3, 2.2, 'FastAPI Gateway', 'Validate JWT\nParse Pydantic Model\nCORS Check', '#43658b')
    draw_step(8, 4, 3, 2.2, 'ML Pipeline', 'Tfidf + PaymentFlag\nSGDClassifier\npredict_proba()', '#ed6663')
    draw_step(12, 4, 3, 2.2, 'Heuristic Engine', '12 Regex Signals\nWeighted Scoring\nSignal Array', '#d62728')
    
    # Connector arrows from Step 4 to backend
    draw_arrow(10.75, 7, 10.75, 6.2, 'Request')
    draw_arrow(10.75, 6.2, 5.5, 6.2)
    draw_arrow(5.5, 6.2, 5.5, 6.2)
    
    # Backend internal flow
    draw_arrow(7, 5.1, 8, 5.1, 'Clean Text')
    draw_arrow(11, 5.1, 12, 5.1, 'Probabilities')
    
    # Ensemble + Calibration
    draw_step(8, 1.5, 3, 2, 'Ensemble Calibration', '66% Model + 34% Heuristic\nRisk Score 0-100\nSeverity Tier', '#2ca02c')
    draw_arrow(13.5, 4, 13.5, 3.5, 'Signals')
    draw_arrow(13.5, 3.5, 9.5, 3.5)
    draw_arrow(9.5, 3.5, 9.5, 3.5)
    
    # Persist
    draw_step(13, 1.5, 3, 2, 'Database Write', 'SQLAlchemy ORM\napp_job_analyses\nSupabase PostgreSQL', '#1b262c')
    draw_arrow(11, 2.5, 13, 2.5, 'Result')
    
    # Legend
    legend_elements = [
        mpatches.Patch(color='#4e89ae', label='Frontend'),
        mpatches.Patch(color='#0f4c75', label='Auth'),
        mpatches.Patch(color='#43658b', label='API Gateway'),
        mpatches.Patch(color='#ed6663', label='ML Engine'),
        mpatches.Patch(color='#d62728', label='Heuristics'),
        mpatches.Patch(color='#2ca02c', label='Calibration'),
        mpatches.Patch(color='#1b262c', label='Database'),
    ]
    ax.legend(handles=legend_elements, loc='lower left', fontsize=9, framealpha=0.9, ncol=4)
    
    plt.tight_layout()
    out_path = OUT_DIR / '10_data_flow.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

