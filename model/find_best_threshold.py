from __future__ import annotations

from pathlib import Path
import numpy as np
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


def main() -> int:
    root = Path(__file__).resolve().parent
    project_root = root.parent

    df = pd.read_csv(root / 'fake_job_postings.csv', index_col=0)
    cols = [c for c in TEXT_FIELDS if c in df.columns]
    df['combined_text'] = df[cols].fillna('').astype(str).agg(' '.join, axis=1).str.lower()
    df = df[df['combined_text'].str.len() > 10].copy()

    y = df['fraudulent'].astype(int).to_numpy()
    model = joblib.load(project_root / 'artifacts' / 'personal_job_model.pkl')
    p = model.predict_proba(df['combined_text'])[:, 1]

    thresholds = np.linspace(0.01, 0.99, 197)
    best_t = 0.5
    best_errors = 10**9
    best_fn = 10**9
    best_fp = 10**9

    for t in thresholds:
        pred = (p >= t).astype(int)
        errors = int((pred != y).sum())
        fn = int(((y == 1) & (pred == 0)).sum())
        fp = int(((y == 0) & (pred == 1)).sum())
        if errors < best_errors or (errors == best_errors and fn < best_fn):
            best_errors = errors
            best_t = float(t)
            best_fn = fn
            best_fp = fp

    print({'best_threshold': round(best_t, 4), 'errors': best_errors, 'fn': best_fn, 'fp': best_fp, 'baseline_errors_at_0.5': int(((p >= 0.5).astype(int) != y).sum())})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
