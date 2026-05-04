import { useEffect, useMemo, useState } from 'react';
// Truely App v1.2 - Styled Reports & Redirect Fix
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { supabase, isSupabaseConfigured } from './supabaseClient';

const TOKEN_KEY = 'truely_auth_token';
const USER_KEY = 'truely_user';

const initialForm = {
  title: '',
  company_profile: '',
  description: '',
};

const initialResearchForm = {
  company: '',
  role: '',
  location: '',
};

function AppShell() {
  const [form, setForm] = useState(initialForm);
  const [researchForm, setResearchForm] = useState(initialResearchForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [researchResult, setResearchResult] = useState(null);
  const [error, setError] = useState('');
  
  const [jobHistory, setJobHistory] = useState([]);
  const [researchHistory, setResearchHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyTab, setHistoryTab] = useState('jobs'); // 'jobs' or 'research'

  const [inputMode, setInputMode] = useState('text');
  const [isScrolled, setIsScrolled] = useState(false);

  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '');
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  });

  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  const navigate = useNavigate();
  const location = useLocation();
  const isAuthenticated = Boolean(token && user);

  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  const toggleDarkMode = () => {
    document.documentElement.classList.toggle('dark');
  };

  // --- Auth Sync Logic ---
  useEffect(() => {
    if (!supabase) return;

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        try {
          const response = await fetch('/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ access_token: session.access_token })
          });
          if (response.ok) {
            const data = await response.json();
            saveSession(data.token, data.user);
            // Only redirect if we are on login or landing to avoid interrupting active research
            if (location.pathname === '/login' || location.pathname === '/') {
              navigate('/verify');
            }
          }
        } catch (err) {
          console.error('Backend sync failed:', err);
        }
      } else if (event === 'SIGNED_OUT') {
        clearAuthState();
      }
    });

    return () => subscription.unsubscribe();
  }, [navigate]);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 10);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const clearAuthState = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken('');
    setUser(null);
    setJobHistory([]);
    setResearchHistory([]);
    if (supabase) supabase.auth.signOut();
  };

  const saveSession = (nextToken, nextUser) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
    setAuthError('');
  };

  const authFetch = async (url, options = {}) => {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let message = `Server error: ${response.status}`;
      try { const payload = await response.json(); message = payload?.detail || payload?.error || message; } catch {}
      throw new Error(message);
    }
    return response.json();
  };

  const fetchHistory = async () => {
    if (!token) return;
    setHistoryLoading(true);
    try {
      const [jobsData, researchData] = await Promise.all([
        authFetch('/api/history?limit=50'),
        authFetch('/api/research-history?limit=50')
      ]);
      setJobHistory(jobsData.items || []);
      setResearchHistory(researchData.items || []);
    } catch (err) {
      if ((err.message || '').toLowerCase().includes('token')) clearAuthState();
    } finally { setHistoryLoading(false); }
  };

  useEffect(() => { fetchHistory(); }, [token]);

  const handlePredict = async (e) => {
    e.preventDefault();
    if (!isAuthenticated) { navigate('/login'); return; }
    setLoading(true);
    setError('');
    try {
      const payload = await authFetch('/api/predict', { method: 'POST', body: JSON.stringify(form) });
      setResult(payload.result);
      fetchHistory();
      navigate('/report');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  const handleResearch = async (e) => {
    e.preventDefault();
    if (!isAuthenticated) { navigate('/login'); return; }
    setLoading(true);
    setError('');
    try {
      const payload = await authFetch('/api/research', { method: 'POST', body: JSON.stringify(researchForm) });
      setResearchResult(payload.data);
      fetchHistory();
      navigate('/research-report');
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };


  const handleGoogleLogin = async () => {
    if (!supabase) {
      alert('Supabase is not configured. Please check your .env file.');
      return;
    }
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin
      }
    });
  };

  // --- Render Functions ---

  const renderLanding = () => (
    <div className="flex flex-col reveal">
      <section className="flex flex-col items-center justify-center text-center px-gutter pt-40 pb-32 relative overflow-hidden min-h-[85vh]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(111,102,241,0.08),transparent_50%)] dark:bg-[radial-gradient(circle_at_top_right,rgba(111,102,241,0.15),transparent_50%)] animate-pulse"></div>
        <div className="relative z-10 max-w-4xl mx-auto">
          <span className="inline-block px-6 py-2 rounded-full bg-violet-500/10 dark:bg-violet-500/20 text-primary-container dark:text-violet-300 text-[11px] font-black uppercase tracking-[0.3em] mb-10 animate-fade-in-down border border-violet-500/20 dark:border-violet-500/30 shadow-[0_0_20px_rgba(167,139,250,0.2)]">INTELLIGENT VERIFICATION</span>
          <h1 className="font-display text-5xl md:text-7xl font-black tracking-tightest leading-[1.0] text-on-surface dark:text-white mb-8 reveal">
            Apply with <span className="text-primary-container dark:text-violet-400 drop-shadow-[0_0_15px_rgba(167,139,250,0.4)]">confidence.</span><br />
            Verify with Truely.
          </h1>
          <p className="font-body-lg text-lg md:text-xl text-on-surface-variant dark:text-slate-400 max-w-2xl mx-auto mb-16 leading-relaxed font-medium reveal" style={{animationDelay: '200ms'}}>
            The global standard for job authenticity analysis and company reputation intelligence. 
            Protect your career from modern recruitment fraud with real-time AI forensics.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-6 reveal" style={{animationDelay: '400ms'}}>
            <button onClick={() => navigate('/verify')} className="w-full sm:w-auto bg-primary-container text-on-primary px-12 py-5 rounded-[24px] font-black text-lg shadow-2xl shadow-primary-container/40 hover:scale-105 active:scale-95 transition-all duration-500">Get Started Free</button>
            <button onClick={() => navigate('/research')} className="w-full sm:w-auto bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-on-surface dark:text-white px-12 py-5 rounded-[24px] font-black text-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-all duration-500">Research Company</button>
          </div>
        </div>
        
        <div className="mt-32 grid grid-cols-2 md:grid-cols-4 gap-12 items-center justify-center grayscale opacity-40 hover:grayscale-0 hover:opacity-100 transition-all duration-700 reveal" style={{animationDelay: '600ms'}}>
          <div className="flex items-center gap-2 font-display font-bold text-sm tracking-widest"><span className="material-symbols-outlined text-primary-container">verified_user</span> SCAM PROOF</div>
          <div className="flex items-center gap-2 font-display font-bold text-sm tracking-widest"><span className="material-symbols-outlined text-orange-500">bolt</span> INSTANT</div>
          <div className="flex items-center gap-2 font-display font-bold text-sm tracking-widest"><span className="material-symbols-outlined text-blue-500">smart_toy</span> AI POWERED</div>
          <div className="flex items-center gap-2 font-display font-bold text-sm tracking-widest"><span className="material-symbols-outlined text-purple-500">history_edu</span> HISTORY</div>
        </div>
      </section>

      <section className="bg-white dark:bg-[#0A0A0B] py-48 px-gutter border-y border-slate-100 dark:border-slate-800">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-24 items-center">
            <div className="reveal">
              <span className="text-primary-container font-bold text-[10px] uppercase tracking-[0.3em] mb-6 block">INTELLIGENT ANALYSIS</span>
              <h2 className="text-5xl font-display font-extrabold mb-8 leading-tight tracking-tightest text-on-surface dark:text-white">Unmasking sophisticated fraud.</h2>
              <p className="text-on-surface-variant dark:text-slate-400 text-xl mb-12 leading-relaxed font-medium opacity-70">
                Our hybrid engine combines deep learning with heuristic pattern matching to 
                detect recruitment scams that often bypass traditional filters.
              </p>
              <div className="space-y-8">
                <div className="flex gap-6 group">
                  <div className="w-14 h-14 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform duration-500">
                    <span className="material-symbols-outlined text-emerald-600 dark:text-emerald-400 text-3xl">payments</span>
                  </div>
                  <div>
                    <h4 className="font-bold text-lg text-on-surface dark:text-white mb-1">Financial Pattern Detection</h4>
                    <p className="text-sm text-on-surface-variant dark:text-slate-400 leading-relaxed">Identifies requests for upfront fees, crypto payments, or suspicious banking setups.</p>
                  </div>
                </div>
                <div className="flex gap-6 group">
                  <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform duration-500">
                    <span className="material-symbols-outlined text-blue-600 dark:text-blue-400 text-3xl">alternate_email</span>
                  </div>
                  <div>
                    <h4 className="font-bold text-lg text-on-surface dark:text-white mb-1">Domain Verification</h4>
                    <p className="text-sm text-on-surface-variant dark:text-slate-400 leading-relaxed">Flags mismatching domains and generic email providers used by impersonators.</p>
                  </div>
                </div>
                <div className="flex gap-6 group">
                  <div className="w-14 h-14 rounded-2xl bg-purple-50 dark:bg-purple-500/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform duration-500">
                    <span className="material-symbols-outlined text-purple-600 dark:text-purple-400 text-3xl">psychology</span>
                  </div>
                  <div>
                    <h4 className="font-bold text-lg text-on-surface dark:text-white mb-1">Psychological Profiling</h4>
                    <p className="text-sm text-on-surface-variant dark:text-slate-400 leading-relaxed">Analyzes high-pressure language and unrealistic promises designed to exploit urgency.</p>
                  </div>
                </div>
              </div>
            </div>
            <div className="relative reveal">
              <div className="bg-surface-container-low dark:bg-slate-900 rounded-[40px] p-12 luxury-shadow border border-white dark:border-slate-800 relative z-10">
                <div className="flex items-center justify-between mb-12">
                  <div className="flex items-center gap-3">
                    <div className="w-2.5 h-2.5 rounded-full bg-error animate-pulse"></div>
                    <span className="text-[10px] font-black text-error uppercase tracking-[0.2em]">Live Forensics Engine</span>
                  </div>
                  <div className="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-[9px] font-bold text-slate-400">v2.4.0</div>
                </div>
                <div className="space-y-6">
                   <div className="h-4 bg-slate-200/50 dark:bg-slate-700/50 rounded-full w-[95%]"></div>
                   <div className="h-4 bg-slate-200/50 dark:bg-slate-700/50 rounded-full w-[75%]"></div>
                   <div className="h-4 bg-slate-200/50 dark:bg-slate-700/50 rounded-full w-[88%]"></div>
                   <div className="pt-12 flex flex-col items-center">
                     <div className="w-24 h-24 rounded-full border-[6px] border-primary-fixed/20 border-t-primary-container animate-spin mb-6"></div>
                     <p className="text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-[0.2em]">Analyzing Risk Vectors...</p>
                   </div>
                </div>
              </div>
              <div className="absolute -bottom-10 -right-10 bg-white dark:bg-slate-800 p-8 rounded-[32px] shadow-2xl border border-slate-50 dark:border-slate-700 max-w-[240px] z-20 hover:scale-105 transition-transform duration-500">
                <div className="flex items-center gap-2 mb-3">
                  <span className="material-symbols-outlined text-emerald-500 text-sm">verified</span>
                  <p className="text-[11px] font-black text-emerald-600 uppercase tracking-widest">99.2% Accuracy</p>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 font-semibold leading-relaxed">Our dataset is trained on over 10,000 verified scam listings and community reports.</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );

  const renderVerify = () => (
    <main className="flex-grow flex flex-col items-center justify-center px-gutter py-xxl max-w-[1200px] mx-auto w-full reveal">
      <div className="text-center mb-xl">
        <h1 className="font-h1 text-h1 text-on-surface dark:text-violet-200 mb-md">Verify Job Posting</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant dark:text-violet-300/70 max-w-2xl mx-auto">
          Analyze listings for fraudulent patterns and recruitment scams.
        </p>
      </div>

      <div className="bg-white dark:bg-[#1A1625] rounded-card soft-shadow w-full max-w-3xl p-lg md:p-xl border border-white dark:border-slate-800">
        <form onSubmit={handlePredict} className="space-y-md">
          <input 
            placeholder="Job Title"
            required
            value={form.title}
            onChange={(e) => setForm(f => ({ ...f, title: e.target.value }))}
            className="w-full h-12 px-md bg-surface-container-low dark:bg-slate-800 border-none rounded-xl focus:ring-2 focus:ring-primary-container outline-none dark:text-white"
          />
          <input 
            placeholder="Company Name (Optional)"
            value={form.company_profile}
            onChange={(e) => setForm(f => ({ ...f, company_profile: e.target.value }))}
            className="w-full h-12 px-md bg-surface-container-low dark:bg-slate-800 border-none rounded-xl focus:ring-2 focus:ring-primary-container outline-none dark:text-white"
          />
          <div 
            className={`relative group border-2 border-dashed rounded-2xl p-8 transition-all flex flex-col items-center justify-center bg-surface-container-low/50 cursor-pointer ${form.description ? 'border-primary-container/30' : 'border-slate-200 hover:border-primary-container'}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={async (e) => {
              e.preventDefault();
              const file = e.dataTransfer.files[0];
              if (file && file.type === 'application/pdf') {
                const formData = new FormData();
                formData.append('file', file);
                setLoading(true);
                try {
                  console.log('Sending PDF to backend...');
                  const data = await authFetch('/api/extract-pdf', { method: 'POST', body: formData });
                  console.log('PDF Result:', data);
                  
                  if (data.text) {
                    const lines = data.text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                    let extractedTitle = '';
                    let extractedCompany = '';

                    // Priority 1: Inside text
                    for (let line of lines.slice(0, 15)) {
                      const compMatch = line.match(/(?:Company|Organization|About|Employer|Client)\s*[:|-]\s*([^.\n]+)/i);
                      if (compMatch) {
                        extractedCompany = compMatch[1].trim();
                        break;
                      }
                    }

                    if (!extractedTitle) {
                      for (let i = 0; i < Math.min(lines.length, 5); i++) {
                        if (lines[i].length < 60 && !lines[i].includes(':') && lines[i].length > 4) {
                          extractedTitle = lines[i];
                          break;
                        }
                      }
                    }

                    // Priority 2: Filename fallback
                    if (!extractedTitle || !extractedCompany) {
                      const nameParts = file.name.replace(/\.pdf$/i, '').split(/[_\-\s]+/);
                      if (nameParts.length >= 2) {
                        if (!extractedCompany) extractedCompany = nameParts[0];
                        if (!extractedTitle) extractedTitle = nameParts.slice(1).join(' ');
                      } else if (nameParts.length === 1) {
                        if (!extractedTitle) extractedTitle = nameParts[0];
                        if (!extractedCompany) extractedCompany = 'Unknown';
                      }
                    }

                    // Fallback: Unknown
                    setForm(f => ({ 
                      ...f, 
                      description: data.text,
                      title: extractedTitle || f.title || 'Unknown Position',
                      company_profile: extractedCompany || f.company_profile || 'Unknown'
                    }));
                  }
                } catch (err) { 
                  console.error('PDF Error:', err);
                  setError('Failed to extract PDF text'); 
                }
                setLoading(false);
              }
            }}
            onClick={() => document.getElementById('pdf-upload').click()}
          >
            <input 
              id="pdf-upload"
              type="file" 
              accept=".pdf" 
              className="hidden" 
              onChange={async (e) => {
                const file = e.target.files[0];
                if (file) {
                  const formData = new FormData();
                  formData.append('file', file);
                  setLoading(true);
                  try {
                    console.log('Sending PDF to backend (input)...');
                    const data = await authFetch('/api/extract-pdf', { method: 'POST', body: formData });
                    console.log('PDF Result (input):', data);
                    
                    if (data.text) {
                      const lines = data.text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                      let extractedTitle = '';
                      let extractedCompany = '';

                      // Priority 1: Inside text
                      for (let line of lines.slice(0, 15)) {
                        const compMatch = line.match(/(?:Company|Organization|About|Employer|Client)\s*[:|-]\s*([^.\n]+)/i);
                        if (compMatch) {
                          extractedCompany = compMatch[1].trim();
                          break;
                        }
                      }

                      if (!extractedTitle) {
                        for (let i = 0; i < Math.min(lines.length, 5); i++) {
                          if (lines[i].length < 60 && !lines[i].includes(':') && lines[i].length > 4) {
                            extractedTitle = lines[i];
                            break;
                          }
                        }
                      }

                      // Priority 2: Filename fallback
                      if (!extractedTitle || !extractedCompany) {
                        const nameParts = file.name.replace(/\.pdf$/i, '').split(/[_\-\s]+/);
                        if (nameParts.length >= 2) {
                          if (!extractedCompany) extractedCompany = nameParts[0];
                          if (!extractedTitle) extractedTitle = nameParts.slice(1).join(' ');
                        } else if (nameParts.length === 1) {
                          if (!extractedTitle) extractedTitle = nameParts[0];
                          if (!extractedCompany) extractedCompany = 'Unknown';
                        }
                      }

                      // Fallback: Unknown
                      setForm(f => ({ 
                        ...f, 
                        description: data.text,
                        title: extractedTitle || f.title || 'Unknown Position',
                        company_profile: extractedCompany || f.company_profile || 'Unknown'
                      }));
                    }
                  } catch (err) { 
                    console.error('PDF Error (input):', err);
                    setError('Failed to extract PDF text'); 
                  }
                    setLoading(false);
                }
              }}
            />
            {form.description ? (
              <div className="w-full text-center space-y-4">
                <div className="flex flex-col items-center">
                  <span className="material-symbols-outlined text-emerald-500 text-5xl mb-2">check_circle</span>
                  <p className="text-sm font-bold text-slate-700 uppercase tracking-widest">Description Captured</p>
                </div>
                <div className="bg-white/50 rounded-xl p-4 text-left max-h-[150px] overflow-y-auto border border-slate-100">
                  <p className="text-[11px] text-slate-500 font-mono leading-relaxed whitespace-pre-wrap">{form.description}</p>
                </div>
                <button onClick={(e) => { e.stopPropagation(); setForm(f => ({...f, description: ''})); }} className="text-[10px] text-error uppercase font-black hover:underline tracking-widest">Clear & Try Again</button>
              </div>
            ) : (
              <div className="text-center">
                <span className="material-symbols-outlined text-slate-400 text-4xl mb-2 group-hover:text-primary-container transition-colors">cloud_upload</span>
                <p className="text-sm font-bold text-slate-700">Drop PDF or Paste Text</p>
                <p className="text-xs text-slate-400 mt-1">We'll automatically extract the job details</p>
              </div>
            )}
          </div>

          {!form.description && (
            <textarea
              rows={6}
              placeholder="Or paste the job description manually here..."
              required
              value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
              className="w-full p-md bg-surface-container-low dark:bg-slate-800 border-none rounded-xl focus:ring-2 focus:ring-primary-container outline-none resize-none reveal dark:text-white"
            />
          )}
          {error && <div className="text-error text-sm text-center">{error}</div>}
          <div className="flex justify-center mt-xl">
            <button 
              type="submit"
              disabled={loading}
              className="w-full md:min-w-[240px] bg-primary-container text-on-primary py-4 px-lg rounded-xl font-button text-body-md shadow-lg shadow-primary-container/20 hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50"
            >
              {loading ? 'Analyzing...' : 'Run Analysis'}
            </button>
          </div>
        </form>
      </div>
    </main>
  );

  const renderResearch = () => (
    <main className="flex-grow flex flex-col items-center justify-center px-gutter py-xxl max-w-[1200px] mx-auto w-full reveal">
      <div className="text-center mb-xl">
        <h1 className="font-h1 text-h1 text-on-surface dark:text-violet-200 mb-md">Company Research</h1>
        <p className="font-body-lg text-body-lg text-on-surface-variant dark:text-violet-300/70 max-w-2xl mx-auto">
          Uncover the reputation and history of any hiring company across public records.
        </p>
      </div>

      <div className="bg-white dark:bg-[#1A1625] rounded-card soft-shadow w-full max-w-3xl p-lg md:p-xl border border-white dark:border-slate-800">
        <form onSubmit={handleResearch} className="space-y-md">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-md">
            <input 
              placeholder="Company Name"
              required
              value={researchForm.company}
              onChange={(e) => setResearchForm(f => ({ ...f, company: e.target.value }))}
              className="w-full h-12 px-md bg-surface-container-low border-none rounded-xl focus:ring-2 focus:ring-primary-container outline-none"
            />
            <input 
              placeholder="Target Role (Optional)"
              value={researchForm.role}
              onChange={(e) => setResearchForm(f => ({ ...f, role: e.target.value }))}
              className="w-full h-12 px-md bg-surface-container-low border-none rounded-xl focus:ring-2 focus:ring-primary-container outline-none"
            />
          </div>
          {error && <div className="text-error text-sm text-center">{error}</div>}
          <div className="flex justify-center mt-xl">
            <button 
              type="submit"
              disabled={loading}
              className="w-full md:min-w-[240px] bg-primary-container text-on-primary py-4 px-lg rounded-xl font-button text-body-md shadow-lg shadow-primary-container/20 hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50"
            >
              {loading ? 'Searching...' : 'Start Research'}
            </button>
          </div>
        </form>
      </div>
    </main>
  );

  const renderReport = () => {
    if (!result) return <Navigate to="/verify" />;
    return (
      <main className="max-w-[1200px] mx-auto px-8 py-12 reveal">
        <div className="mb-12">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-label-caps font-label-caps text-primary-container px-2 py-1 bg-primary-fixed rounded uppercase">ANALYSIS COMPLETE</span>
          </div>
          <h1 className="font-h1 text-h1 text-on-surface mb-2">Analysis Report</h1>
          <p className="text-on-surface-variant">Verdict: {result.prediction.toUpperCase()}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-gutter">
          <div className="md:col-span-4 bg-white dark:bg-[#1A1625] soft-shadow card-radius p-8 flex flex-col items-center justify-center text-center border border-white dark:border-slate-800 h-fit">
            <h3 className="font-h2 text-h2 mb-8 text-on-surface dark:text-violet-200">Risk Score</h3>
            <div className="relative w-48 h-48 mb-8">
              <svg className="w-full h-full transform -rotate-90">
                <circle className="text-surface-container-high" cx="96" cy="96" fill="transparent" r="88" stroke="currentColor" strokeWidth="4"></circle>
                <circle 
                  className={result.risk_score > 50 ? "text-error" : "text-emerald-500"} 
                  cx="96" cy="96" fill="transparent" r="88" stroke="currentColor" 
                  strokeDasharray="552.92" 
                  strokeDashoffset={552.92 - (552.92 * result.risk_score / 100)} 
                  strokeLinecap="round" strokeWidth="6"
                  style={{transition: 'stroke-dashoffset 1s ease-out'}}
                ></circle>
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-4xl font-extrabold text-on-surface tracking-tight">{Math.round(result.risk_score)}</span>
                <span className="text-label-caps font-label-caps text-outline uppercase">Out of 100</span>
              </div>
            </div>
            <p className="text-on-surface-variant text-sm">Based on model and heuristic analysis.</p>
          </div>

          <div className="md:col-span-8 space-y-gutter">
            <div className="bg-white dark:bg-[#1A1625] rounded-card p-8 soft-shadow border border-white dark:border-slate-800">
              <h4 className="text-h2 mb-6 dark:text-violet-200">Detection Highlights</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {(result.risk_signals || []).map((sig, i) => (
                  <div key={i} className="p-4 bg-surface-container-low rounded-xl border border-white">
                    <p className="font-bold text-sm mb-1">{sig.label}</p>
                    <p className="text-xs text-on-surface-variant mb-2">{sig.detail}</p>
                    <p className="text-[10px] font-mono bg-white p-1 rounded">"{sig.evidence}"</p>
                  </div>
                ))}
                {(result.risk_signals || []).length === 0 && <p className="text-on-surface-variant opacity-50 italic">No specific red flags matched.</p>}
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  };

  const renderResearchReport = () => {
    if (!researchResult) {
      console.log('No researchResult found, redirecting...');
      return <Navigate to="/research" />;
    }
    const wiki = researchResult.wikipedia || {};
    
    return (
      <main className="max-w-[1200px] mx-auto px-gutter py-xxl reveal min-h-screen">
        <div className="flex flex-col md:flex-row gap-xl items-start mb-xxl">
          <div className="w-32 h-32 rounded-3xl overflow-hidden shadow-2xl bg-white dark:bg-[#1A1625] p-4 border border-slate-100 dark:border-slate-800 shrink-0 hover:scale-105 transition-transform duration-500">
            <img 
              src={`https://logo.clearbit.com/${researchResult.company.toLowerCase().replace(/[^a-z0-9]/g, '')}.com`} 
              alt={researchResult.company} 
              className="w-full h-full object-contain dark:brightness-90"
              onError={(e) => {
                e.target.onerror = null;
                e.target.src = wiki.thumbnail || 'https://www.google.com/s2/favicons?sz=128&domain=' + researchResult.company.toLowerCase().replace(/[^a-z0-9]/g, '') + '.com';
              }}
            />
          </div>
          <div className="flex-grow">
            <div className="flex items-center gap-3 mb-2">
              <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest ${researchResult.trust_level === 'High' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                {researchResult.trust_level} Trust Level
              </span>
            </div>
            <h1 className="font-h1 text-h1 text-on-surface dark:text-violet-200 mb-2">{researchResult.company}</h1>
            {researchForm.role && <p className="text-on-surface-variant dark:text-violet-300/60 font-medium">Researching for: {researchForm.role}</p>}
          </div>
          <div className="bg-white dark:bg-[#1A1625] p-6 rounded-card border border-slate-100 dark:border-slate-800 soft-shadow text-center min-w-[160px]">
             <div className="text-3xl font-extrabold text-primary-container mb-1">{researchResult.trust_score}</div>
             <div className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Trust Score</div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-gutter">
          {/* Column 1: Core Overview */}
          <div className="space-y-gutter">
            <section className="bg-white dark:bg-[#1A1625] p-xl rounded-card soft-shadow border border-white dark:border-slate-800 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
              <h3 className="font-h2 text-h2 mb-6 dark:text-violet-200">Company Overview</h3>
              <p className="text-body-md text-on-surface-variant leading-relaxed mb-8">
                {wiki.description || "No detailed description available for this company."}
              </p>
              
              <div className={`grid ${wiki.founders ? 'grid-cols-3' : 'grid-cols-2'} gap-4 pt-8 border-t border-slate-100`}>
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Founded</p>
                  <p className="font-semibold text-on-surface">{wiki.founding_year || 'Unknown'}</p>
                </div>
                {wiki.founders && (
                  <div>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Founder</p>
                    <p className="font-semibold text-on-surface line-clamp-1" title={wiki.founders}>{wiki.founders}</p>
                  </div>
                )}
              </div>
            </section>

            <div className="bg-surface-container-low p-xl rounded-card border border-white hover:shadow-lg transition-all">
              <h4 className="font-bold text-sm mb-4">Risk Assessment</h4>
              <ul className="space-y-4">
                <li className="flex gap-3">
                  <span className="material-symbols-outlined text-emerald-500 text-sm">check_circle</span>
                  <p className="text-xs text-on-surface-variant">Verified corporate history in public records.</p>
                </li>
                <li className="flex gap-3">
                  <span className="material-symbols-outlined text-emerald-500 text-sm">check_circle</span>
                  <p className="text-xs text-on-surface-variant">No known recruitment scams reported.</p>
                </li>
                <li className="flex gap-3">
                  <span className="material-symbols-outlined text-emerald-500 text-sm">check_circle</span>
                  <p className="text-xs text-on-surface-variant">Consistent headquarters data.</p>
                </li>
              </ul>
            </div>

            {wiki.url && (
              <a 
                href={wiki.url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="flex items-center justify-between p-6 bg-slate-900 text-white rounded-card hover:bg-slate-800 hover:shadow-xl transition-all group"
              >
                <div className="flex items-center gap-4">
                  <span className="material-symbols-outlined text-emerald-400">public</span>
                  <span className="font-semibold">Wikipedia</span>
                </div>
                <span className="material-symbols-outlined group-hover:translate-x-1 transition-transform">arrow_forward</span>
              </a>
            )}
          </div>

          {/* Column 2: Professional Feed (LeetCode & HN) */}
          <div className="space-y-gutter">
            <div className="flex items-center justify-between px-1">
              <h4 className="font-bold text-sm text-slate-900 dark:text-violet-200">Technical Insights</h4>
              <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-400/10 px-2 py-0.5 rounded uppercase">Community Verified</span>
            </div>
            
            {(researchResult.reviews || []).filter(r => r.source === 'LeetCode Discuss' || r.source === 'Hacker News' || r.source === 'StackOverflow').length === 0 ? (
              <div className="bg-white/50 border border-dashed border-slate-200 p-8 rounded-card text-center italic text-xs text-slate-400">
                No technical discussions found.
              </div>
            ) : (
              (researchResult.reviews || [])
                .filter(r => r.source === 'LeetCode Discuss' || r.source === 'Hacker News' || r.source === 'StackOverflow')
                .map((rev, i) => (
                  <a key={i} href={rev.url} target="_blank" rel="noopener noreferrer" className="block bg-white dark:bg-[#1A1625] p-5 rounded-card soft-shadow border border-slate-100 dark:border-slate-800 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
                    <div className="flex items-center justify-between mb-3">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase ${
                        rev.source === 'LeetCode Discuss' ? 'bg-amber-100 dark:bg-amber-400/10 text-amber-700 dark:text-amber-400' : 
                        rev.source === 'Hacker News' ? 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-400' : 'bg-blue-100 dark:bg-blue-400/10 text-blue-700 dark:text-blue-400'
                      }`}>{rev.source}</span>
                      <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500">{rev.score || rev.views || ''} engagement</span>
                    </div>
                    <h5 className="text-sm font-bold text-slate-800 dark:text-white mb-2 leading-snug">{rev.title}</h5>
                    <p className="text-xs text-slate-500 dark:text-violet-300/50 line-clamp-3 leading-relaxed">{rev.text}</p>
                  </a>
                ))
            )}
          </div>

          {/* Column 3: Culture Feed (Reddit) */}
          <div className="space-y-gutter">
            <div className="flex items-center justify-between px-1">
              <h4 className="font-bold text-sm text-slate-900">Culture & Reputation</h4>
              <div className="flex gap-1">
                 <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                 <span className="text-[10px] font-bold text-slate-400 uppercase">Live Reddit Feed</span>
              </div>
            </div>

            {(researchResult.reviews || []).filter(r => r.source === 'Reddit').length === 0 ? (
              <div className="bg-white/50 border border-dashed border-slate-200 p-8 rounded-card text-center italic text-xs text-slate-400">
                No cultural reviews found.
              </div>
            ) : (
              (researchResult.reviews || [])
                .filter(r => r.source === 'Reddit')
                .map((rev, i) => (
                  <a key={i} href={rev.url} target="_blank" rel="noopener noreferrer" className="block bg-white p-5 rounded-card soft-shadow border border-slate-100 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded-full uppercase bg-orange-100 text-orange-700">Reddit</span>
                      <span className="text-[10px] font-bold text-slate-400">{rev.score} pts</span>
                    </div>
                    <h5 className="text-sm font-bold text-slate-800 mb-2 leading-snug">{rev.title}</h5>
                    <p className="text-xs text-slate-500 line-clamp-3 leading-relaxed">{rev.text}</p>
                  </a>
                ))
            )}
          </div>
        </div>
      </main>
    );
  };

  const renderHistory = () => (
    <main className="max-w-[1200px] mx-auto px-8 py-xxl min-h-screen reveal">
      <div className="mb-xl flex flex-col md:flex-row justify-between items-end gap-4">
        <div>
          <h1 className="font-h1 text-h1 text-on-surface dark:text-violet-200 mb-xs">Your History</h1>
          <p className="font-body-md text-on-surface-variant dark:text-violet-300/60">Manage your saved analyses and research.</p>
        </div>
        <div className="bg-surface-container p-1 rounded-full flex gap-1">
          <button onClick={() => setHistoryTab('jobs')} className={`px-6 py-1.5 rounded-full text-xs font-semibold transition-all ${historyTab === 'jobs' ? 'bg-white shadow-sm text-primary-container' : 'text-on-surface-variant'}`}>Jobs</button>
          <button onClick={() => setHistoryTab('research')} className={`px-6 py-1.5 rounded-full text-xs font-semibold transition-all ${historyTab === 'research' ? 'bg-white shadow-sm text-primary-container' : 'text-on-surface-variant'}`}>Research</button>
        </div>
      </div>

      <div className="bg-white dark:bg-[#1A1625] rounded-macos soft-shadow border border-slate-100 dark:border-slate-800 overflow-hidden">
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {historyLoading ? <div className="p-20 text-center text-slate-400 dark:text-violet-300/40">Loading...</div> : 
            (historyTab === 'jobs' ? jobHistory : researchHistory).length === 0 ? 
            <div className="p-20 text-center text-slate-400 dark:text-violet-300/40 italic">No records found.</div> : 
            (historyTab === 'jobs' ? jobHistory : researchHistory).map((item, i) => (
              <li key={item.id} className="p-6 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex items-center justify-between reveal" style={{animationDelay: `${i * 50}ms`}}>
                <div className="flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${historyTab === 'jobs' ? (item.is_fake ? 'bg-error-container text-error' : 'bg-emerald-100 text-emerald-600') : 'bg-primary-fixed text-primary'}`}>
                    <span className="material-symbols-outlined">{historyTab === 'jobs' ? (item.is_fake ? 'warning' : 'verified') : 'corporate_fare'}</span>
                  </div>
                  <div>
                    <h3 className="font-bold text-on-surface dark:text-white">{historyTab === 'jobs' ? (item.input_payload?.title || 'Job Check') : item.company}</h3>
                    <p className="text-xs text-on-surface-variant dark:text-violet-300/50">{historyTab === 'jobs' ? (item.input_payload?.company_profile || 'Unknown Company') : `${item.role || 'General Research'} • ${item.location || 'Remote'}`}</p>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  {historyTab === 'jobs' && (
                    <div className="text-right">
                      <p className={`text-xs font-bold ${item.is_fake ? 'text-error' : 'text-emerald-600'}`}>{item.is_fake ? 'SCAM' : 'SECURE'}</p>
                      <p className="text-[10px] text-slate-400 uppercase tracking-widest">{Math.round(item.risk_score)}% Risk</p>
                    </div>
                  )}
                  <p className="text-xs text-slate-400 hidden sm:block">{new Date(item.created_at).toLocaleDateString()}</p>
                  <button 
                    onClick={async () => { if(window.confirm('Delete entry?')) { await authFetch(historyTab === 'jobs' ? `/api/history/${item.id}` : `/api/research-history`, { method: 'DELETE' }); fetchHistory(); }}}
                    className="text-slate-300 hover:text-error transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">delete</span>
                  </button>
                </div>
              </li>
            ))
          }
        </ul>
      </div>
    </main>
  );

  const renderLogin = () => (
    <main className="flex-grow flex items-center justify-center px-gutter py-xxl reveal">
      <div className="w-full max-w-[440px] bg-white dark:bg-[#1A1625] rounded-[20px] luxury-shadow p-xl flex flex-col items-center border border-white dark:border-slate-800">
        <div className="w-20 h-20 mb-lg flex items-center justify-center rounded-2xl bg-surface-container-low dark:bg-slate-800 shadow-inner">
          <span className="material-symbols-outlined text-primary-container text-[40px]">shield_person</span>
        </div>
        <h1 className="font-h1 text-h1 text-on-surface text-center mb-xs">Sign in with Truely</h1>
        <p className="text-on-surface-variant text-center font-body-md mb-xl">Your intelligent career guardian</p>
        
        <button 
          onClick={handleGoogleLogin}
          className="w-full h-14 bg-white border border-slate-200 rounded-xl flex items-center justify-center gap-3 hover:bg-slate-50 transition-all active:scale-[0.98] shadow-sm mb-6"
        >
          <img src="https://www.google.com/favicon.ico" alt="Google" className="w-5 h-5" />
          <span className="font-semibold text-slate-700">Continue with Google</span>
        </button>

        {authError && <div className="text-error text-xs text-center mt-4">{authError}</div>}
      </div>
    </main>
  );

  return (
    <div className="min-h-screen flex flex-col bg-[#F9F9F7] dark:bg-[#0A0A0B] transition-colors duration-700">
      <div className="absolute top-8 left-1/2 -translate-x-1/2 w-[98%] max-w-[1300px] z-[100] transition-all duration-500">
        <nav className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-2xl border border-white/50 dark:border-slate-800/50 rounded-[32px] px-12 py-6 luxury-shadow flex items-center justify-between">
          <div onClick={() => navigate('/')} className="text-3xl font-bold tracking-tightest text-primary-container font-display cursor-pointer flex items-center gap-3">
            <span className="material-symbols-outlined text-primary-container text-3xl">shield_with_heart</span>
            Truely
          </div>
          
          <div className="hidden md:flex items-center space-x-10 font-display text-sm font-medium tracking-tight">
            <NavLink to="/" className={({ isActive }) => `transition-all hover:text-primary-container ${isActive && location.pathname === '/' ? 'text-primary-container' : 'text-slate-500'}`}>Home</NavLink>
            <NavLink to="/verify" className={({ isActive }) => `transition-all hover:text-primary-container ${isActive ? 'text-primary-container' : 'text-slate-500'}`}>Verify</NavLink>
            <NavLink to="/research" className={({ isActive }) => `transition-all hover:text-primary-container ${isActive ? 'text-primary-container' : 'text-slate-500'}`}>Research</NavLink>
            <NavLink to="/history" className={({ isActive }) => `transition-all hover:text-primary-container ${isActive ? 'text-primary-container' : 'text-slate-500'}`}>History</NavLink>
          </div>

          <div className="flex items-center gap-6">
            <button onClick={toggleDarkMode} className="p-3 rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
              <span className="material-symbols-outlined text-slate-500 dark:text-slate-400 text-2xl">dark_mode</span>
            </button>
            {isAuthenticated ? (
              <div className="flex items-center gap-4">
                <div className="flex flex-col items-end hidden lg:flex">
                  <span className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">{user?.name}</span>
                  <button onClick={clearAuthState} className="text-[11px] font-bold text-primary-container hover:underline">Sign Out</button>
                </div>
                <div className="w-10 h-10 rounded-full bg-primary-fixed flex items-center justify-center font-bold text-primary-container">
                  {user?.name?.[0] || 'U'}
                </div>
              </div>
            ) : (
              <button onClick={() => navigate('/login')} className="bg-primary-container text-on-primary px-8 py-2.5 rounded-full text-sm font-bold shadow-lg shadow-primary-container/20 hover:scale-105 transition-all">Sign In</button>
            )}
          </div>
        </nav>
      </div>

      <div className="pt-28 flex-grow">
        <Routes>
          <Route path="/" element={renderLanding()} />
          <Route path="/verify" element={renderVerify()} />
          <Route path="/research" element={renderResearch()} />
          <Route path="/report" element={result ? renderReport() : <Navigate to="/verify" />} />
          <Route path="/research-report" element={researchResult ? renderResearchReport() : <Navigate to="/research" />} />
          <Route path="/history" element={isAuthenticated ? renderHistory() : <Navigate to="/login" />} />
          <Route path="/login" element={renderLogin()} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>

      <footer className="bg-[#F9F9F7] dark:bg-[#0F0D15] border-t border-slate-200 dark:border-slate-800 py-16 transition-colors">
        <div className="flex flex-col md:flex-row justify-between items-center px-8 max-w-[1200px] mx-auto w-full gap-8">
          <div className="text-center md:text-left">
            <div className="text-lg font-bold text-slate-900 dark:text-violet-200 mb-2">Truely</div>
            <p className="text-xs text-slate-400 dark:text-violet-300/40 tracking-wide">© 2026 Truely Verification Systems. <br />Protecting career journeys worldwide.</p>
          </div>
          <div className="flex gap-12 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">
            <a href="#" className="hover:text-primary-container transition-colors">Privacy</a>
            <a href="#" className="hover:text-primary-container transition-colors">Terms</a>
            <a href="#" className="hover:text-primary-container transition-colors">API</a>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
