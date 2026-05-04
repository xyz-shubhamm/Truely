"""
Graph 03: Validation Curves - Threshold vs Metrics
Shows how F1, Precision, Recall, and Accuracy change across probability thresholds.
Fixed threshold at 0.52 is marked.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
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
FIXED_THRESHOLD = 0.52

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
    
    thresholds = np.linspace(0.001, 0.99, 200)
    
    f1s = []
    precisions = []
    recalls = []
    accuracies = []
    
    for t in thresholds:
        y_pred = (y_score >= t).astype(int)
        f1s.append(f1_score(y_valid, y_pred, zero_division=0))
        precisions.append(precision_score(y_valid, y_pred, zero_division=0))
        recalls.append(recall_score(y_valid, y_pred, zero_division=0))
        accuracies.append(accuracy_score(y_valid, y_pred))
    
    # Compute metrics at fixed threshold
    y_pred_fixed = (y_score >= FIXED_THRESHOLD).astype(int)
    fixed_f1 = f1_score(y_valid, y_pred_fixed, zero_division=0)
    fixed_precision = precision_score(y_valid, y_pred_fixed, zero_division=0)
    fixed_recall = recall_score(y_valid, y_pred_fixed, zero_division=0)
    fixed_accuracy = accuracy_score(y_valid, y_pred_fixed)
    fixed_metrics = {
        'F1 Score': fixed_f1,
        'Precision': fixed_precision,
        'Recall': fixed_recall,
        'Accuracy': fixed_accuracy,
    }
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    metrics_data = [
        (f1s, 'F1 Score', 'F1 Score', 'green'),
        (precisions, 'Precision', 'Precision', 'blue'),
        (recalls, 'Recall', 'Recall', 'red'),
        (accuracies, 'Accuracy', 'Accuracy', 'orange')
    ]
    
    metric_names = ['F1 Score', 'Precision', 'Recall', 'Accuracy']
    
    for ax, (values, title, ylabel, color) in zip(axes.flatten(), metrics_data):
        ax.plot(thresholds, values, color=color, lw=2)
        ax.set_xlabel('Probability Threshold', fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)
        
        # Mark max point
        max_idx = np.argmax(values)
        ax.axvline(x=thresholds[max_idx], color='black', linestyle='--', alpha=0.5)
        ax.scatter([thresholds[max_idx]], [values[max_idx]], color='black', zorder=5)
        ax.annotate(f'{values[max_idx]:.3f} @ {thresholds[max_idx]:.3f}', 
                    xy=(thresholds[max_idx], values[max_idx]), 
                    xytext=(thresholds[max_idx]+0.05, values[max_idx]-0.05),
                    fontsize=9)
        
        # Mark fixed threshold
        metric_name = metric_names[metrics_data.index((values, title, ylabel, color))]
        fixed_val = fixed_metrics[metric_name]
        ax.axvline(x=FIXED_THRESHOLD, color='purple', linestyle='-.', alpha=0.7, lw=2, label=f'Fixed (0.52): {fixed_val:.3f}')
        ax.scatter([FIXED_THRESHOLD], [fixed_val], color='purple', zorder=5, s=80, marker='D')
        ax.legend(fontsize=8, loc='best')
    
    fig.suptitle('Validation Curves: Metrics vs Probability Threshold (Fixed @ 0.52)', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    out_path = OUT_DIR / '03_threshold_validation_curves.png'
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f'Saved: {out_path}')
    plt.close()

if __name__ == '__main__':
    main()

