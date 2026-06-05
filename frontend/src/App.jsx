import { useEffect, useMemo, useState } from 'react';

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

export default function App() {
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState('');
  const [session, setSession] = useState(null);
  const [inputText, setInputText] = useState('');
  const [latestCorrection, setLatestCorrection] = useState(null);
  const [mistakes, setMistakes] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState('Loading scenarios');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([request('/api/scenarios'), request('/api/mistakes')])
      .then(([scenarioBody, mistakeBody]) => {
        if (!active) {
          return;
        }
        setScenarios(scenarioBody.scenarios);
        setSelectedScenarioId(scenarioBody.scenarios[0]?.id || '');
        setMistakes(mistakeBody.mistakes);
        setStatus('Ready');
      })
      .catch((err) => {
        if (!active) {
          return;
        }
        setError(err.message);
        setStatus('Offline');
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId),
    [scenarios, selectedScenarioId],
  );

  const turns = session?.turns || [];
  const sessionEnded = session?.status === 'ended';

  async function refreshMistakes() {
    const body = await request('/api/mistakes');
    setMistakes(body.mistakes);
  }

  async function startSession() {
    if (!selectedScenarioId) {
      return;
    }
    setError('');
    setSummary(null);
    setLatestCorrection(null);
    setStatus('Starting');
    try {
      const body = await request('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ scenario_id: selectedScenarioId }),
      });
      setSession(body.session);
      await refreshMistakes();
      setStatus('In session');
    } catch (err) {
      setError(err.message);
      setStatus('Error');
    }
  }

  async function sendTurn(event) {
    event.preventDefault();
    const text = inputText.trim();
    if (!session || !text || sessionEnded) {
      return;
    }
    setError('');
    setStatus('Sending');
    setInputText('');
    try {
      const [turnBody, correctionBody] = await Promise.all([
        request(`/api/sessions/${session.id}/turns/text`, {
          method: 'POST',
          body: JSON.stringify({ text }),
        }),
        request('/api/grammar/check', {
          method: 'POST',
          body: JSON.stringify({
            scenario_id: session.scenario_id,
            user_text: text,
            conversation_context: turns.map((turn) => turn.text),
          }),
        }),
      ]);
      setSession(turnBody.session);
      setLatestCorrection(correctionBody);
      await refreshMistakes();
      setStatus('In session');
    } catch (err) {
      setError(err.message);
      setStatus('Error');
    }
  }

  async function endSession() {
    if (!session) {
      return;
    }
    setError('');
    setStatus('Ending');
    try {
      const ended = await request(`/api/sessions/${session.id}/end`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const sessionSummary = await request(`/api/sessions/${session.id}/summary`);
      setSession(ended.session);
      setSummary(sessionSummary);
      await refreshMistakes();
      setStatus('Ended');
    } catch (err) {
      setError(err.message);
      setStatus('Error');
    }
  }

  async function reviewMistake(mistakeId) {
    setError('');
    try {
      const reviewed = await request(`/api/mistakes/${mistakeId}/review`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      setMistakes((current) => current.map((mistake) => (mistake.id === reviewed.id ? reviewed : mistake)));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">XEngineer</p>
          <h1>AI English Speaking Coach</h1>
        </div>
        <span className="status-pill">{status}</span>
      </header>

      {error ? <p className="inline-error">{error}</p> : null}

      <section className="workspace" aria-label="Practice workspace">
        <aside className="scenario-panel">
          <h2>Scenario</h2>
          <div className="scenario-list">
            {scenarios.map((scenario) => (
              <button
                className={scenario.id === selectedScenarioId ? 'scenario-button active' : 'scenario-button'}
                key={scenario.id}
                onClick={() => {
                  setSelectedScenarioId(scenario.id);
                  setSession(null);
                  setLatestCorrection(null);
                  setSummary(null);
                }}
                type="button"
              >
                {scenario.name}
              </button>
            ))}
          </div>

          {selectedScenario ? (
            <div className="scenario-detail">
              <h3>{selectedScenario.user_role}</h3>
              <ul>
                {selectedScenario.conversation_goals.map((goal) => (
                  <li key={goal}>{goal}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <button className="primary-action" disabled={!selectedScenarioId} onClick={startSession} type="button">
            Start
          </button>
        </aside>

        <section className="conversation-panel">
          <div className="panel-heading">
            <h2>Conversation</h2>
            <button className="secondary-action" disabled={!session || sessionEnded} onClick={endSession} type="button">
              End
            </button>
          </div>

          <div className="message-list">
            {turns.map((turn) => (
              <article className={`message ${turn.speaker}`} key={turn.id}>
                <span>{turn.speaker === 'ai' ? 'AI' : 'You'}</span>
                <p>{turn.text}</p>
              </article>
            ))}
          </div>

          <form className="turn-form" onSubmit={sendTurn}>
            <textarea
              aria-label="Your reply"
              disabled={!session || sessionEnded}
              onChange={(event) => setInputText(event.target.value)}
              placeholder="Type your reply"
              rows={3}
              value={inputText}
            />
            <button className="primary-action" disabled={!session || !inputText.trim() || sessionEnded} type="submit">
              Send
            </button>
          </form>
        </section>

        <aside className="coach-panel">
          <h2>Coach</h2>
          {latestCorrection?.issues?.length ? (
            <section className="coach-block">
              <h3>Correction</h3>
              <p className="corrected">{latestCorrection.corrected_text}</p>
              <p>{latestCorrection.issues[0].explanation_zh}</p>
            </section>
          ) : (
            <section className="coach-block">
              <h3>Correction</h3>
              <p>No issue on the latest turn.</p>
            </section>
          )}

          {summary ? (
            <section className="coach-block">
              <h3>Summary</h3>
              <dl>
                <div>
                  <dt>Grammar</dt>
                  <dd>{summary.grammar_score ?? '-'}</dd>
                </div>
                <div>
                  <dt>Pronunciation</dt>
                  <dd>{summary.pronunciation_score ?? '-'}</dd>
                </div>
                <div>
                  <dt>Tasks</dt>
                  <dd>{Math.round(summary.task_completion_rate * 100)}%</dd>
                </div>
              </dl>
              <ul className="drill-list">
                {summary.next_drills.map((drill) => (
                  <li key={drill}>{drill}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="coach-block">
            <h3>Mistakes</h3>
            {mistakes.length ? (
              <div className="mistake-list">
                {mistakes.slice(0, 5).map((mistake) => (
                  <article className="mistake-item" key={mistake.id}>
                    <div>
                      <span>{mistake.type}</span>
                      <p>{mistake.wrong}</p>
                      <strong>{mistake.correct}</strong>
                    </div>
                    <button className="review-button" onClick={() => reviewMistake(mistake.id)} type="button">
                      Review {mistake.review_count}
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <p>No saved mistakes yet.</p>
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}
