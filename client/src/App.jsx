import { useEffect, useMemo, useState } from 'react';
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';

const TOKEN_KEY = 'checkmate_auth_token';
const USER_KEY = 'checkmate_user';

const initialForm = {
  title: '',
  company_profile: '',
  description: '',
  requirements: '',
  benefits: '',
  location: '',
  department: '',
  employment_type: '',
  required_experience: '',
  required_education: '',
  industry: '',
  function: '',
};

const redFlagPatterns = [
  {
    label: 'Unusual Payment Requests',
    detail: 'Posting asks for fees, deposits, or paid onboarding before interview.',
    regex: /(fee|deposit|registration charge|payment required|pay upfront)/i,
  },
  {
    label: 'Suspicious Contact Channel',
    detail: 'Uses unverified contact channels like generic email, Telegram, or WhatsApp only.',
    regex: /(gmail\.com|yahoo\.com|telegram|whatsapp)/i,
  },
  {
    label: 'Vague Requirements',
    detail: 'Very high rewards with little clarity on responsibilities or qualification standards.',
    regex: /(earn\s+\$?\d+|high salary|no experience needed|quick money|instant joining)/i,
  },
  {
    label: 'Urgency Pressure',
    detail: 'Forces immediate action with pressure language that bypasses verification steps.',
    regex: /(apply now|limited slots|urgent hiring|join immediately|today only)/i,
  },
];

const buildFlagInsights = (text) => {
  if (!text) {
    return [];
  }

  return redFlagPatterns
    .map((item) => {
      const match = text.match(item.regex);
      if (!match) {
        return null;
      }

      return {
        label: item.label,
        detail: item.detail,
        evidence: match[0],
      };
    })
    .filter(Boolean);
};

const samplePrediction = {
  prediction: 'fake',
  threshold: 0.57,
  real_probability: 0.17,
  fake_probability: 0.83,
  input_length: 190,
};

