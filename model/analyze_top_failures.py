
from __future__ import annotations
from feature_utils import PaymentFlagAdder, add_payment_flag

from pathlib import Path
import json
import pandas as pd
import joblib


TEXT_FIELDS = [
    'title',
    'company_profile',
    'description',
    'requirements',
    'benefits',
    'location',
    'department',
    'employment_type',
    'required_experience',
    'required_education',
    'industry',
    'function',
]


def _build_text(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in TEXT_FIELDS if c in df.columns]
    return (
        df[cols]
        .fillna('')
        .astype(str)
        .agg(' '.join, axis=1)
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
        .str.lower()
    )


def main() -> int:
    root = Path(__file__).resolve().parent
    project_root = root.parent

    data_path = root / 'fake_job_postings.csv'
    model_path = project_root / 'artifacts' / 'personal_job_model.pkl'
    threshold_path = project_root / 'artifacts' / 'fraud_threshold.json'

    out_dir = project_root / 'artifacts'
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / 'top_100_failure_cases.csv'
    out_json = out_dir / 'top_100_failure_cases_summary.json'

    decision_threshold = 0.52
    if threshold_path.exists():
        try:
            payload = json.loads(threshold_path.read_text(encoding='utf-8'))
            decision_threshold = float(payload.get('selected_probability_threshold', decision_threshold))
        except Exception:
            pass

    decision_threshold = max(0.05, min(0.95, decision_threshold))

    df = pd.read_csv(data_path, index_col=0)
    if 'fraudulent' not in df.columns:
        raise ValueError("Expected 'fraudulent' column in dataset")

    df = df.copy()
    df['combined_text'] = _build_text(df)
    df = df[df['combined_text'].str.len() > 10].copy()

    model = joblib.load(model_path)

    X = df['combined_text']
    y_true = df['fraudulent'].astype(int)

    p_fraud = model.predict_proba(X)[:, 1]
    y_pred = (p_fraud >= decision_threshold).astype(int)

    eval_df = pd.DataFrame(
        {
            'dataset_index': df.index,
            'y_true': y_true.values,
            'y_pred': y_pred,
            'p_fraud': p_fraud,
            'title': df.get('title', '').astype(str),
            'company_profile': df.get('company_profile', '').astype(str),
            'description': df.get('description', '').astype(str),
            'location': df.get('location', '').astype(str),
            'industry': df.get('industry', '').astype(str),
            'required_experience': df.get('required_experience', '').astype(str),
            'required_education': df.get('required_education', '').astype(str),
            'employment_type': df.get('employment_type', '').astype(str),
            'function': df.get('function', '').astype(str),
        }
    )

    eval_df['is_error'] = eval_df['y_true'] != eval_df['y_pred']
    eval_df['error_type'] = eval_df.apply(
        lambda r: 'false_negative' if (r['y_true'] == 1 and r['y_pred'] == 0) else ('false_positive' if (r['y_true'] == 0 and r['y_pred'] == 1) else 'correct'),
        axis=1,
    )

    # Larger means model was more confidently wrong.
    eval_df['error_magnitude'] = (eval_df['y_true'] - eval_df['p_fraud']).abs()

    failures = eval_df[eval_df['is_error']].copy()
    top100 = failures.sort_values('error_magnitude', ascending=False).head(100).copy()

    top100['description'] = top100['description'].str.slice(0, 350)
    top100.to_csv(out_csv, index=False)

    summary = {
        'decision_threshold': round(decision_threshold, 4),
        'total_rows': int(len(eval_df)),
        'total_errors': int(len(failures)),
        'top_100_count': int(len(top100)),
        'false_negative_count': int((failures['error_type'] == 'false_negative').sum()),
        'false_positive_count': int((failures['error_type'] == 'false_positive').sum()),
        'output_csv': str(out_csv),
    }

    out_json.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    print('Top 100 failure analysis complete')
    print(summary)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
