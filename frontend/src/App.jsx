import { useEffect, useState } from 'react';
import DiffViewer from 'react-diff-viewer-continued';

const rateRows = [['Baseline', 'baseline_pass_rate'], ['Shuffled', 'shuffled_pass_rate'], ['Suite', 'full_suite_pass_rate']];

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
    <details className="source-preview">
      <summary>Read the full original test</summary>
      <pre>{result.original_source}</pre>
    </details>
    <details className="source-preview">
      <summary>Read the full {result.success ? 'patched test' : 'last evaluated patch'}</summary>
      <pre>{result.patched_source}</pre>
    </details>
    <div className="diff-heading"><h3>Before and after</h3><span>Red: original lines · Green: added lines</span></div>
    <div className="diff"><DiffViewer oldValue={result.original_source} newValue={result.patched_source} splitView={false} leftTitle="Original" rightTitle="Patched" showDiffOnly={false} styles={{ variables: { light: { diffViewerBackground: '#fffefa', addedBackground: '#e6f2e7', removedBackground: '#fce7df' } }, contentText: { fontSize: '13px', lineHeight: '1.7' } }} /></div>
  </section>;
}

function ActivityLog({ events }) {
  if (!events?.length) return null;
  return <section className="activity-log" aria-label="Execution activity">
    <h2>Recorded run log</h2>
    <p>Tool actions and measured results from the original run. Times show elapsed time during that run.</p>
    <ol>{events.map((event, i) => (
      <li key={i}><span className="event-time">{event.elapsed_seconds.toFixed(1)}s</span> {event.message}</li>
    ))}</ol>
  </section>;
}

export default function App() {
  const [demos, setDemos] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(null);
  const [result, setResult] = useState(null);
  const [replay, setReplay] = useState(null);
  const [visibleEvents, setVisibleEvents] = useState(0);

  useEffect(() => {
    if (!replay) return;
    let count = 0;
    const timer = setInterval(() => {
      count += 1;
      setVisibleEvents(count);
      if (count >= (replay.result.activity?.length || 0)) {
        setResult(replay.result);
        setReplay(null);
      }
    }, 500);
    return () => clearInterval(timer);
  }, [replay]);

  useEffect(() => {
    const abort = new AbortController();
    fetch(`${import.meta.env.BASE_URL}recordings/demos.json`, { signal: abort.signal })
      .then(response => {
        if (!response.ok) throw new Error('Recording catalog unavailable');
        return response.json();
      })
      .then(recordings => {
        if (!Array.isArray(recordings) || !recordings.length ||
            recordings.some(demo => !demo.id || !demo.result || !demo.original_source)) {
          throw new Error('Invalid recording catalog');
        }
        setDemos(recordings);
      })
      .catch(err => {
        if (err.name !== 'AbortError') setError('Could not load the recordings. Please refresh to try again.');
      })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, []);

  function viewDemo(demo) {
    if (replay) return;
    setActive(demo);
    setResult(null);
    setVisibleEvents(0);
    setReplay(demo);
    setError('');
  }

  function skipReplay() {
    setResult(replay.result);
    setReplay(null);
  }

  const events = result?.activity || replay?.result.activity?.slice(0, visibleEvents) || [];
  const phase = events.at(-1)?.phase || 'observing';
  const stages = [['observing', 'Observe'], ['diagnosing', 'Diagnose'], ['repairing', 'Repair'], ['verifying', 'Verify']];
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
        <h2>Explore a recorded demo</h2>
        <p>Captured from real local FlakeDetective runs.</p>
      </section>
      <section aria-label="Demo examples">
        {loading ? <p role="status">Loading demos…</p> : (
          <div className="cards">
            {demos.map(demo => (
              <article className={`card ${active?.id === demo.id ? 'selected' : ''}`} key={demo.id}>
                <h3>{demo.display_name}</h3>
                <p>{demo.description}</p>
                <details className="source-preview">
                  <summary>View original test</summary>
                  <p>Target: <code>{demo.target_test.split('::')[1]}</code></p>
                  <pre>{demo.original_source}</pre>
                </details>
                <button disabled={!!replay} onClick={() => viewDemo(demo)}>
                  {replay?.id === demo.id ? 'Replaying…' : 'Replay demo'}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
      {error && <div className="error" role="alert">{error}</div>}
      {active && (
        <section className="test-context">
          <h2>The test in this recording</h2>
          <p>Recorded {new Date(active.recorded_at).toLocaleDateString()} · {active.runs} runs per mode. These are saved results, not a live repair.</p>
          <p>{active.description}</p>
          <p>Target: <code>{active.target_test.split('::')[1]}</code>. The other tests in this file provide its execution context.</p>
          <details className="source-preview" open>
            <summary>Original source</summary>
            <pre>{active.original_source}</pre>
          </details>
        </section>
      )}
      {replay && (
        <section className="progress" role="status" aria-live="polite">
          <h2>Replaying recorded run</h2>
          <p className="steps">{stages.map(([key, label], i) => (
            <span key={key}>{i > 0 && ' → '}<span className={phase === key ? 'current-step' : ''}>{label}</span></span>
          ))}</p>
          <p>{events.at(-1)?.message || 'Starting the recorded walkthrough…'}</p>
          <button onClick={skipReplay}>Skip to results</button>
        </section>
      )}
      <ActivityLog events={events}/>
      {result && <Results result={result}/>}
      <section className="how">
        <h2>Behind FlakeDetective</h2>
        <p>FlakeDetective combines controlled test experiments, static analysis, and an AI repair
          agent in a bounded feedback loop. The Python orchestrator decides when to retry,
          accept a patch, or restore the original file using measured test outcomes.</p>
        <p className="architecture-flow">React → FastAPI → Python orchestrator → pytest sandbox<br />
          SQLite stores jobs · Claude proposes repairs · pytest checks them</p>
        <ul className="architecture-list">
          <li><strong>API and job lifecycle:</strong> the live FastAPI backend accepts a curated
            demo ID, creates a temporary copy, and queues execution. SQLite stores job status,
            timestamps, results, and submission limits. The frontend can poll for progress;
            an asyncio cleanup task removes jobs and their working directories after 24 hours,
            sweeping on startup and hourly.</li>
          <li><strong>Evidence before generation:</strong> separate pytest subprocesses measure
            isolated, shuffled, and file-order behavior. The classifier identifies patterns
            from those pass rates, while AST analysis flags possible shared state. Both become
            context for the repair agent.</li>
          <li><strong>Repair and verification:</strong> Claude returns a complete Python file,
            which is checked for valid syntax before execution. Each patch is tested again;
            failed patches and failure evidence inform the next attempt, up to three attempts.
            The original file is backed up and restored if no repair verifies.</li>
          <li><strong>Execution boundaries:</strong> the Docker Compose deployment uses a
            Bubblewrap sandbox, resource limits, and an Anthropic-only network proxy.
            Requests select predefined demos rather than uploading executable code, and
            public results exclude raw traces and private execution details.</li>
        </ul>
        <p><strong>This portfolio version:</strong> React replays saved results from real local
          runs, so the public page needs no backend or API key. The architecture above describes
          the implemented live backend and CLI; SQLite and the sandbox are used in the live
          deployment, rather than during this recorded replay.</p>
        <p className="footnote">Passing these sampled runs is a useful check, not a guarantee.</p>
      </section>
    </main>
    <footer>Made with <span role="img" aria-label="love">♡</span> by Anusha</footer>
  </div>;
}
