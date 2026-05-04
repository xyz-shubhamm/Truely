
"""
Model Evaluation Script for Fake Job Detection
Computes confusion matrix, F1 score, precision, and recall metrics.
"""

import json
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_score, recall_score

# Paths
ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
DATA_PATH = ROOT_DIR / 'fake_job_postings.csv'
MODEL_DIR = PROJECT_ROOT / 'artifacts'
MODEL_PATH = MODEL_DIR / 'personal_job_model.pkl'

def load_data_and_model():
    """Load test data, preprocess, and load model pipeline"""
    print("[1] Loading dataset...")
    df = pd.read_csv(DATA_PATH, index_col=0)
    print(f"Loaded {len(df):,} job postings")

    print("\n[2] Preprocessing text...")
    text_fields = [
        'title', 'company_profile', 'description', 'requirements', 'benefits',
        'location', 'department', 'employment_type', 'required_experience',
        'required_education', 'industry', 'function'
    ]
    df['combined_text'] = df[text_fields].fillna('').agg(' '.join, axis=1).str.lower()
    df = df[df['combined_text'].str.len() > 10]

    print("\n[3] Loading trained pipeline model...")
    model = joblib.load(MODEL_PATH)
    print("\u2713 Model loaded")
    return df, model

def evaluate_model(df, model):
    """Evaluate model performance on the entire dataset"""
    print("\n[4] Vectorizing text data...")
def evaluate_model(df, model):
    y_true = df['fraudulent'].values
    # Use the same feature as training: 'combined_text'
    X = df['combined_text']

    print("\n[4] Making predictions...")
    y_pred = model.predict(X)
    y_pred_proba = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else None
    # Confusion Matrix
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()

    # Individual metrics
    f1 = f1_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred)
    recall = recall_score(y_true, y_pred)

    print("\n" + "="*50)
    print("MODEL EVALUATION RESULTS")
    print("="*50)

    print("\nConfusion Matrix:")
    print(f"  True Negative (TN):  {tn:,}")
    print(f"  False Positive (FP): {fp:,}")
    print(f"  False Negative (FN): {fn:,}")
    print(f"  True Positive (TP):  {tp:,}")

    print("\nPredicted:     Genuine    Fraud")
    print(f"Actual: Genuine  {tn:>8,}  {fp:>6,}")
    print(f"       Fraud     {fn:>8,}  {tp:>6,}")

    print("\nKey Metrics:")
    print(f"F1 Score: {f1:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall: {recall:.4f}")

    print("\nAdditional Metrics:")
    print(f"Accuracy: {(tp + tn) / (tp + tn + fp + fn):.4f}")
    print(f"Specificity: {tn / (tn + fp) if (tn + fp) > 0 else 0:.4f}")
    print(f"Balanced Accuracy: {(recall + (tn / (tn + fp) if (tn + fp) > 0 else 0)) / 2:.4f}")

    # Class-wise metrics
    print("\nClass-wise Performance:")
    print("Genuine Jobs (Class 0):")
    print(f"  Precision: {tn / (tn + fn) if (tn + fn) > 0 else 0:.4f}")
    print(f"  Recall: {tn / (tn + fp) if (tn + fp) > 0 else 0:.4f}")

    print("\nFraudulent Jobs (Class 1):")
    print(f"  Precision: {tp / (tp + fp) if (tp + fp) > 0 else 0:.4f}")
    print(f"  Recall: {tp / (tp + fn) if (tp + fn) > 0 else 0:.4f}")

    print("\n" + "="*50)
    print("Detailed Classification Report:")
    print("="*50)
    print(classification_report(y_true, y_pred, target_names=['Genuine', 'Fraudulent']))

    return {
        'confusion_matrix': {
            'tn': int(tn), 'fp': int(fp), 'fn': int(fn), 'tp': int(tp)
        },
        'metrics': {
            'f1_score': float(f1),
            'precision': float(precision),
            'recall': float(recall),
            'accuracy': float((tp + tn) / (tp + tn + fp + fn)),
            'specificity': float(tn / (tn + fp)) if (tn + fp) > 0 else 0
        }
    }

def main():
    """Main evaluation function"""
    try:
        df, model = load_data_and_model()
        results = evaluate_model(df, model)
        output_path = ROOT_DIR / 'evaluation_results.json'
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n\u2713 Results saved to {output_path}")
    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())