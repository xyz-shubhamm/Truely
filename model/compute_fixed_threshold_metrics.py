"""
Compute fixed-threshold (0.52) metrics and inject into personal_model_metrics.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

MODEL_PATH = PROJECT_ROOT / 'artifacts' / 'personal_job_model.pkl'
METRICS_PATH = PROJECT_ROOT / 'artifacts' / 'personal_model_metrics.json'

DATA_CANDIDATES = [
    ROOT / 'cleaned_fake_job_postings_shreya.csv',
    ROOT / 'fake_job_postings.csv',
]

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
    print('[1] Loading datasets...')
    frames = []
    for path in DATA_CANDIDATES:
        if path.exists():
            frames.append(_load_dataset(path))
    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)

    X = df['combined_text'].values
    y = df['fraudulent'].astype(int).values

    print('[2] Train/validation split...')
    _, X_valid, _, y_valid = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print('[3] Loading model...')
    model = joblib.load(MODEL_PATH)
    proba = model.predict_proba(X_valid)[:, 1]

    print(f'[4] Computing metrics at fixed threshold {FIXED_THRESHOLD}...')
    y_pred_fixed = (proba >= FIXED_THRESHOLD).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_valid, y_pred_fixed).ravel()

    validation_fixed = {
        'accuracy': float(accuracy_score(y_valid, y_pred_fixed)),
        'f1': float(f1_score(y_valid, y_pred_fixed, zero_division=0)),
        'precision': float(precision_score(y_valid, y_pred_fixed, zero_division=0)),
        'recall': float(recall_score(y_valid, y_pred_fixed, zero_division=0)),
        'confusion_matrix': {
            'tn': int(tn),
            'fp': int(fp),
            'fn': int(fn),
            'tp': int(tp),
        },
    }

    print(f'  Accuracy:  {validation_fixed["accuracy"]:.4f}')
    print(f'  F1:        {validation_fixed["f1"]:.4f}')
    print(f'  Precision: {validation_fixed["precision"]:.4f}')
    print(f'  Recall:    {validation_fixed["recall"]:.4f}')
    print(f'  CM: TN={tn}, FP={fp}, FN={fn}, TP={tp}')

    print('[5] Updating metrics JSON...')
    with open(METRICS_PATH, 'r', encoding='utf-8') as f:
        metrics = json.load(f)

    metrics['validation_fixed'] = validation_fixed
    metrics['threshold_fixed'] = FIXED_THRESHOLD

    with open(METRICS_PATH, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)

    print(f'  Saved: {METRICS_PATH}')
    print('Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

