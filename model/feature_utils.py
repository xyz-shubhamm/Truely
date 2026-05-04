from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np

def add_payment_flag(texts):
    payment_keywords = [
        'entry fee', 'registration fee', 'upfront payment', 'deposit required',
        'pay before', 'transfer fee', 'processing fee', 'wire transfer',
        'send money', 'payment required', 'payment before', 'upfront cost',
        'explicit fee', 'payment through', 'bank details', 'personal email',
    ]
    return [int(any(kw in t for kw in payment_keywords)) for t in texts]

class PaymentFlagAdder(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self
    def transform(self, X):
        return np.array(add_payment_flag(X)).reshape(-1, 1)
