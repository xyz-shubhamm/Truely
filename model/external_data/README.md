# External Datasets (Fraud Priority)

Drop additional CSV datasets here to increase fake-job coverage.

Required columns:
- `fraudulent` (target: 1=fake, 0=real)
- At least one text field from:
  - `title`, `company_profile`, `description`, `requirements`, `benefits`,
  - `location`, `department`, `employment_type`, `required_experience`,
  - `required_education`, `industry`, `function`

How it works:
- `model/train_model.py` automatically loads all `*.csv` files in this folder.
- It deduplicates and trains with a fake-first objective.
- Threshold is optimized for high recall and exported to `artifacts/fraud_threshold.json`.

Notes:
- We intentionally accept more false positives to reduce fake->real misses.
- Keep file encoding as UTF-8 where possible.
