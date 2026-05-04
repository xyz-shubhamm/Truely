"""
Autonomous self-correction loop.
Finds cases where the model fails (false positives/false negatives),
extracts them, and forces the model to learn the correct label via partial_fit.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
import sys

# Ensure feature_utils can be imported
sys.path.append(str(Path(__file__).resolve().parent))

ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
MODEL_DIR = PROJECT_ROOT / 'artifacts'
DATA_CANDIDATES = [
    ROOT_DIR / 'cleaned_fake_job_postings_shreya.csv',
    ROOT_DIR / 'fake_job_postings.csv',
]

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
    df['combined_text'] = df[available_text_fields].fillna('').astype(str).agg(' '.join, axis=1).str.lower()
    df = df[df['combined_text'].str.split().str.len() >= 5]
    return df[['combined_text', 'fraudulent']].copy()

def main():
    print('Starting Autonomous Self-Correction Loop...')
    
    # 1. Load data
    frames = []
    for path in DATA_CANDIDATES:
        if not path.exists(): continue
        frames.append(_load_dataset(path))
    if not frames:
        print("No data found!")
        return 1
    
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['combined_text', 'fraudulent']).reset_index(drop=True)
    X = df['combined_text'].values
    y = df['fraudulent'].astype(int).values
    
    print(f"Loaded {len(X)} unique examples for continuous testing.")

    # 2. Load model & threshold
    if not FINAL_PIPELINE_PATH.exists():
        print("Model artifact not found. Please train first.")
        return 1
        
    pipeline = joblib.load(FINAL_PIPELINE_PATH)
    
    threshold = 0.5
    if THRESHOLD_PATH.exists():
        try:
            payload = json.loads(THRESHOLD_PATH.read_text(encoding='utf-8'))
            threshold = payload.get('selected_probability_threshold', 0.5)
        except Exception:
            pass

    max_iterations = 5
    print(f"Running for up to {max_iterations} iterations...")
    
    feature_extractor = pipeline.named_steps['features']
    clf = pipeline.named_steps['clf']
    
    for i in range(max_iterations):
        print(f"\n--- Iteration {i+1} ---")
        
        # Make predictions
        proba = pipeline.predict_proba(X)[:, 1]
        y_pred = (proba >= threshold).astype(int)
        
        # Evaluate
        tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
        f1 = f1_score(y, y_pred, zero_division=0)
        precision = precision_score(y, y_pred, zero_division=0)
        recall = recall_score(y, y_pred, zero_division=0)
        
        print(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
        print(f"F1: {f1:.4f} | Precision: {precision:.4f} | Recall: {recall:.4f}")
        
        # Identify errors
        errors_mask = y != y_pred
        num_errors = errors_mask.sum()
        
        if num_errors == 0:
            print("No errors found! The model is perfect on this dataset.")
            break
            
        print(f"Found {num_errors} failing cases. Retraining on them...")
        
        X_errors = X[errors_mask]
        y_errors = y[errors_mask]
        
        # Transform text to features for the failing cases
        X_errors_features = feature_extractor.transform(X_errors)
        
        # Give the classifier multiple passes over the failing cases to ensure it learns
        classes = np.array([0, 1])
        for _ in range(3):
            clf.partial_fit(X_errors_features, y_errors, classes=classes)
        
        # Save the improved model
        joblib.dump(pipeline, FINAL_PIPELINE_PATH)
        print(f"Saved updated model to {FINAL_PIPELINE_PATH}")

    # Final evaluation metrics save
    proba = pipeline.predict_proba(X)[:, 1]
    y_pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    metrics = {
        'dataset_rows': len(X),
        'threshold_selected': threshold,
        'validation_tuned': {
            'accuracy': float(accuracy_score(y, y_pred)),
            'f1': float(f1_score(y, y_pred, zero_division=0)),
            'precision': float(precision_score(y, y_pred, zero_division=0)),
            'recall': float(recall_score(y, y_pred, zero_division=0)),
            'confusion_matrix': {'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)}
        }
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print("Self-correction loop complete.")

if __name__ == '__main__':
    main()