function AppShell() {
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const [historyItems, setHistoryItems] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyActionLoading, setHistoryActionLoading] = useState(false);
  const [historyActionError, setHistoryActionError] = useState('');

  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '');
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  });

  const [authForm, setAuthForm] = useState({ name: '', email: '', password: '' });
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  const navigate = useNavigate();
  const location = useLocation();

  const isAuthenticated = Boolean(token && user);

  const navItems = useMemo(
    () => [
      { path: '/', label: 'Home' },
      { path: '/check-job', label: 'Check Job' },
      { path: '/history', label: 'History' },
    ],
    []
  );

  const combinedText = useMemo(() => Object.values(form).join(' ').trim(), [form]);

  const clearAuthState = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken('');
    setUser(null);
    setHistoryItems([]);
  };

  const updateField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const authFetch = async (url, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };

    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
      let message = `Server error: ${response.status}`;
      try {
        const payload = await response.json();
        message = payload?.detail || payload?.error || message;
      } catch {
        message = `Server error: ${response.status}`;
      }
      throw new Error(message);
    }

    return response.json();
  };

  const fetchHistory = async () => {
    if (!token) {
      return;
    }

    setHistoryLoading(true);
    try {
      const payload = await authFetch('/api/history?limit=30');
      setHistoryItems(payload.items || []);
    } catch (err) {
      if ((err.message || '').toLowerCase().includes('token')) {
        clearAuthState();
      }
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDeleteHistoryItem = async (itemId) => {
    const confirmed = window.confirm('Delete this history entry?');
    if (!confirmed) {
      return;
    }

    setHistoryActionLoading(true);
    setHistoryActionError('');
    try {
      await authFetch(`/api/history/${itemId}`, { method: 'DELETE' });
      setHistoryItems((current) => current.filter((item) => item.id !== itemId));
    } catch (err) {
      setHistoryActionError(err.message || 'Failed to delete history item.');
    } finally {
      setHistoryActionLoading(false);
    }
  };

  const handleClearHistory = async () => {
    const confirmed = window.confirm('Delete all saved history? This cannot be undone.');
    if (!confirmed) {
      return;
    }

    setHistoryActionLoading(true);
    setHistoryActionError('');
    try {
      await authFetch('/api/history', { method: 'DELETE' });
      setHistoryItems([]);
    } catch (err) {
      setHistoryActionError(err.message || 'Failed to clear history.');
    } finally {
      setHistoryActionLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [token]);

  const openCheckPage = () => {
    if (!isAuthenticated) {
      navigate('/login');
      return;
    }
    setError('');
    navigate('/check-job');
  };

  const requestPrediction = async (postingPayload) => {
    if (!isAuthenticated) {
      throw new Error('Please login first');
    }

    const payload = await authFetch('/api/predict', {
      method: 'POST',
      body: JSON.stringify(postingPayload),
    });
    return payload.result;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const predicted = await requestPrediction(form);
      setResult(predicted);
      fetchHistory();
      navigate('/report');
    } catch (err) {
      setError(err.message || 'Prediction failed');
    } finally {
      setLoading(false);
    }
  };

  const saveSession = (nextToken, nextUser) => {
    if (!nextToken || !nextUser) {
      clearAuthState();
      setAuthError('Authentication failed. Please login again.');
      return;
    }

    localStorage.setItem(TOKEN_KEY, nextToken);
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
    setAuthError('');
    setAuthForm({ name: '', email: '', password: '' });
  };

  const handleSignup = async (event) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError('');

    try {
      const payload = await authFetch('/auth/signup', {
        method: 'POST',
        headers: {},
        body: JSON.stringify(authForm),
      });
      saveSession(payload.token, payload.user);
      navigate('/check-job');
    } catch (err) {
      setAuthError(err.message || 'Signup failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async (event) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError('');

    try {
      const payload = await authFetch('/auth/login', {
        method: 'POST',
        headers: {},
        body: JSON.stringify({
          email: authForm.email,
          password: authForm.password,
        }),
      });
      saveSession(payload.token, payload.user);
      navigate('/check-job');
    } catch (err) {
      setAuthError(err.message || 'Login failed');
    } finally {
      setAuthLoading(false);
    }
  };

  const activeResult = useMemo(() => {
    const useSample = new URLSearchParams(location.search).get('sample') === '1';
    if (result) {
      return result;
    }
    if (useSample) {
      return samplePrediction;
    }
    return null;
  }, [location.search, result]);

  const activeTextForFlags = useMemo(() => {
    if (combinedText) {
      return combinedText;
    }
    if (activeResult === samplePrediction) {
      return 'Urgent hiring no experience needed payment required through personal email.';
    }
    return '';
  }, [activeResult, combinedText]);

  const activeReport = useMemo(() => {
    if (!activeResult) {
      return null;
    }

    const backendFlags = Array.isArray(activeResult.risk_signals) ? activeResult.risk_signals : [];
    const matchedFlags = backendFlags.length > 0 ? backendFlags : buildFlagInsights(activeTextForFlags);
    const calibratedRisk = Number.isFinite(activeResult.risk_score) ? activeResult.risk_score : Math.round((activeResult.fake_probability || 0) * 100);
    const riskScore = calibratedRisk;
    const fallbackFlags = [
      {
        label: riskScore >= 50 ? 'Pattern Confidence Risk' : 'Low Explicit Trigger Match',
        detail:
          riskScore >= 50
            ? 'The combined model and rule-based signals indicate elevated fraud risk.'
            : 'No strong scam phrases were matched in visible text. Continue manual verification for recruiter identity.',
        evidence: `Calibrated risk ${riskScore}%`,
      },
    ];

    return {
      riskScore,
      confidence: Math.max(activeResult.fake_probability || 0, activeResult.real_probability || 0),
      severity: riskScore >= 70 ? 'high' : riskScore >= 40 ? 'moderate' : 'low',
      flags: matchedFlags.length > 0 ? matchedFlags : fallbackFlags,
      modelLabel: activeResult.model_label,
      modelFakeProbability: activeResult.model_fake_probability,
      heuristicFakeProbability: activeResult.heuristic_fake_probability,
      calibratedRisk,
      checklist: [
        'Do not share banking details until company identity is verified.',
        'Verify the official company website and recruiter domain.',
        'Request formal interview scheduling through verifiable channels.',
      ],
    };
  }, [activeResult, activeTextForFlags]);

  const renderHome = () => (
    <section className="hero-section">
      <div className="hero-grid">
        <div className="hero-copy reveal">
          <span className="chip">DAILY PROTECTION MODE</span>
          <h1>Verify Jobs Before You Apply.</h1>
          <p>
            Built for daily use: account-based access, saved history, and instant scam analysis for
            every listing you evaluate.
          </p>
          <div className="hero-actions">
            <button type="button" className="btn btn-primary" onClick={openCheckPage}>
              Start Verification
            </button>
            <button type="button" className="btn btn-muted" onClick={() => navigate('/report?sample=1')}>
              View Sample Report
            </button>
          </div>
        </div>
        <div className="scanner-card reveal delay-1">
          <h3>Account Features</h3>
          <ul className="simple-list">
            <li>Secure signup/login</li>
            <li>Saved verification history</li>
            <li>Per-user prediction logs</li>
            <li>Ready for future chat persistence</li>
          </ul>
        </div>
      </div>
    </section>
  );

  const renderCheckJob = () => (
    <section className="check-layout">
      <header className="page-head reveal">
        <span className="chip">AUTHENTICITY LEDGER</span>
        <h1>Analyze Job Posting</h1>
        <p>Paste a job listing and store the result in your account history.</p>
      </header>

      <div className="check-grid">
        <form className="check-form reveal delay-1" onSubmit={handleSubmit}>
          <div className="field-grid">
            <label>
              <span>JOB TITLE</span>
              <input
                value={form.title}
                onChange={(event) => updateField('title', event.target.value)}
                placeholder="e.g. Senior Software Engineer"
                required
              />
            </label>
            <label>
              <span>COMPANY NAME (OPTIONAL)</span>
              <input
                value={form.company_profile}
                onChange={(event) => updateField('company_profile', event.target.value)}
                placeholder="e.g. Google"
              />
            </label>
          </div>

          <label>
            <span>JOB DESCRIPTION</span>
            <textarea
              rows={11}
              value={form.description}
              onChange={(event) => updateField('description', event.target.value)}
              placeholder="Paste the full job description here..."
              required
            />
          </label>

          {error ? <p className="form-error">{error}</p> : null}

          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Analyzing...' : 'Analyze Posting'}
            </button>
          </div>
        </form>

        <aside className="check-side reveal delay-2">
          <div className="why-card">
            <h3>Why verify daily?</h3>
            <ul>
              <li>Track suspicious patterns over time.</li>
              <li>Keep all your checked opportunities in one account.</li>
              <li>Review old reports before interviews.</li>
            </ul>
          </div>
          <div className="side-banner">
            <p>Logged in as {user?.name || user?.email}.</p>
          </div>
        </aside>
      </div>
    </section>
  );

  const renderResult = () => {
    if (!activeReport || !activeResult) {
      return (
        <section className="empty-state">
          <h2>No analysis yet</h2>
          <p>Run a job posting analysis first to see the full report.</p>
          <button type="button" className="btn btn-primary" onClick={openCheckPage}>
            Go to Check Job
          </button>
        </section>
      );
    }

    return (
      <section className="report-layout">
        <button type="button" className="back-link" onClick={openCheckPage}>
          Back to Search
        </button>

        <h1>Analysis Report</h1>
        <div className="report-grid">
          <aside className="risk-column">
            <article className="risk-card">
              <h3>Risk Assessment</h3>
              <div className="risk-ring">
                <div>
                  <strong>{activeReport.riskScore}%</strong>
                  <span>SCAM PROBABILITY</span>
                </div>
              </div>
              <div className={`risk-alert ${activeReport.severity}`}>
                <h4>{activeReport.severity.toUpperCase()} RISK</h4>
              </div>
              <div className="meta-card" style={{ marginTop: '0.9rem' }}>
                <div>
                  <span>Model signal</span>
                  <strong>{Math.round((activeReport.modelFakeProbability || 0) * 100)}%</strong>
                </div>
                <div>
                  <span>Heuristic signal</span>
                  <strong>{Math.round((activeReport.heuristicFakeProbability || 0) * 100)}%</strong>
                </div>
                <div>
                  <span>Calibrated risk</span>
                  <strong>{Math.round(activeReport.calibratedRisk || activeReport.riskScore)}%</strong>
                </div>
              </div>
            </article>
          </aside>

          <main className="summary-column">
            <article className="summary-card">
              <h3>Risk Summary</h3>
              <div className="flag-grid">
                {activeReport.flags.map((flag) => (
                  <div key={flag.label} className="flag-item">
                    <div>
                      <h4>{flag.label}</h4>
                      <p>{flag.detail}</p>
                      {flag.evidence ? <p>Matched evidence: "{flag.evidence}"</p> : null}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </main>
        </div>
      </section>
    );
  };

  const renderHistory = () => (
    <section className="about-layout">
      <header className="about-hero reveal">
        <div>
          <span className="kicker">YOUR SAVED ANALYSES</span>
          <h1>Verification History</h1>
          <p>Every prediction you run is stored in your account.</p>
        </div>
        <div className="hero-actions">
          <button
            type="button"
            className="btn btn-muted"
            onClick={handleClearHistory}
            disabled={historyActionLoading || historyLoading || historyItems.length === 0}
          >
            {historyActionLoading ? 'Deleting...' : 'Clear History'}
          </button>
        </div>
      </header>

      {historyLoading ? <p>Loading history...</p> : null}
      {historyActionError ? <p className="form-error">{historyActionError}</p> : null}
      {!historyLoading && historyItems.length === 0 ? <p>No saved analyses yet.</p> : null}

      <div className="about-grid">
        {historyItems.map((item) => (
          <article className="purpose-card" key={item.id}>
            <h3>{item.input_payload?.title || 'Untitled Posting'}</h3>
            <p>{item.input_payload?.company_profile || 'Company not provided'}</p>
            <p>
              Risk: <strong>{Math.round(item.risk_score)}%</strong> | Verdict:{' '}
              <strong>{item.is_fake ? 'Likely Scam' : 'Likely Genuine'}</strong>
            </p>
            <small>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</small>
            <div style={{ marginTop: '0.75rem' }}>
              <button
                type="button"
                className="btn btn-muted"
                onClick={() => handleDeleteHistoryItem(item.id)}
                disabled={historyActionLoading}
              >
                Delete
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );

  const renderLogin = () => (
    <section className="contact-layout">
      <form className="report-form reveal" onSubmit={handleLogin}>
        <h3>Login</h3>
        <p>Sign in to access your daily verification workspace.</p>

        <label>
          <span>EMAIL</span>
          <input
            type="email"
            value={authForm.email}
            onChange={(event) => setAuthForm((c) => ({ ...c, email: event.target.value }))}
            required
          />
        </label>

        <label>
          <span>PASSWORD</span>
          <input
            type="password"
            value={authForm.password}
            onChange={(event) => setAuthForm((c) => ({ ...c, password: event.target.value }))}
            required
          />
        </label>

        {authError ? <p className="form-error">{authError}</p> : null}

        <button type="submit" className="btn btn-primary" disabled={authLoading}>
          {authLoading ? 'Signing in...' : 'Login'}
        </button>
        <button type="button" className="btn btn-muted" onClick={() => navigate('/signup')}>
          Need an account? Signup
        </button>
      </form>
    </section>
  );

  const renderSignup = () => (
    <section className="contact-layout">
      <form className="report-form reveal" onSubmit={handleSignup}>
        <h3>Create Account</h3>
        <p>Signup once, then use CheckMate daily with saved records.</p>

        <label>
          <span>FULL NAME</span>
          <input
            type="text"
            value={authForm.name}
            onChange={(event) => setAuthForm((c) => ({ ...c, name: event.target.value }))}
            required
          />
        </label>

        <label>
          <span>EMAIL</span>
          <input
            type="email"
            value={authForm.email}
            onChange={(event) => setAuthForm((c) => ({ ...c, email: event.target.value }))}
            required
          />
        </label>

        <label>
          <span>PASSWORD</span>
          <input
            type="password"
            value={authForm.password}
            onChange={(event) => setAuthForm((c) => ({ ...c, password: event.target.value }))}
            required
          />
        </label>

        {authError ? <p className="form-error">{authError}</p> : null}

        <button type="submit" className="btn btn-primary" disabled={authLoading}>
          {authLoading ? 'Creating account...' : 'Signup'}
        </button>
        <button type="button" className="btn btn-muted" onClick={() => navigate('/login')}>
          Already have an account? Login
        </button>
      </form>
    </section>
  );

  return (
    <div className="vh-app">
      <nav className="top-nav">
        <button type="button" className="brand" onClick={() => navigate('/')}>
          CheckMate
        </button>

        <div className="nav-links">
          {navItems.map((item) => (
            <NavLink key={item.path} to={item.path} className={({ isActive }) => (isActive ? 'active' : '')}>
              {item.label}
            </NavLink>
          ))}
        </div>

        {!isAuthenticated ? (
          <div className="nav-auth">
            <button type="button" className="btn btn-muted" onClick={() => navigate('/login')}>
              Login
            </button>
            <button type="button" className="btn btn-nav" onClick={() => navigate('/signup')}>
              Signup
            </button>
          </div>
        ) : (
          <div className="nav-auth">
            <span className="auth-pill">{user?.name || user?.email}</span>
            <button type="button" className="btn btn-muted" onClick={clearAuthState}>
              Logout
            </button>
          </div>
        )}
      </nav>

      <main className="vh-main">
        <Routes>
          <Route path="/" element={renderHome()} />
          <Route path="/login" element={!isAuthenticated ? renderLogin() : <Navigate to="/check-job" replace />} />
          <Route path="/signup" element={!isAuthenticated ? renderSignup() : <Navigate to="/check-job" replace />} />
          <Route path="/check-job" element={isAuthenticated ? renderCheckJob() : <Navigate to="/login" replace />} />
          <Route path="/report" element={isAuthenticated ? renderResult() : <Navigate to="/login" replace />} />
          <Route path="/history" element={isAuthenticated ? renderHistory() : <Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <footer className="site-footer">
        <div>
          <strong>CheckMate Professional Ledger</strong>
          <p>Secure, account-based scam detection for daily use.</p>
        </div>
        <small>© 2026 CheckMate. All rights reserved.</small>
      </footer>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}

export default App;
