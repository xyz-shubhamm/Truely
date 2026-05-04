"""
Graph 02: ROC Curve and Precision-Recall Curve
Generated from validation data using the trained model pipeline.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc, precision_recall_curve, average_precision_score
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / 'model'))
MODEL_PATH = ROOT / 'artifacts' / 'personal_job_model.pkl'
DATA_CANDIDATES = [
    ROOT / 'model' / 'cleaned_fake_job_postings_shreya.csv',
    ROOT / 'model' / 'fake_job_postings.csv',
]
OUT_DIR = Path(__file__).resolve().parent / 'outputs'
OUT_DIR.mkdir(exist_ok=True)

TEXT_FIELDS = ['title', 'company_profile', 'description']

def _load_dataset(path: Path):
    df = pd.read_csv(path)
    for bad_col in ('\x85', 'Unnamed: 0'):
        if bad_col in df.columns:
            df = df.drop(columns=[bad_col])
    if 'fraudulent' not in df.columns:
        raise ValueError(f"Missing target in {path}")
    available = [c for c in TEXT_FIELDS if c in df.columns]
    df['combined_text'] = df[available].fillna('').astype(str).agg(' '.join, axis=1).str.lower()
    df = df[df['combined_text'].str.split().str.len() >= 5]
    return df[['combined_text', 'fraudulent']].copy()

def main():
    frames = []
    for path in DATA_CANDIDATES:
        if path.exists():
            frames.append(_load_dataset(path))
    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
    
    X = df['combined_text'].values
    y = df['fraudulent'].astype(int).values
    
    _, X_valid, _, y_valid = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    model = joblib.load(MODEL_PATH)
    y_score = model.predict_proba(X_valid)[:, 1]
    
    fpr, tpr, _ = roc_curve(y_valid, y_score)
    roc_auc = auc(fpr, tpr)
    
    precision, recall, _ = precision_recall_curve(y_valid, y_score)
    avg_precision = average_precision_score(y_valid, y_score)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # ROC
    axes[0].plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC Curve (AUC = {roc_auc:.4f})')
    axes[0].plot([0, 1], [0, 1], color='navy', lw=1, linestyle='--', label='Random Classifier')
    axes[0].set_xlim([0.0, 1.0])
    axes[0].set_ylim([0.0, 1.05])
    axes[0].set_xlabel('False Positive Rate', fontsize=11)
    axes[0].set_ylabel('True Positive Rate (Recall)', fontsize=11)
    axes[0].set_title('ROC Curve', fontsize=13, fontweight='bold')
    axes[0].legend(loc='lower right')
    axes[0].grid(True, alpha=0.3)
    
    # PR
    axes[1].plot(recall, precision, color='purple', lw=2, label=f'PR Curve (AP = {avg_precision:.4f})')
    baseline = (y_valid == 1).sum() / len(y_valid)
    axes[1].axhline(y=baseline, color='gray', linestyle='--', label=f'Baseline ({baseline:.3f})')
    axes[1].set_xlabel('Recall', fontsize=11)
    axes[1].set_ylabel('Precision', fontsize=11)
    axes[1].set_title('Precision-Recall Curve', fontsize=13, fontweight='bold')
    axes[1].legend(loc='lower left')
    axes[1].grid(True, alpha=0.3)
    
    fig.suptitle('Model Performance Curves (Validation Set)', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '02_roc_pr_curves.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

