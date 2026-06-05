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
  const [customScenarioText, setCustomScenarioText] = useState('');
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
  const [mainView, setMainView] = useState('practice');
  const [analysisErrors, setAnalysisErrors] = useState([]);
  const [latestTiming, setLatestTiming] = useState(null);
  const [status, setStatus] = useState('Loading scenarios');
  const [error, setError] = useState('');
  const mediaRecorderRef = useRef(null);
  const messageListRef = useRef(null);
  const voiceWebSocketRef = useRef(null);
  const voiceStreamRef = useRef(null);
  const voiceStateRef = useRef('idle');
  const pendingAudioSendsRef = useRef([]);
  const streamingReplyRef = useRef(null);
  const voiceCanceledRef = useRef(false);
  const voiceErrorRef = useRef(false);
  const readingRecorderRef = useRef(null);
  const readingStreamRef = useRef(null);
  const readingChunksRef = useRef([]);
  const readingCanceledRef = useRef(false);

  useEffect(() => {
    voiceStateRef.current = voiceState;
  }, [voiceState]);

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
    readingCanceledRef.current = true;
    stopReadingStream();
  }, []);

  const selectedScenario = useMemo(() => {
    const scenario = scenarios.find((item) => item.id === selectedScenarioId);
    if (scenario || selectedScenarioId !== 'custom') {
      return scenario;
    }
    const topic = customScenarioText.trim();
    return {
      id: 'custom',
      name: 'Custom',
      user_role: topic ? `Custom practice: ${topic}` : 'Custom conversation practice',
      conversation_goals: topic
        ? [`Practice a realistic conversation about ${topic}`, 'Answer naturally and ask a follow-up question']
        : ['Describe the scenario you want to practice'],
    };
  }, [customScenarioText, scenarios, selectedScenarioId]);

  const turns = session?.turns || [];
  const sessionEnded = session?.status === 'ended';
  const sessionActive = Boolean(session && !sessionEnded);
  const sessionActionLabel = sessionActive ? 'End' : 'Start';
  const canStartSession = Boolean(
    selectedScenarioId && (selectedScenarioId !== 'custom' || customScenarioText.trim().length >= 3),
  );

  useEffect(() => {
    const list = messageListRef.current;
    if (!list) {
      return;
    }
    list.scrollTop = list.scrollHeight;
  }, [turns.length]);

  async function refreshMistakes() {
    const body = await request('/api/mistakes');
    setMistakes(body.mistakes);
  }

  function resetSessionDerivedState() {
    setLatestCorrection(null);
    setPronunciation(null);
    setPartialText('');
    setSummary(null);
    setSummaryState('idle');
    setAnalysisErrors([]);
    setLatestTiming(null);
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

  function mergeTiming(stage, timings) {
    setLatestTiming((current) => ({
      stage,
      timings: {
        ...(current?.timings || {}),
        ...timings,
      },
    }));
  }

  function recordTtsStart(replyReadyAt) {
    mergeTiming('tts', {
      reply_text_to_tts_start_ms: Math.max(0, nowMs() - replyReadyAt),
    });
  }

  async function speak(text, options = {}) {
    if (!text) {
      return;
    }
    const replyReadyAt = options.replyReadyAt ?? nowMs();
    try {
      const result = await request('/api/tts/synthesize', {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      if (result.audio_base64) {
        await playCloudAudio(result);
        recordTtsStart(replyReadyAt);
        return;
      }
    } catch {
      // Browser speech remains the local fallback when cloud TTS is unavailable.
    }
    speakWithBrowser(text, replyReadyAt);
  }

  function speakWithBrowser(text, replyReadyAt) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 0.94;
    utterance.pitch = 1;
    const voice = chooseEnglishVoice(window.speechSynthesis.getVoices?.() || []);
    if (voice) {
      utterance.voice = voice;
    }
    let started = false;
    utterance.onstart = () => {
      started = true;
      recordTtsStart(replyReadyAt);
    };
    window.speechSynthesis.speak(utterance);
    window.setTimeout(() => {
      if (!started) {
        recordTtsStart(replyReadyAt);
      }
    }, 0);
  }

  async function startSession() {
    if (!selectedScenarioId) {
      return;
    }
    setError('');
    resetSessionDerivedState();
    setStatus('Starting');
    try {
      const payload = { scenario_id: selectedScenarioId };
      if (selectedScenarioId === 'custom') {
        payload.custom_topic = customScenarioText.trim();
      }
      const body = await request('/api/sessions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setSession(body.session);
      const openingText = body.opening_line || body.session?.turns?.find((turn) => turn.speaker === 'ai')?.text;
      if (openingText) {
        speak(openingText, { replyReadyAt: nowMs() }).catch(() => {});
      }
      await refreshMistakes();
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
      speak(turnBody.ai_turn?.text || turnBody.session.turns.at(-1)?.text, { replyReadyAt: nowMs() }).catch(() => {});
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
    streamingReplyRef.current = null;
    closeVoiceSocket();
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
      voiceStateRef.current = 'recording';
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
        const replyReadyAt = nowMs();
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
        speak(message.text, { replyReadyAt }).catch(() => {});
        setVoiceState('idle');
        setStatus('In session');
      }
      if (message.type === 'reply.delta') {
        const streamId = ensureStreamingReplyId();
        setSession((current) => upsertTurnText(current, {
          id: streamId,
          session_id: session.id,
          speaker: 'ai',
          text: (streamingReplyRef.current?.text || '') + message.text,
          created_at: new Date().toISOString(),
          mode: 'text',
          audio_path: null,
          asr_confidence: null,
        }));
        streamingReplyRef.current.text = (streamingReplyRef.current.text || '') + message.text;
      }
      if (message.type === 'reply.done') {
        const replyReadyAt = nowMs();
        const streamId = ensureStreamingReplyId();
        const finalText = message.text || streamingReplyRef.current?.text || '';
        setSession((current) => replaceTurnIdAndText(current, streamId, {
          id: message.turn_id || streamId,
          session_id: session.id,
          speaker: 'ai',
          text: finalText,
          created_at: new Date().toISOString(),
          mode: 'text',
          audio_path: null,
          asr_confidence: null,
        }));
        streamingReplyRef.current = null;
        speak(finalText, { replyReadyAt }).catch(() => {});
        setVoiceState('idle');
        setStatus('In session');
      }
      if (message.type === 'analysis.result') {
        if (message.stage === 'pronunciation') {
          setPronunciation(message.result);
        } else {
          setLatestCorrection(message.result);
        }
        refreshMistakes().catch(() => {});
      }
      if (message.type === 'debug.timing') {
        mergeTiming(message.stage, message.timings || {});
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
        if (detail.stage === 'asr' || message.type === 'error') {
          setStatus('Error');
          closeVoiceSocket();
        }
        setVoiceState('idle');
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
    if (voiceStateRef.current !== 'recording') {
      return;
    }
    voiceStateRef.current = 'processing';
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
    voiceStateRef.current = 'idle';
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

  function ensureStreamingReplyId() {
    if (!streamingReplyRef.current) {
      streamingReplyRef.current = {
        id: `local-ai-stream-${Date.now()}`,
        text: '',
      };
    }
    return streamingReplyRef.current.id;
  }

  if (mainView === 'mistakes') {
    return (
      <main className="app-shell">
        <header className="topbar">
          <div>
            <h1>Mistake Book</h1>
          </div>
          <button className="secondary-action topbar-action" onClick={() => setMainView('practice')} type="button">
            Back to Practice
          </button>
        </header>

        {error ? <p className="inline-error">{error}</p> : null}

        <section className="mistake-book" aria-label="Mistake Book">
          {mistakes.length ? (
            <div className="mistake-list">
              {mistakes.map((mistake) => (
                <article className="mistake-item" key={mistake.id}>
                  <div>
                    <span>{mistake.type}</span>
                    <p>{mistake.wrong}</p>
                    <strong>{mistake.correct}</strong>
                    {mistake.explanation_zh ? <p className="mistake-explanation">{mistake.explanation_zh}</p> : null}
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
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Speaking Coach</h1>
        </div>
        <span className="status-pill">{status}</span>
      </header>

      {error ? <p className="inline-error">{error}</p> : null}

      <section className="workspace" aria-label="Practice workspace">
        <section className="conversation-panel">
          <div className="conversation-toolbar">
            <label className="scenario-select-label">
              <span>Scenario</span>
              <select
                aria-label="Scenario"
                disabled={sessionActive}
                onChange={(event) => {
                  setSelectedScenarioId(event.target.value);
                  setSession(null);
                  resetSessionDerivedState();
                }}
                value={selectedScenarioId}
              >
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>
                    {scenario.name}
                  </option>
                ))}
                <option value="custom">
                  Custom
                </option>
              </select>
              {selectedScenarioId === 'custom' ? (
                <input
                  aria-label="Custom scenario"
                  disabled={sessionActive}
                  maxLength={160}
                  onChange={(event) => setCustomScenarioText(event.target.value)}
                  placeholder="e.g. airport check-in"
                  value={customScenarioText}
                />
              ) : null}
            </label>
            <button
              className={sessionActive ? 'secondary-action session-action' : 'primary-action session-action'}
              disabled={!canStartSession || status === 'Starting' || status === 'Ending'}
              onClick={sessionActive ? endSession : startSession}
              type="button"
            >
              {sessionActionLabel}
            </button>
          </div>

          <div className="message-list" aria-label="Conversation history" ref={messageListRef}>
            {turns.map((turn) => (
              <article className={`message ${turn.speaker}`} key={turn.id}>
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
            <h3>Pronunciation</h3>
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
                <div className="score-row" aria-label="Pronunciation scores">
                  <span>Overall {Math.round(pronunciation.overall)}</span>
                  <span>Accuracy {Math.round(pronunciation.accuracy)}</span>
                  <span>Fluency {Math.round(pronunciation.fluency)}</span>
                </div>
                <p className="score-label">Low-score words</p>
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
            <h3>Mistake Book</h3>
            <button className="secondary-action mistake-book-action" onClick={() => setMainView('mistakes')} type="button">
              Mistake Book{mistakes.length ? ` (${mistakes.length})` : ''}
            </button>
          </section>

          {latestTiming ? (
            <div className="timing-footnote">
              <p>Timing:</p>
              <ul>
                {timingRows(latestTiming.timings).map(([label, value]) => (
                  <li key={label}>
                    <span>{label}</span>
                    <span>{formatMs(value)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
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

function upsertTurnText(session, turn) {
  if (!session) {
    return session;
  }
  if (!session.turns.some((existing) => existing.id === turn.id)) {
    return {
      ...session,
      turns: [...session.turns, turn],
    };
  }
  return {
    ...session,
    turns: session.turns.map((existing) => (existing.id === turn.id ? { ...existing, text: turn.text } : existing)),
  };
}

function replaceTurnIdAndText(session, oldId, turn) {
  if (!session) {
    return session;
  }
  if (!session.turns.some((existing) => existing.id === oldId)) {
    return appendTurn(session, turn);
  }
  return {
    ...session,
    turns: session.turns.map((existing) => (existing.id === oldId ? turn : existing)),
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

async function playCloudAudio(result) {
  if (!window.Audio) {
    throw new Error('Audio playback is not supported.');
  }
  const mimeType = result.mime_type || 'audio/mpeg';
  const audio = new Audio(`data:${mimeType};base64,${result.audio_base64}`);
  await audio.play();
}

function formatMs(value) {
  return value === null || value === undefined ? '-' : `${Math.round(value)} ms`;
}

function timingRows(timings) {
  return [
    ['ASR', timings.asr_ms],
    ['Reply', timings.dialogue_reply_ms],
    ['Grammar', timings.grammar_ms],
    ['Pronunciation', timings.pronunciation_ms],
    ['TTS', timings.reply_text_to_tts_start_ms],
  ].filter(([, value]) => value !== null && value !== undefined);
}

function nowMs() {
  return window.performance?.now?.() ?? Date.now();
}

function chooseEnglishVoice(voices) {
  const englishVoices = voices.filter((voice) => voice.lang?.toLowerCase().startsWith('en'));
  if (!englishVoices.length) {
    return null;
  }
  const preferredNameParts = [
    'natural',
    'neural',
    'online',
    'google',
    'microsoft',
    'samantha',
    'daniel',
    'karen',
  ];
  return (
    englishVoices.find((voice) => {
      const name = voice.name.toLowerCase();
      return preferredNameParts.some((part) => name.includes(part));
    }) || englishVoices[0]
  );
}
