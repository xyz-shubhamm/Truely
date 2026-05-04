"""
Graph 09: System Architecture Diagram
High-level block diagram of the decoupled client-server model.
"""

from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

def main():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    def draw_box(x, y, w, h, text, color, text_color='white', fontsize=10):
        box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", 
                             facecolor=color, edgecolor='black', linewidth=2)
        ax.add_patch(box)
        ax.text(x + w/2, y + h/2, text, ha='center', va='center', 
                fontsize=fontsize, color=text_color, fontweight='bold', wrap=True)
    
    def draw_arrow(x1, y1, x2, y2, label=''):
        arrow = FancyArrowPatch((x1, y1), (x2, y2),
                                arrowstyle='->', mutation_scale=20, 
                                linewidth=2, color='#333333')
        ax.add_patch(arrow)
        if label:
            mid_x, mid_y = (x1+x2)/2, (y1+y2)/2
            ax.text(mid_x, mid_y+0.2, label, ha='center', va='bottom', 
                    fontsize=9, style='italic', color='#555555',
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.8))
    
    # Title
    ax.text(8, 9.5, 'CheckMate System Architecture', ha='center', va='center',
            fontsize=18, fontweight='bold', color='#1a1a2e')
    
    # Tiers
    # Presentation Tier
    draw_box(1, 6.5, 3.5, 2, 'Presentation Tier\n(React SPA + pdf.js)\nClient-Side Routing\nPDF Text Extraction', '#4e89ae')
    
    # API Gateway
    draw_box(6, 6.5, 3.5, 2, 'API Gateway\n(FastAPI + Uvicorn)\nJWT Validation\nCORS / Auth', '#43658b')
    
    # Service Tier
    draw_box(11, 6.5, 3.5, 2, 'Service Tier\n(ML Engine)\nSGDClassifier\nHeuristic Engine\nEnsemble Scoring', '#ed6663')
    
    # Data Access Layer
    draw_box(6, 3.5, 3.5, 2, 'Data Access Layer\n(SQLAlchemy ORM)\nSchema Compatibility\nQuery Abstraction', '#ffa372')
    
    # Storage Tier
    draw_box(11, 3.5, 3.5, 2, 'Storage Tier\n(Supabase PostgreSQL)\nUser Accounts\nJob Analysis History', '#1b262c')
    
    # Auth Service
    draw_box(1, 3.5, 3.5, 2, 'Auth Service\n(Supabase OAuth)\nGoogle Sign-In\nJWT Token Issuance', '#0f4c75')
    
    # Arrows
    draw_arrow(4.5, 7.5, 6, 7.5, 'HTTPS / JSON')
    draw_arrow(9.5, 7.5, 11, 7.5, 'Clean Text')
    draw_arrow(9.5, 6.5, 9.5, 5.5, 'Risk Score')
    draw_arrow(9.5, 3.5, 11, 3.5, 'Persist')
    draw_arrow(4.5, 4.5, 6, 4.5, 'Verify')
    draw_arrow(2.75, 6.5, 2.75, 5.5, 'Token')
    
    # Legend
    legend_elements = [
        mpatches.Patch(color='#4e89ae', label='Frontend (Presentation)'),
        mpatches.Patch(color='#43658b', label='API Gateway'),
        mpatches.Patch(color='#ed6663', label='ML Service Tier'),
        mpatches.Patch(color='#ffa372', label='Data Access'),
        mpatches.Patch(color='#1b262c', label='Storage'),
        mpatches.Patch(color='#0f4c75', label='Authentication'),
    ]
    ax.legend(handles=legend_elements, loc='lower left', fontsize=10, framealpha=0.9)
    
    plt.tight_layout()
    out_path = OUT_DIR / '09_system_architecture.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

