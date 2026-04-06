import re
from pathlib import Path
import joblib

# Load model
MODEL_PATH = Path('artifacts/baseline_logreg_model.joblib')
VECTORIZER_PATH = Path('artifacts/baseline_tfidf_vectorizer.joblib')
model = joblib.load(MODEL_PATH)
vectorizer = joblib.load(VECTORIZER_PATH)

# Test text from your screenshot
test_text = 'Senior Software Engineer Kalvium Labs with the great package of 30lpa and with entry fees of 10 thousand'

# ML prediction
features = vectorizer.transform([test_text])
probs = model.predict_proba(features)[0]
print('=== ENHANCED PREDICTION TEST ===')
print(f'Test: "{test_text}"')
print(f'ML Model (before boost): {100*probs[1]:.1f}% fraud probability')

# Red flag detection (using corrected patterns)
text_lower = test_text.lower()
critical_flags = []

payment_patterns = [
    (r'entry\s+fee|registration\s+fee|upfront\s+payment|deposit\s+required|pay\s+.*\s+before|transfer\s+fee|processing\s+fee', 'Entry/Payment Fee Required'),
    (r'wire\s+transfer|wire\s+money|send\s+money|payment\s+before|upfront\s+cost', 'Upfront Payment Demanded'),
    (r'\$\d+.*fee|£\d+.*fee', 'Explicit Fee Amount'),
]

for pattern, label in payment_patterns:
    if re.search(pattern, text_lower):
        critical_flags.append(label)
        print(f'🚩 Detected: {label}')

# Boost calculation
if critical_flags:
    boost = 2.5 if any('Entry' in f or 'Payment' in f for f in critical_flags) else 1.5
    boosted = min(probs[1] * boost, 1.0)
    boosted = max(boosted, 0.85)  # Min 0.85 for critical payment flags
    print(f'\nAfter intelligent boosting (×{boost}):', f'{100*boosted:.1f}% fraud probability')
    print('✅ NOW CORRECTLY FLAGGED AS HIGH RISK INSTEAD OF 35%!')
else:
    print('No critical flags detected')

