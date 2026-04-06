#!/usr/bin/env python3
"""
Proper ML training script for fake job detection.
Handles imbalanced data, proper text preprocessing, and model evaluation.
"""

import json
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, roc_curve, auc

ROOT_DIR = Path(__file__).resolve().parent
DATA_PATH = ROOT_DIR / 'fake_job_postings.csv'
MODEL_DIR = ROOT_DIR / 'artifacts'
MODEL_PATH = MODEL_DIR / 'baseline_logreg_model.joblib'
VECTORIZER_PATH = MODEL_DIR / 'baseline_tfidf_vectorizer.joblib'
THRESHOLD_PATH = MODEL_DIR / 'baseline_metrics.json'

MODEL_DIR.mkdir(exist_ok=True)

print("[1] Loading dataset...")
df = pd.read_csv(DATA_PATH, index_col=0)  # Drop first malformed column
print(f"Loaded {len(df):,} job postings")

# Check target distribution
fraud_count = (df['fraudulent'] == 1).sum()
real_count = (df['fraudulent'] == 0).sum()
fraud_pct = 100 * fraud_count / len(df)
print(f"  - Fraud: {fraud_count:,} ({fraud_pct:.2f}%)")
print(f"  - Genuine: {real_count:,} ({100-fraud_pct:.2f}%)")

print("\n[2] Preprocessing text...")
# Combine all text fields for analysis
text_fields = [
    'title', 'company_profile', 'description', 'requirements', 'benefits',
    'location', 'department', 'employment_type', 'required_experience',
    'required_education', 'industry', 'function'
]

df['combined_text'] = df[text_fields].fillna('').agg(' '.join, axis=1).str.lower()
df = df[df['combined_text'].str.len() > 10]  # Remove empty postings
print(f"After filtering: {len(df):,} postings")

X = df['combined_text'].values
y = df['fraudulent'].values

print("\n[3] Splitting data (80/20)...")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"  Train: {len(X_train):,} | Test: {len(X_test):,}")

print("\n[4] TF-IDF Vectorization...")
vectorizer = TfidfVectorizer(
    max_features=5000,
    min_df=5,
    max_df=0.8,
    ngram_range=(1, 2),
    stop_words='english',
    sublinear_tf=True,
)
X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)
print(f"  Vocabulary size: {len(vectorizer.get_feature_names_out()):,}")

print("\n[5] Training LogisticRegression with class balancing...")
model = LogisticRegression(
    max_iter=1000,
    class_weight='balanced',  # Handle imbalance
    random_state=42,
    solver='liblinear',
    C=0.5,  # Regularization
)
model.fit(X_train_vec, y_train)

print("\n[6] Evaluating on test set...")
y_pred = model.predict(X_test_vec)
y_pred_proba = model.predict_proba(X_test_vec)[:, 1]

print("\nClassification Report:")
print(classification_report(y_test, y_pred, target_names=['Genuine', 'Fraud']))

print("\nConfusion Matrix:")
tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
print(f"  TN: {tn:,} | FP: {fp:,}")
print(f"  FN: {fn:,} | TP: {tp:,}")
print(f"  TPR (Recall): {tp / (tp + fn):.3f}")
print(f"  FPR: {fp / (fp + tn):.3f}")

# Find optimal threshold
fpr, tpr, thresholds = roc_curve(y_test, y_pred_proba)
roc_auc = auc(fpr, tpr)
print(f"\nROC-AUC: {roc_auc:.4f}")

# Choose threshold that maximizes TPR - FPR (Youden index)
optimal_idx = np.argmax(tpr - fpr)
optimal_threshold = thresholds[optimal_idx]
print(f"Optimal threshold (Youden): {optimal_threshold:.4f}")

print("\n[7] Saving artifacts...")
joblib.dump(model, MODEL_PATH)
print(f"  ✓ Model saved to {MODEL_PATH}")

joblib.dump(vectorizer, VECTORIZER_PATH)
print(f"  ✓ Vectorizer saved to {VECTORIZER_PATH}")

metrics = {
    'roc_auc': float(roc_auc),
    'optimal_threshold': float(optimal_threshold),
    'selected_threshold': float(optimal_threshold),
    'test_recall': float(tp / (tp + fn)),
    'test_fpr': float(fp / (fp + tn)),
    'confusion_matrix': {'tp': int(tp), 'tn': int(tn), 'fp': int(fp), 'fn': int(fn)},
}
THRESHOLD_PATH.write_text(json.dumps(metrics, indent=2))
print(f"  ✓ Metrics saved to {THRESHOLD_PATH}")

print("\n✅ Training complete! Model ready for predictions.")
print(f"\n📊 Summary:")
print(f"   ROC-AUC: {roc_auc:.4f}")
print(f"   Optimal Threshold: {optimal_threshold:.4f}")
print(f"   Recall (detect frauds): {tp / (tp + fn):.2%}")
print(f"   False Positive Rate: {fp / (fp + tn):.2%}")
