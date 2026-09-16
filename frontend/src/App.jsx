import { useEffect, useRef, useState } from 'react';
import DiffViewer from 'react-diff-viewer-continued';

const API = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const steps = ['Observing', 'Diagnosing', 'Repairing', 'Verifying'];
const rateRows = [['Baseline', 'baseline_pass_rate'], ['Shuffled', 'shuffled_pass_rate'], ['Suite', 'full_suite_pass_rate']];

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (response.status === 429) throw new Error('This demo is rate-limited. Try again in a bit.');
  if (response.status === 404) throw new Error('This demo or result has expired. Start a new run.');
  if (!response.ok) throw new Error('The demo could not finish. Please try again.');
  return response.json();
}

function Results({ result }) {
  return <section className="results" aria-label="Repair results">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h2>{result.diagnosis.diagnosis_category}</h2></div>
      <span className={`badge ${result.success ? 'success' : 'failure'}`}>{result.success ? 'Repair verified' : 'Repair unsuccessful'}</span>
    </div>
    <p className="description">{result.diagnosis.diagnosis_description}</p>
    <div className="result-grid">
      <div><h3>Pass rates</h3><table><thead><tr><th>Mode</th><th>Before</th><th>After</th></tr></thead><tbody>{rateRows.map(([label, key]) => <tr key={key}><td>{label}</td><td>{result.before[key].toFixed(1)}%</td><td className="after">{result.after[key].toFixed(1)}%</td></tr>)}</tbody></table></div>
      <div className="notes"><h3>Evidence</h3><p>{result.attempts} repair attempt{result.attempts === 1 ? '' : 's'}</p><h4>Potential shared state</h4>{result.suspicious_vars.length ? <div className="flex flex-wrap gap-2">{result.suspicious_vars.map(name => <code key={name}>{name}</code>)}</div> : <p>No module variables detected. State can also hide in function defaults.</p>}</div>
    </div>
    <div className="diff-heading"><h3>The change</h3><span>Original → {result.success ? 'verified repair' : 'last evaluated patch'}</span></div>
    <div className="diff"><DiffViewer oldValue={result.original_source} newValue={result.patched_source} splitView={false} leftTitle="Original" rightTitle="Patched" showDiffOnly={false} styles={{ variables: { light: { diffViewerBackground: '#fffefa', addedBackground: '#e6f2e7', removedBackground: '#fce7df' } }, contentText: { fontSize: '13px', lineHeight: '1.7' } }} /></div>
  </section>;
}

export default function App() {
  const [demos, setDemos] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const controller = useRef(null);

  useEffect(() => {
    const abort = new AbortController();
    api('/demos', { signal: abort.signal }).then(setDemos).catch(err => { if (err.name !== 'AbortError') setError('Could not load the demo catalog. Please refresh to try again.'); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => { abort.abort(); controller.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!job?.job_id || ['complete', 'error'].includes(job.status)) return;
    const abort = new AbortController();
    let timer;
    let stopped = false;
    const poll = async () => {
      try {
        const next = await api(`/status/${encodeURIComponent(job.job_id)}`, { signal: abort.signal });
        if (stopped) return;
        setJob(next);
        if (next.status === 'complete') { setResult(next.result); setBusy(false); }
        else if (next.status === 'error') { setError(next.result?.message || 'The demo could not finish. Please try again.'); setBusy(false); }
        else timer = setTimeout(poll, 2000);
      } catch (err) {
        if (err.name !== 'AbortError') { setError(err.message); setBusy(false); }
      }
    };
    timer = setTimeout(poll, 2000);
    return () => { stopped = true; abort.abort(); clearTimeout(timer); };
  }, [job?.job_id, job?.status]);

  async function run(demo) {
    if (busy) return;
    setBusy(true); setActive(demo); setError(''); setResult(null); setJob(null);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const { job_id } = await api(`/run/${encodeURIComponent(demo.id)}`, { method: 'POST', signal: abort.signal });
      setJob({ job_id, status: 'queued', elapsed_seconds: 0 });
    } catch (err) { if (err.name !== 'AbortError') setError(err.message); setBusy(false); }
  }

  const stage = job?.status === 'queued' ? 0 : Math.min(3, Math.floor((job?.elapsed_seconds || 0) / 12));
  return <div className="page">
    <header>
      <h1>FlakeDetective<span className="title-dot" aria-hidden="true" /></h1>
      <p>An agentic approach to diagnosing and repairing flaky pytest tests.</p>
      <p className="made-with-love">Made with <span role="img" aria-label="love">♡</span> by Anusha</p>
    </header>
    <main>
      <section className="intro">
        <h2>From test evidence to a verified repair</h2>
        <p>This project explores whether repeated test runs under different execution orders
          can reveal isolation problems and guide automated repairs.</p>
        <p className="architecture-flow">Observe → Diagnose → Act → Verify → Retry if needed</p>
        <ul className="architecture-list">
          <li><strong>Execution:</strong> TestRunner launches pytest subprocesses, running the
            target alone and alongside tests in the same file, with and without shuffled order.</li>
          <li><strong>Analysis:</strong> a rule-based classifier compares pass rates to identify
            failure patterns. An AST inspector flags module-level assignments and declared globals.</li>
          <li><strong>Repair loop:</strong> the orchestrator gives the repair agent the source,
            diagnosis, and evidence. Claude proposes a patch; the tool reruns the experiments.
            Failed attempts feed their patch and failure evidence into the next attempt.</li>
        </ul>
        <p>A repair is accepted when suite and shuffled pass rates both reach 100% in the
          sampled runs. After three unsuccessful attempts, the original file is restored.</p>
      </section>
      <section className="demo-heading">
        <h2>Try a demo</h2>
        <p>Choose a small example to see the diagnosis, measured pass rates, and source changes.</p>
      </section>
      <section aria-label="Demo examples">
        {loading ? <p role="status">Loading demos…</p> : (
          <div className="cards">
            {demos.map(demo => (
              <article className={`card ${active?.id === demo.id ? 'selected' : ''}`} key={demo.id}>
                <h3>{demo.display_name}</h3>
                <p>{demo.description}</p>
                <button disabled={busy} onClick={() => run(demo)}>
                  {busy && active?.id === demo.id ? 'Running…' : 'Run Demo'}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
      {error && <div className="error" role="alert">{error}</div>}
      {busy && (
        <section className="progress" aria-live="polite">
          <h2>Running: {active?.display_name}</h2>
          <p className="steps">
            {steps.map((step, i) => (
              <span key={step}>
                {i > 0 && ' → '}
                <span className={i === stage ? 'current-step' : ''}>{step}</span>
              </span>
            ))}
          </p>
          <p>{job?.status === 'queued' ? 'Your demo is queued.' : 'Testing and checking the fix…'}
            {' '}The steps shown are estimated from elapsed time.</p>
        </section>
      )}
      {result && <Results result={result}/>}
      <section className="how">
        <h2>About this demo</h2>
        <p>The React frontend submits a demo ID to FastAPI, which runs the Python orchestrator
          on a temporary copy. Job status and results are stored in SQLite and polled by this page.</p>
        <p className="footnote">Passing these runs is a useful check, not a guarantee. Results expire after 24 hours.</p>
      </section>
    </main>
    <footer>Made with <span role="img" aria-label="love">♡</span> by Anusha</footer>
  </div>;
}
