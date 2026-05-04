"""
Fast strong training for fake-job detection using all available local data.
Saves the final local model as artifacts/personal_job_model.pkl.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_curve, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline



ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
MODEL_DIR = PROJECT_ROOT / 'artifacts'
MODEL_DIR.mkdir(exist_ok=True)
EXTERNAL_DATA_DIR = ROOT_DIR / 'external_data'
DATA_CANDIDATES = [
    ROOT_DIR / 'cleaned_fake_job_postings_shreya.csv',
    ROOT_DIR / 'fake_job_postings.csv',
]

# Import PaymentFlagAdder and add_payment_flag from feature_utils
from feature_utils import PaymentFlagAdder, add_payment_flag


FINAL_PIPELINE_PATH = MODEL_DIR / 'personal_job_model.pkl'
METRICS_PATH = MODEL_DIR / 'personal_model_metrics.json'
THRESHOLD_PATH = MODEL_DIR / 'fraud_threshold.json'

TEXT_FIELDS = [
    'title',
    'company_profile',
    'description',
]


def _load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    for bad_col in ('\x85', 'Unnamed: 0'):
        if bad_col in df.columns:
            df = df.drop(columns=[bad_col])

    if 'fraudulent' not in df.columns:
        raise ValueError(f"Dataset {path} missing required target column 'fraudulent'.")

    available_text_fields = [col for col in TEXT_FIELDS if col in df.columns]
    if not available_text_fields:
        raise ValueError(f'Dataset {path} has no expected text fields.')

    df['combined_text'] = df[available_text_fields].fillna('').astype(str).agg(' '.join, axis=1).str.lower()
    df = df[df['combined_text'].str.split().str.len() >= 5]
    return df[['combined_text', 'fraudulent']].copy()


def _select_threshold(y_true: np.ndarray, y_score: np.ndarray) -> tuple[float, float, float]:
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    f1_values = (2 * precision * recall) / np.clip(precision + recall, 1e-12, None)
    
    # User specifically requested: "our priority is to detect a wrong thing, even if right job is compromised"
    # So we want to find a threshold that gives >= 0.99 recall, while keeping precision from collapsing to absolute 0.
    recall_for_thresholds = recall[:-1]
    
    # Find all thresholds where recall is at least 0.99
    eligible_indices = np.where(recall_for_thresholds >= 0.99)[0]
    
    if len(eligible_indices) > 0:
        # Among those that give 99% recall, pick the one with the highest F1 (best possible precision)
        best_idx = eligible_indices[np.argmax(f1_values[:-1][eligible_indices])]
    else:
        # Fallback: if 99% recall isn't possible, just maximize recall directly while adding a tiny penalty for low precision
        recall_weighted = (0.1 * precision[:-1]) + (0.9 * recall_for_thresholds)
        best_idx = int(np.argmax(recall_weighted))

    return float(thresholds[best_idx]), float(f1_values[:-1][best_idx]), float(recall_for_thresholds[best_idx])


def main() -> int:
    print('[1] Loading datasets...')
    frames = []
    for path in DATA_CANDIDATES:
        if not path.exists():
            continue
        frame = _load_dataset(path)
        print(f'  - {path.name}: {len(frame):,} rows')
        frames.append(frame)

    if EXTERNAL_DATA_DIR.exists():
        external_paths = sorted(EXTERNAL_DATA_DIR.glob('*.csv'))
        for path in external_paths:
            try:
                frame = _load_dataset(path)
                print(f'  - external/{path.name}: {len(frame):,} rows')
                frames.append(frame)
            except Exception as exc:
                print(f'  - skipped external/{path.name}: {exc}')

    if not frames:
        raise FileNotFoundError('No dataset found to train model.')

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=['combined_text', 'fraudulent']).reset_index(drop=True)

    fraud_count = int((df['fraudulent'] == 1).sum())
    legit_count = int((df['fraudulent'] == 0).sum())
    fraud_ratio = fraud_count / len(df)

    print(f'  Combined unique rows: {len(df):,}')
    print(f'  Fraud class: {fraud_count:,} ({fraud_ratio * 100:.2f}%)')
    print(f'  Legit class: {legit_count:,} ({(1 - fraud_ratio) * 100:.2f}%)')

    X = df['combined_text'].values
    y = df['fraudulent'].astype(int).values

    print('\n[2] Train/validation split...')
    X_train, X_valid, y_train, y_valid = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    print(f'  Train size: {len(X_train):,}')
    print(f'  Valid size: {len(X_valid):,}')

    print('\n[3] Training high-capacity pipeline...')

    # Prepare features
    tfidf = TfidfVectorizer(
        strip_accents='unicode',
        lowercase=True,
        sublinear_tf=True,
        stop_words='english',
        ngram_range=(1, 3),  # Use trigrams
        min_df=2,
        max_df=0.95,
        max_features=30000,
    )
    clf = SGDClassifier(
        loss='log_loss',
        alpha=1e-5,
        max_iter=2500,
        tol=1e-3,
        class_weight={0: 1.0, 1: 12.0},  # More aggressive fraud weight
        random_state=42,
    )
    from sklearn.pipeline import FeatureUnion
    pipeline = Pipeline([
        ('features', FeatureUnion([
            ('tfidf', tfidf),
            ('payment_flag', PaymentFlagAdder()),
        ])),
        ('clf', clf),
    ])
    pipeline.fit(X_train, y_train)

    print('\n[4] Validation metrics...')
    proba = pipeline.predict_proba(X_valid)[:, 1]
    threshold, threshold_f1, threshold_recall = _select_threshold(y_valid, proba)
    y_pred_default = (proba >= 0.5).astype(int)
    y_pred_tuned = (proba >= threshold).astype(int)
    y_pred_fixed = (proba >= 0.52).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_valid, y_pred_tuned).ravel()
    tn_f, fp_f, fn_f, tp_f = confusion_matrix(y_valid, y_pred_fixed).ravel()

    metrics = {
        'dataset_rows': int(len(df)),
        'fraud_ratio': float(fraud_ratio),
        'validation_auc': float(roc_auc_score(y_valid, proba)),
        'threshold_default': 0.5,
        'threshold_selected': float(threshold),
        'threshold_selected_f1': float(threshold_f1),
        'threshold_selected_recall': float(threshold_recall),
        'validation_default': {
            'accuracy': float(accuracy_score(y_valid, y_pred_default)),
            'f1': float(f1_score(y_valid, y_pred_default, zero_division=0)),
            'precision': float(precision_score(y_valid, y_pred_default, zero_division=0)),
            'recall': float(recall_score(y_valid, y_pred_default, zero_division=0)),
        },
        'validation_tuned': {
            'accuracy': float(accuracy_score(y_valid, y_pred_tuned)),
            'f1': float(f1_score(y_valid, y_pred_tuned, zero_division=0)),
            'precision': float(precision_score(y_valid, y_pred_tuned, zero_division=0)),
            'recall': float(recall_score(y_valid, y_pred_tuned, zero_division=0)),
            'confusion_matrix': {
                'tn': int(tn),
                'fp': int(fp),
                'fn': int(fn),
                'tp': int(tp),
            },
        },
        'validation_fixed': {
            'accuracy': float(accuracy_score(y_valid, y_pred_fixed)),
            'f1': float(f1_score(y_valid, y_pred_fixed, zero_division=0)),
            'precision': float(precision_score(y_valid, y_pred_fixed, zero_division=0)),
            'recall': float(recall_score(y_valid, y_pred_fixed, zero_division=0)),
            'confusion_matrix': {
                'tn': int(tn_f),
                'fp': int(fp_f),
                'fn': int(fn_f),
                'tp': int(tp_f),
            },
        },
    }

    print(f"  Validation AUC: {metrics['validation_auc']:.4f}")
    print(f"  Tuned threshold: {threshold:.4f}")
    print(f"  Tuned F1: {metrics['validation_tuned']['f1']:.4f}")
    print(f"  Tuned Recall: {metrics['validation_tuned']['recall']:.4f}")
    print(f"  Fixed threshold: 0.52")
    print(f"  Fixed F1: {metrics['validation_fixed']['f1']:.4f}")
    print(f"  Fixed Recall: {metrics['validation_fixed']['recall']:.4f}")

    print('\n[5] Saving artifacts...')
    joblib.dump(pipeline, FINAL_PIPELINE_PATH)

    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    THRESHOLD_PATH.write_text(
        json.dumps(
            {
                'fraud_risk_threshold_percent': 52.0,
                'selected_probability_threshold': 0.52,
                'selection_objective': 'fixed_production_threshold',
            },
            indent=2,
        ),
        encoding='utf-8',
    )

    print(f'  Saved pipeline: {FINAL_PIPELINE_PATH}')
    print(f'  Saved metrics: {METRICS_PATH}')
    print(f'  Saved threshold: {THRESHOLD_PATH}')

    print('\nTraining complete.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
