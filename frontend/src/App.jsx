import { useEffect, useMemo, useRef, useState } from 'react';

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
  const [pronunciation, setPronunciation] = useState(null);
  const [partialText, setPartialText] = useState('');
  const [voiceState, setVoiceState] = useState('idle');
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState('Loading scenarios');
  const [error, setError] = useState('');
  const mediaRecorderRef = useRef(null);
  const voiceWebSocketRef = useRef(null);
  const voiceStreamRef = useRef(null);
  const pendingAudioSendsRef = useRef([]);
  const voiceCanceledRef = useRef(false);

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

  useEffect(() => () => {
    voiceCanceledRef.current = true;
    closeVoiceSocket();
    stopVoiceStream();
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

  function speak(text) {
    if (!text || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
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
      speak(turnBody.ai_turn?.text || turnBody.session.turns.at(-1)?.text);
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

  async function assessReading() {
    setError('');
    setStatus('Assessing');
    try {
      const assessment = await request('/api/pronunciation/assess', {
        method: 'POST',
        body: JSON.stringify({ fixture_id: 'speechocean_000010113' }),
      });
      setPronunciation(assessment);
      await refreshMistakes();
      setStatus(sessionEnded ? 'Ended' : session ? 'In session' : 'Ready');
    } catch (err) {
      setError(err.message);
      setStatus('Error');
    }
  }

  async function startVoiceTurn() {
    if (!session || sessionEnded) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone recording is not supported in this browser.');
      setStatus('Error');
      return;
    }
    setError('');
    setPartialText('');
    setStatus('Requesting mic');
    voiceCanceledRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      voiceStreamRef.current = stream;
      openVoiceSocket(stream);
    } catch (err) {
      setError(err?.message || 'Microphone permission was denied.');
      setStatus('Error');
      setVoiceState('idle');
      stopVoiceStream();
    }
  }

  function openVoiceSocket(stream) {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const websocket = new WebSocket(`${scheme}://${window.location.host}/ws/sessions/${session.id}/audio`);
    voiceWebSocketRef.current = websocket;
    websocket.onopen = () => {
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      pendingAudioSendsRef.current = [];
      websocket.send(JSON.stringify({ type: 'start_turn', mime_type: recorder.mimeType }));
      recorder.ondataavailable = (event) => queueAudioChunk(event.data);
      recorder.onerror = () => {
        setError('Recording failed.');
        cancelVoiceTurn();
      };
      recorder.onstop = () => {
        if (!voiceCanceledRef.current) {
          finishVoiceTurn().catch((err) => {
            setError(err.message);
            setStatus('Error');
            setVoiceState('idle');
            closeVoiceSocket();
            stopVoiceStream();
          });
        }
      };
      recorder.start(250);
      setVoiceState('recording');
      setStatus('Recording');
    };
    websocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'asr.partial') {
        setPartialText(message.text);
      }
      if (message.type === 'asr.final') {
        setPartialText(message.text);
        setSession((current) => appendTurn(current, {
          id: message.user_turn_id || `local-user-${Date.now()}`,
          session_id: session.id,
          speaker: 'user',
          text: message.text,
          created_at: new Date().toISOString(),
          mode: 'audio',
          audio_path: null,
          asr_confidence: null,
        }));
      }
      if (message.type === 'reply.text') {
        setSession((current) => appendTurn(current, {
          id: message.turn_id,
          session_id: session.id,
          speaker: 'ai',
          text: message.text,
          created_at: new Date().toISOString(),
          mode: 'text',
          audio_path: null,
          asr_confidence: null,
        }));
        speak(message.text);
      }
      if (message.type === 'analysis.result') {
        setLatestCorrection(message.result);
        refreshMistakes().catch(() => {});
        closeVoiceSocket();
      }
      if (message.type === 'error' || message.type === 'analysis.error') {
        setError(message.message || message.error?.user_message_zh || 'Analysis error');
        closeVoiceSocket();
      }
    };
    websocket.onerror = () => {
      setError('Voice connection failed.');
      setStatus('Error');
      setVoiceState('idle');
      stopVoiceStream();
    };
    websocket.onclose = () => {
      voiceWebSocketRef.current = null;
      mediaRecorderRef.current = null;
      pendingAudioSendsRef.current = [];
      stopVoiceStream();
      setVoiceState('idle');
      setStatus(sessionEnded ? 'Ended' : 'In session');
    };
  }

  function stopVoiceTurn() {
    if (voiceState !== 'recording') {
      return;
    }
    setVoiceState('processing');
    setStatus('Processing');
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      finishVoiceTurn().catch((err) => {
        setError(err.message);
        setStatus('Error');
        setVoiceState('idle');
      });
      return;
    }
    if (recorder.requestData) {
      recorder.requestData();
    }
    recorder.stop();
  }

  function cancelVoiceTurn() {
    voiceCanceledRef.current = true;
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    closeVoiceSocket();
    stopVoiceStream();
    mediaRecorderRef.current = null;
    pendingAudioSendsRef.current = [];
    setVoiceState('idle');
    setStatus(sessionEnded ? 'Ended' : session ? 'In session' : 'Ready');
  }

  function queueAudioChunk(blob) {
    if (!blob?.size) {
      return;
    }
    const sendPromise = blob.arrayBuffer().then((buffer) => {
      const websocket = voiceWebSocketRef.current;
      if (websocket?.readyState === WebSocket.OPEN && buffer.byteLength > 0) {
        websocket.send(buffer);
      }
    });
    pendingAudioSendsRef.current = [...pendingAudioSendsRef.current, sendPromise];
    sendPromise.finally(() => {
      pendingAudioSendsRef.current = pendingAudioSendsRef.current.filter((item) => item !== sendPromise);
    });
  }

  async function finishVoiceTurn() {
    await Promise.allSettled(pendingAudioSendsRef.current);
    const websocket = voiceWebSocketRef.current;
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      throw new Error('Voice connection closed before the turn finished.');
    }
    websocket.send(JSON.stringify({ type: 'end_turn' }));
    stopVoiceStream();
  }

  function closeVoiceSocket() {
    const websocket = voiceWebSocketRef.current;
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close();
    }
  }

  function stopVoiceStream() {
    const stream = voiceStreamRef.current;
    if (!stream) {
      return;
    }
    stream.getTracks().forEach((track) => track.stop());
    voiceStreamRef.current = null;
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
            <button
              className="secondary-action voice-action"
              disabled={!session || sessionEnded || voiceState === 'processing'}
              onClick={voiceState === 'recording' ? stopVoiceTurn : startVoiceTurn}
              type="button"
            >
              {voiceState === 'recording' ? 'Stop' : voiceState === 'processing' ? 'Wait' : 'Record'}
            </button>
          </form>
          {partialText ? <p className="partial-line">Partial: {partialText}</p> : null}
        </section>

        <aside className="coach-panel">
          <h2>Coach</h2>
          <section className="coach-block">
            <h3>Read Aloud</h3>
            <p className="read-reference">THEN HE WENT TO THEME PARK</p>
            <button className="secondary-action assess-action" onClick={assessReading} type="button">
              Assess Reading
            </button>
            {pronunciation ? (
              <div className="pronunciation-result">
                <dl>
                  <div>
                    <dt>Overall</dt>
                    <dd>{Math.round(pronunciation.overall)}</dd>
                  </div>
                  <div>
                    <dt>Accuracy</dt>
                    <dd>{Math.round(pronunciation.accuracy)}</dd>
                  </div>
                  <div>
                    <dt>Fluency</dt>
                    <dd>{Math.round(pronunciation.fluency)}</dd>
                  </div>
                </dl>
                <div className="word-score-list">
                  {pronunciation.words.map((word) => (
                    <span className={word.accuracy < 60 ? 'low-word' : ''} key={word.word}>
                      {word.word}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </section>
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

function appendTurn(session, turn) {
  if (!session) {
    return session;
  }
  if (session.turns.some((existing) => existing.id === turn.id)) {
    return session;
  }
  return {
    ...session,
    turns: [...session.turns, turn],
  };
}
