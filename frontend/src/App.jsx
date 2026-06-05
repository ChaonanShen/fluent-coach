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
    const detail = body.detail;
    if (detail && typeof detail === 'object') {
      const error = new Error(detail.user_message_zh || detail.code || `Request failed: ${response.status}`);
      error.detail = detail;
      throw error;
    }
    throw new Error(detail || `Request failed: ${response.status}`);
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
  const [readingState, setReadingState] = useState('idle');
  const [summary, setSummary] = useState(null);
  const [summaryState, setSummaryState] = useState('idle');
  const [progress, setProgress] = useState(null);
  const [analysisErrors, setAnalysisErrors] = useState([]);
  const [status, setStatus] = useState('Loading scenarios');
  const [error, setError] = useState('');
  const mediaRecorderRef = useRef(null);
  const voiceWebSocketRef = useRef(null);
  const voiceStreamRef = useRef(null);
  const pendingAudioSendsRef = useRef([]);
  const voiceCanceledRef = useRef(false);
  const voiceErrorRef = useRef(false);
  const readingRecorderRef = useRef(null);
  const readingStreamRef = useRef(null);
  const readingChunksRef = useRef([]);
  const readingCanceledRef = useRef(false);

  useEffect(() => {
    let active = true;
    Promise.all([request('/api/scenarios'), request('/api/mistakes'), request('/api/progress')])
      .then(([scenarioBody, mistakeBody, progressBody]) => {
        if (!active) {
          return;
        }
        setScenarios(scenarioBody.scenarios);
        setSelectedScenarioId(scenarioBody.scenarios[0]?.id || '');
        setMistakes(mistakeBody.mistakes);
        setProgress(progressBody);
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
    readingCanceledRef.current = true;
    stopReadingStream();
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

  async function refreshProgress() {
    const body = await request('/api/progress');
    setProgress(body);
  }

  function resetSessionDerivedState() {
    setLatestCorrection(null);
    setPronunciation(null);
    setPartialText('');
    setSummary(null);
    setSummaryState('idle');
    setAnalysisErrors([]);
  }

  function pushAnalysisError(detail) {
    if (!detail || typeof detail !== 'object') {
      return;
    }
    setAnalysisErrors((current) => [detail, ...current].slice(0, 5));
  }

  function handleRequestError(err, fallbackMessage = 'Request failed.') {
    pushAnalysisError(err.detail);
    setError(err.message || fallbackMessage);
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
    resetSessionDerivedState();
    setStatus('Starting');
    try {
      const body = await request('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ scenario_id: selectedScenarioId }),
      });
      setSession(body.session);
      await refreshMistakes();
      await refreshProgress().catch(() => {});
      setStatus('In session');
    } catch (err) {
      handleRequestError(err);
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
      const turnBody = await request(`/api/sessions/${session.id}/turns/text`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      setSession(turnBody.session);
      setLatestCorrection(turnBody.grammar_result);
      speak(turnBody.ai_turn?.text || turnBody.session.turns.at(-1)?.text);
      await refreshMistakes();
      setStatus('In session');
    } catch (err) {
      handleRequestError(err);
      setStatus('Error');
    }
  }

  async function endSession() {
    if (!session) {
      return;
    }
    setError('');
    setStatus('Ending');
    setSummaryState('loading');
    try {
      const ended = await request(`/api/sessions/${session.id}/end`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      const sessionSummary = await request(`/api/sessions/${session.id}/summary`);
      setSession(ended.session);
      setSummary(sessionSummary);
      await refreshMistakes();
      await refreshProgress().catch(() => {});
      setSummaryState('ready');
      setStatus('Ended');
    } catch (err) {
      handleRequestError(err);
      setSummaryState('error');
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
      handleRequestError(err);
    }
  }

  async function startReadingRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone recording is not supported in this browser.');
      setStatus('Error');
      return;
    }
    setError('');
    setPronunciation(null);
    setStatus('Requesting mic');
    readingCanceledRef.current = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      readingStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      readingRecorderRef.current = recorder;
      readingChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          readingChunksRef.current = [...readingChunksRef.current, event.data];
        }
      };
      recorder.onerror = () => {
        setError('Reading recording failed.');
        cancelReadingRecording();
      };
      recorder.onstop = () => {
        if (!readingCanceledRef.current) {
          finishReadingAssessment(recorder.mimeType).catch((err) => {
            handleRequestError(err, 'Reading assessment failed.');
            setStatus('Error');
            setReadingState('idle');
            stopReadingStream();
          });
        }
      };
      recorder.start();
      setReadingState('recording');
      setStatus('Recording');
    } catch (err) {
      setError(err?.message || 'Microphone permission was denied.');
      setStatus('Error');
      setReadingState('idle');
      stopReadingStream();
    }
  }

  function stopReadingRecording() {
    if (readingState !== 'recording') {
      return;
    }
    setReadingState('assessing');
    setStatus('Assessing');
    const recorder = readingRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      finishReadingAssessment().catch((err) => {
        setError(err.message);
        setStatus('Error');
        setReadingState('idle');
      });
      return;
    }
    if (recorder.requestData) {
      recorder.requestData();
    }
    recorder.stop();
  }

  function cancelReadingRecording() {
    readingCanceledRef.current = true;
    const recorder = readingRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    readingRecorderRef.current = null;
    readingChunksRef.current = [];
    stopReadingStream();
    setReadingState('idle');
    setStatus(sessionEnded ? 'Ended' : session ? 'In session' : 'Ready');
  }

  async function finishReadingAssessment(mimeType = 'audio/webm') {
    const chunks = readingChunksRef.current;
    if (!chunks.length) {
      throw new Error('No reading audio was recorded.');
    }
    const audio = chunks.length === 1 && chunks[0].arrayBuffer
      ? chunks[0]
      : new Blob(chunks, { type: mimeType || 'audio/webm' });
    const assessment = await request('/api/pronunciation/assess/upload', {
      method: 'POST',
      body: JSON.stringify({
        reference_text: 'THEN HE WENT TO THEME PARK',
        audio_base64: await blobToBase64(audio),
        mime_type: audio.type || mimeType || 'audio/webm',
        ...(session?.id ? { session_id: session.id } : {}),
      }),
    });
    setPronunciation(assessment);
    await refreshMistakes();
    await refreshProgress().catch(() => {});
    setReadingState('idle');
    setStatus(sessionEnded ? 'Ended' : session ? 'In session' : 'Ready');
    stopReadingStream();
  }

  function stopReadingStream() {
    const stream = readingStreamRef.current;
    if (!stream) {
      return;
    }
    stream.getTracks().forEach((track) => track.stop());
    readingStreamRef.current = null;
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
    voiceErrorRef.current = false;
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
            handleRequestError(err, 'Voice turn failed.');
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
        refreshProgress().catch(() => {});
        closeVoiceSocket();
      }
      if (message.type === 'error' || message.type === 'analysis.error') {
        const detail = message.error || {
          stage: message.stage || 'asr',
          code: message.code || 'voice_error',
          user_message_zh: message.message || '语音链路暂时不可用，请重试。',
          severity: 'warning',
          fallback_applied: false,
        };
        voiceErrorRef.current = true;
        pushAnalysisError(detail);
        setError(detail.user_message_zh || message.message || 'Analysis error');
        setStatus('Error');
        setVoiceState('idle');
        closeVoiceSocket();
      }
    };
    websocket.onerror = () => {
      voiceErrorRef.current = true;
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
      if (!voiceErrorRef.current) {
        setStatus(sessionEnded ? 'Ended' : 'In session');
      }
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
                  resetSessionDerivedState();
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
            <button
              className="secondary-action assess-action"
              disabled={sessionEnded || readingState === 'assessing'}
              onClick={readingState === 'recording' ? stopReadingRecording : startReadingRecording}
              type="button"
            >
              {readingState === 'recording' ? 'Stop Reading' : readingState === 'assessing' ? 'Assessing' : 'Record Reading'}
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

          {analysisErrors.length ? (
            <section className="coach-block">
              <h3>Issues</h3>
              <div className="analysis-error-list">
                {analysisErrors.map((item, index) => (
                  <article className="analysis-error" key={`${item.code}-${index}`}>
                    <span>{item.stage}</span>
                    <p>{item.user_message_zh || item.code}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {summaryState === 'loading' ? (
            <section className="coach-block">
              <h3>Summary</h3>
              <p>Generating summary...</p>
            </section>
          ) : null}

          {summaryState === 'error' ? (
            <section className="coach-block">
              <h3>Summary</h3>
              <p>Summary is unavailable for this session.</p>
            </section>
          ) : null}

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
            <h3>Progress</h3>
            {progress?.session_count ? (
              <dl>
                <div>
                  <dt>Sessions</dt>
                  <dd>{progress.session_count}</dd>
                </div>
                <div>
                  <dt>Grammar avg</dt>
                  <dd>{formatScore(progress.average_grammar_score)}</dd>
                </div>
                <div>
                  <dt>Pronunciation avg</dt>
                  <dd>{formatScore(progress.average_pronunciation_score)}</dd>
                </div>
              </dl>
            ) : (
              <p>No completed practice history yet.</p>
            )}
          </section>

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

async function blobToBase64(blob) {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return window.btoa(binary);
}

function formatScore(value) {
  return value === null || value === undefined ? '-' : Math.round(value);
}
