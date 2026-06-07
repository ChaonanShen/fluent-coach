import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

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

const MESSAGE_LIST_BOTTOM_THRESHOLD_PX = 72;
const BROWSER_VOICE_READY_TIMEOUT_MS = 500;
const PREFERRED_ENGLISH_VOICE_NAME_PARTS = [
  'natural',
  'neural',
  'online',
  'google',
  'microsoft',
  'samantha',
  'daniel',
  'karen',
];

function isNearMessageListBottom(list) {
  return list.scrollHeight - list.scrollTop - list.clientHeight <= MESSAGE_LIST_BOTTOM_THRESHOLD_PX;
}

function useAutoScrollToBottom(dependency) {
  const listRef = useRef(null);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) {
      return;
    }
    list.scrollTop = list.scrollHeight;
  }, [dependency]);
  return listRef;
}

export default function App() {
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState('');
  const [customScenarioText, setCustomScenarioText] = useState('');
  const [session, setSession] = useState(null);
  const [inputText, setInputText] = useState('');
  const [mistakes, setMistakes] = useState([]);
  const [mistakeBooks, setMistakeBooks] = useState([]);
  const [selectedMistakeBookIds, setSelectedMistakeBookIds] = useState(new Set());
  const [selectedMistakeBookId, setSelectedMistakeBookId] = useState(null);
  const [mistakeBookDetail, setMistakeBookDetail] = useState(null);
  const [mistakeBookProgress, setMistakeBookProgress] = useState(null);
  const [mistakeBookState, setMistakeBookState] = useState('idle');
  const [activeMistakeTypeFilter, setActiveMistakeTypeFilter] = useState(null);
  const [turnCorrections, setTurnCorrections] = useState({});
  const [turnPronunciations, setTurnPronunciations] = useState({});
  const [turnAssessmentErrors, setTurnAssessmentErrors] = useState({});
  const [practicePronunciation, setPracticePronunciation] = useState(null);
  const [practiceReferenceText, setPracticeReferenceText] = useState('');
  const [assessedPracticeReferenceText, setAssessedPracticeReferenceText] = useState('');
  const [partialText, setPartialText] = useState('');
  const [voiceState, setVoiceState] = useState('idle');
  const [readingState, setReadingState] = useState('idle');
  const [mistakeReadingState, setMistakeReadingState] = useState({ mistakeId: null, targetType: null, status: 'idle' });
  const [mistakePracticeResults, setMistakePracticeResults] = useState({});
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
  const messageListShouldFollowRef = useRef(true);
  const pendingVoiceUserTurnIdRef = useRef(null);
  const readingRecorderRef = useRef(null);
  const readingStreamRef = useRef(null);
  const readingChunksRef = useRef([]);
  const readingCanceledRef = useRef(false);
  const browserVoiceRef = useRef(null);
  const mistakeReadingRecorderRef = useRef(null);
  const mistakeReadingStreamRef = useRef(null);
  const mistakeReadingChunksRef = useRef([]);
  const mistakeReadingCanceledRef = useRef(false);

  useEffect(() => {
    voiceStateRef.current = voiceState;
  }, [voiceState]);

  useEffect(() => {
    let active = true;
    Promise.all([request('/api/scenarios'), request('/api/mistakes'), request('/api/mistake-books')])
      .then(([scenarioBody, mistakeBody, mistakeBookBody]) => {
        if (!active) {
          return;
        }
        setScenarios(scenarioBody.scenarios);
        setSelectedScenarioId(scenarioBody.scenarios[0]?.id || '');
        setMistakes(mistakeBody.mistakes);
        setMistakeBooks(mistakeBookBody.books);
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
    mistakeReadingCanceledRef.current = true;
    stopMistakeReadingStream();
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
      return undefined;
    }
    const handleScroll = () => {
      messageListShouldFollowRef.current = isNearMessageListBottom(list);
    };
    list.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      list.removeEventListener('scroll', handleScroll);
    };
  }, [mainView]);

  const latestTurnText = turns.at(-1)?.text || '';

  useLayoutEffect(() => {
    const list = messageListRef.current;
    if (!list || !messageListShouldFollowRef.current) {
      return;
    }
    const scrollToBottom = () => {
      if (!messageListShouldFollowRef.current) {
        return;
      }
      list.scrollTop = list.scrollHeight;
      messageListShouldFollowRef.current = true;
    };
    scrollToBottom();
    if (typeof window.requestAnimationFrame !== 'function') {
      return;
    }
    const frameId = window.requestAnimationFrame(scrollToBottom);
    return () => window.cancelAnimationFrame(frameId);
  }, [latestTurnText, mainView, turns.length]);

  async function refreshMistakes() {
    const [mistakeBody, mistakeBookBody] = await Promise.all([
      request('/api/mistakes'),
      request('/api/mistake-books'),
    ]);
    setMistakes(mistakeBody.mistakes);
    setMistakeBooks(mistakeBookBody.books);
    setSelectedMistakeBookIds((current) => {
      const availableIds = new Set(mistakeBookBody.books.map((book) => book.session_id));
      return new Set([...current].filter((sessionId) => availableIds.has(sessionId)));
    });
  }

  function resetSessionDerivedState() {
    setTurnCorrections({});
    setTurnPronunciations({});
    setTurnAssessmentErrors({});
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

  function pushTurnAssessmentError(turnId, detail) {
    if (!turnId || !detail || typeof detail !== 'object') {
      return;
    }
    setTurnAssessmentErrors((current) => ({
      ...current,
      [turnId]: [detail, ...(current[turnId] || [])].slice(0, 3),
    }));
  }

  function resetCurrentTurnFeedback() {
    setAnalysisErrors([]);
    setLatestTiming(null);
  }

  async function openMistakeBook(sessionId) {
    setError('');
    setSelectedMistakeBookId(sessionId);
    setActiveMistakeTypeFilter(null);
    setMistakeBookState('loading');
    try {
      const detail = await request(`/api/mistake-books/${sessionId}`);
      setMistakeBookDetail(detail);
      setMistakeBookProgress(null);
      setMistakeBookState('ready');
      request('/api/progress')
        .then((progress) => {
          setMistakeBookProgress(progress);
        })
        .catch(() => {
          setMistakeBookProgress(null);
        });
    } catch (err) {
      handleRequestError(err, 'Mistake book failed to load.');
      setMistakeBookState('error');
    }
  }

  function closeMistakeBookDetail() {
    setSelectedMistakeBookId(null);
    setMistakeBookDetail(null);
    setMistakeBookProgress(null);
    setMistakeBookState('idle');
    setActiveMistakeTypeFilter(null);
  }

  function toggleMistakeBookSelection(sessionId) {
    setSelectedMistakeBookIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  }

  function selectAllMistakeBooks() {
    setSelectedMistakeBookIds(new Set(mistakeBooks.map((book) => book.session_id)));
  }

  function clearSelectedMistakeBooks() {
    setSelectedMistakeBookIds(new Set());
  }

  function updateDetailMistake(reviewed) {
    setMistakeBookDetail((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        turn_groups: current.turn_groups.map((group) => ({
          ...group,
          mistakes: group.mistakes.map((mistake) => (mistake.id === reviewed.id ? reviewed : mistake)),
        })),
      };
    });
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
    await speakWithBrowser(text, replyReadyAt);
  }

  async function speakWithBrowser(text, replyReadyAt) {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 0.94;
    utterance.pitch = 1;
    const voice = await resolveEnglishVoice(window.speechSynthesis, browserVoiceRef);
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
    messageListShouldFollowRef.current = true;
    setError('');
    resetSessionDerivedState();
    setStatus('Starting');
    try {
      const payload = { scenario_id: selectedScenarioId };
      if (selectedScenarioId === 'custom') {
        payload.custom_prompt = customScenarioText.trim();
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
    messageListShouldFollowRef.current = true;
    resetCurrentTurnFeedback();
    setError('');
    setStatus('Sending');
    setInputText('');
    try {
      const turnBody = await request(`/api/sessions/${session.id}/turns/text`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      setSession(turnBody.session);
      const userTurnId = turnBody.user_turn?.id || latestUserTurnId(turnBody.session);
      if (userTurnId && turnBody.grammar_result) {
        setTurnCorrections((current) => ({
          ...current,
          [userTurnId]: turnBody.grammar_result,
        }));
      }
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

  async function deleteMistake(mistakeId) {
    setError('');
    try {
      await request(`/api/mistakes/${mistakeId}`, {
        method: 'DELETE',
      });
      await refreshMistakes();
      if (selectedMistakeBookId) {
        const detail = await request(`/api/mistake-books/${selectedMistakeBookId}`);
        setMistakeBookDetail(detail);
      }
    } catch (err) {
      handleRequestError(err, 'Delete failed.');
    }
  }

  async function deleteMistakeBook(sessionId) {
    if (!sessionId) {
      return;
    }
    setError('');
    try {
      await request(`/api/mistake-books/${sessionId}`, {
        method: 'DELETE',
      });
      setSelectedMistakeBookIds((current) => {
        const next = new Set(current);
        next.delete(sessionId);
        return next;
      });
      if (selectedMistakeBookId === sessionId) {
        closeMistakeBookDetail();
      }
      await refreshMistakes();
    } catch (err) {
      handleRequestError(err, 'Delete failed.');
    }
  }

  async function deleteSelectedMistakeBooks() {
    const sessionIds = [...selectedMistakeBookIds];
    if (!sessionIds.length) {
      return;
    }
    setError('');
    try {
      await request('/api/mistake-books/delete', {
        method: 'POST',
        body: JSON.stringify({ session_ids: sessionIds }),
      });
      if (selectedMistakeBookId && sessionIds.includes(selectedMistakeBookId)) {
        closeMistakeBookDetail();
      }
      setSelectedMistakeBookIds(new Set());
      await refreshMistakes();
    } catch (err) {
      handleRequestError(err, 'Delete failed.');
    }
  }

  async function startReadingRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone recording is not supported in this browser.');
      setStatus('Error');
      return;
    }
    setError('');
    setPracticePronunciation(null);
    setAssessedPracticeReferenceText('');
    setAnalysisErrors([]);
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
    const assessment = await uploadPracticePronunciation({
      audio,
      mimeType: audio.type || mimeType || 'audio/webm',
    });
    setPracticePronunciation(assessment);
    setPracticeReferenceText(assessment.reference_text || '');
    setAssessedPracticeReferenceText(assessment.reference_text || '');
    setReadingState('idle');
    setStatus(sessionEnded ? 'Ended' : session ? 'In session' : 'Ready');
    stopReadingStream();
  }

  async function uploadPracticePronunciation({ referenceText, audio, mimeType }) {
    const body = {
      audio_base64: await blobToBase64(audio),
      mime_type: mimeType || 'audio/webm',
    };
    if (referenceText?.trim()) {
      body.reference_text = referenceText.trim();
    }
    return request('/api/pronunciation/practice/upload', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  function stopReadingStream() {
    const stream = readingStreamRef.current;
    if (!stream) {
      return;
    }
    stream.getTracks().forEach((track) => track.stop());
    readingStreamRef.current = null;
  }

  async function startMistakeReading(mistake, targetType, referenceText) {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError('Microphone recording is not supported in this browser.');
      setStatus('Error');
      return;
    }
    if (!referenceText?.trim()) {
      setError('No pronunciation text is available for this mistake.');
      return;
    }
    setError('');
    setMistakePracticeResults((current) => removeMistakePracticeResult(current, mistake.id, targetType));
    mistakeReadingCanceledRef.current = false;
    setMistakeReadingState({ mistakeId: mistake.id, targetType, status: 'requesting' });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mistakeReadingStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      mistakeReadingRecorderRef.current = recorder;
      mistakeReadingChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          mistakeReadingChunksRef.current = [...mistakeReadingChunksRef.current, event.data];
        }
      };
      recorder.onerror = () => {
        setError('Pronunciation practice recording failed.');
        cancelMistakeReading();
      };
      recorder.onstop = () => {
        if (!mistakeReadingCanceledRef.current) {
          finishMistakeReadingAssessment(mistake, targetType, referenceText, recorder.mimeType).catch((err) => {
            handleRequestError(err, 'Pronunciation practice failed.');
            setMistakeReadingState({ mistakeId: null, targetType: null, status: 'idle' });
            stopMistakeReadingStream();
          });
        }
      };
      recorder.start();
      setMistakeReadingState({ mistakeId: mistake.id, targetType, status: 'recording' });
    } catch (err) {
      setError(err?.message || 'Microphone permission was denied.');
      setMistakeReadingState({ mistakeId: null, targetType: null, status: 'idle' });
      stopMistakeReadingStream();
    }
  }

  function stopMistakeReading(mistakeId, targetType) {
    if (
      mistakeReadingState.status !== 'recording'
      || mistakeReadingState.mistakeId !== mistakeId
      || mistakeReadingState.targetType !== targetType
    ) {
      return;
    }
    setMistakeReadingState({ mistakeId, targetType, status: 'assessing' });
    const recorder = mistakeReadingRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      finishMistakeReadingAssessmentById(mistakeId, targetType).catch((err) => {
        setError(err.message);
        setMistakeReadingState({ mistakeId: null, targetType: null, status: 'idle' });
      });
      return;
    }
    if (recorder.requestData) {
      recorder.requestData();
    }
    recorder.stop();
  }

  function cancelMistakeReading() {
    mistakeReadingCanceledRef.current = true;
    const recorder = mistakeReadingRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    }
    mistakeReadingRecorderRef.current = null;
    mistakeReadingChunksRef.current = [];
    stopMistakeReadingStream();
    setMistakeReadingState({ mistakeId: null, targetType: null, status: 'idle' });
  }

  async function finishMistakeReadingAssessmentById(mistakeId, targetType, mimeType = 'audio/webm') {
    const mistake = mistakeBookDetail?.turn_groups
      ?.flatMap((group) => group.mistakes)
      .find((item) => item.id === mistakeId);
    if (!mistake) {
      throw new Error('Pronunciation mistake is no longer available.');
    }
    const target = pronunciationPracticeTargetByType(mistake, targetType);
    if (!target) {
      throw new Error('Pronunciation practice target is no longer available.');
    }
    return finishMistakeReadingAssessment(mistake, target.type, target.text, mimeType);
  }

  async function finishMistakeReadingAssessment(mistake, targetType, referenceText, mimeType = 'audio/webm') {
    const chunks = mistakeReadingChunksRef.current;
    if (!chunks.length) {
      throw new Error('No reading audio was recorded.');
    }
    const audio = chunks.length === 1 && chunks[0].arrayBuffer
      ? chunks[0]
      : new Blob(chunks, { type: mimeType || 'audio/webm' });
    const assessment = await uploadPracticePronunciation({
      referenceText,
      audio,
      mimeType: audio.type || mimeType || 'audio/webm',
    });
    setMistakePracticeResults((current) => ({
      ...current,
      [mistake.id]: {
        ...(current[mistake.id] || {}),
        [targetType]: {
          assessment,
          referenceText,
          targetType,
        },
      },
    }));
    setMistakeReadingState({ mistakeId: null, targetType: null, status: 'idle' });
    stopMistakeReadingStream();
  }

  function clearMistakePracticeResult(mistakeId, targetType) {
    setMistakePracticeResults((current) => removeMistakePracticeResult(current, mistakeId, targetType));
  }

  function stopMistakeReadingStream() {
    const stream = mistakeReadingStreamRef.current;
    if (!stream) {
      return;
    }
    stream.getTracks().forEach((track) => track.stop());
    mistakeReadingStreamRef.current = null;
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
    resetCurrentTurnFeedback();
    setStatus('Requesting mic');
    voiceCanceledRef.current = false;
    voiceErrorRef.current = false;
    pendingVoiceUserTurnIdRef.current = null;
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
        const userTurnId = message.user_turn_id || `local-user-${Date.now()}`;
        pendingVoiceUserTurnIdRef.current = userTurnId;
        const userTurn = {
          id: userTurnId,
          session_id: session.id,
          speaker: 'user',
          text: message.text,
          created_at: new Date().toISOString(),
          mode: 'audio',
          audio_path: null,
          asr_confidence: null,
        };
        flushSync(() => {
          setPartialText(message.text);
          setSession((current) => appendTurn(current, userTurn));
        });
      }
      if (message.type === 'reply.text') {
        const replyReadyAt = nowMs();
        reconcileVoiceUserTurnId(message.user_turn_id);
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
        reconcileVoiceUserTurnId(message.user_turn_id);
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
        const turnId = message.turn_id || pendingVoiceUserTurnIdRef.current;
        if (message.stage === 'pronunciation') {
          if (turnId) {
            setTurnPronunciations((current) => ({
              ...current,
              [turnId]: message.result,
            }));
          }
        } else {
          if (turnId) {
            setTurnCorrections((current) => ({
              ...current,
              [turnId]: message.result,
            }));
          }
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
        pushTurnAssessmentError(message.turn_id || pendingVoiceUserTurnIdRef.current, detail);
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
    messageListShouldFollowRef.current = true;
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

  function reconcileVoiceUserTurnId(serverTurnId) {
    const localTurnId = pendingVoiceUserTurnIdRef.current;
    if (!serverTurnId || !localTurnId || serverTurnId === localTurnId) {
      if (serverTurnId) {
        pendingVoiceUserTurnIdRef.current = serverTurnId;
      }
      return;
    }
    setSession((current) => replaceTurnId(current, localTurnId, serverTurnId));
    setTurnCorrections((current) => rekeyById(current, localTurnId, serverTurnId));
    setTurnPronunciations((current) => rekeyById(current, localTurnId, serverTurnId));
    setTurnAssessmentErrors((current) => rekeyById(current, localTurnId, serverTurnId));
    pendingVoiceUserTurnIdRef.current = serverTurnId;
  }

  const visibleMistakeTurnGroups = mistakeBookDetail
    ? filteredTurnGroups(mistakeBookDetail.turn_groups, activeMistakeTypeFilter)
    : [];

  if (mainView === 'mistakes') {
    return (
      <main className="app-shell">
        <header className="topbar">
          <div>
            <h1>Mistake Book</h1>
          </div>
          <button
            className="secondary-action topbar-action"
            onClick={() => {
              setMainView('practice');
              closeMistakeBookDetail();
            }}
            type="button"
          >
            Back to Practice
          </button>
        </header>

        {error ? <p className="inline-error">{error}</p> : null}

        <section className="mistake-book-workspace" aria-label="Mistake Book workspace">
          <section className="mistake-book" aria-label="Mistake Book">
            {selectedMistakeBookId ? (
              <div className="mistake-book-detail">
              <div className="mistake-book-detail-actions">
                <button className="secondary-action" onClick={closeMistakeBookDetail} type="button">
                  All Books
                </button>
                <button className="delete-button" onClick={() => deleteMistakeBook(selectedMistakeBookId)} type="button">
                  Delete Book
                </button>
              </div>
              {mistakeBookState === 'loading' ? <p>Loading mistake book...</p> : null}
              {mistakeBookState === 'error' ? <p>Could not load this mistake book.</p> : null}
              {mistakeBookDetail ? (
                <>
                  <div className="mistake-book-heading">
                    <h2>{mistakeBookDetail.record.title}</h2>
                    <SummaryScores summary={mistakeBookDetail.record.summary} variant="detail" />
                    <SummaryTrend progress={mistakeBookProgress} sessionId={mistakeBookDetail.record.session_id} />
                    <div className="mistake-book-counts" aria-label="Mistake counts">
                      {mistakeTypeFilters(mistakeBookDetail.record).map((item) => (
                        <button
                          aria-pressed={activeMistakeTypeFilter === item.type}
                          className={activeMistakeTypeFilter === item.type ? 'active' : ''}
                          key={item.type}
                          onClick={() => {
                            setActiveMistakeTypeFilter((current) => (current === item.type ? null : item.type));
                          }}
                          type="button"
                        >
                          {item.label} {item.count}
                        </button>
                      ))}
                    </div>
                  </div>
                  {visibleMistakeTurnGroups.length ? (
                    <div className="mistake-turn-list">
                      {visibleMistakeTurnGroups.map((group, index) => (
                        <section className="mistake-turn-group" key={group.turn?.id || `other-${index}`}>
                          <div className="mistake-list">
                            {group.mistakes.map((mistake) => {
                              const practiceTargets = pronunciationPracticeTargets(mistake);
                              return (
                                <article className="mistake-item" key={mistake.id}>
                                  <div className="mistake-item-header">
                                    <span>{mistake.subtype || mistake.type}</span>
                                    <button className="delete-button mistake-item-delete" onClick={() => deleteMistake(mistake.id)} type="button">
                                      Delete
                                    </button>
                                  </div>
                                  <div className="mistake-item-body">
                                    {mistake.type === 'pronunciation' ? null : (
                                      <>
                                        <p>{mistake.wrong}</p>
                                        <strong>{mistake.correct}</strong>
                                      </>
                                    )}
                                    {mistake.explanation_zh ? (
                                      <p className="mistake-explanation">{mistake.explanation_zh}</p>
                                    ) : null}
                                    {mistake.type === 'pronunciation' && practiceTargets.length ? (
                                      <div className="mistake-practice-targets">
                                        {practiceTargets.map((target) => (
                                          <div className="mistake-practice-target" key={target.type}>
                                            <div className="mistake-practice-target-row">
                                              <div className="mistake-target-actions">
                                                <button
                                                  aria-label={`Play ${target.type} pronunciation`}
                                                  className="icon-action pronunciation-play-action"
                                                  onClick={() => speak(target.text)}
                                                  title={`Play ${target.type} pronunciation`}
                                                  type="button"
                                                >
                                                  <PlayIcon />
                                                </button>
                                                <button
                                                  aria-label={mistakeReadingAriaLabel(mistakeReadingState, mistake.id, target.type)}
                                                  className={`icon-action mistake-record-action${
                                                    isCurrentMistakeReading(mistakeReadingState, mistake.id, target.type, 'recording')
                                                      ? ' recording'
                                                      : ''
                                                  }`}
                                                  disabled={isMistakeReadingDisabled(mistakeReadingState, mistake.id, target.type)}
                                                  onClick={() => {
                                                    if (isCurrentMistakeReading(mistakeReadingState, mistake.id, target.type, 'recording')) {
                                                      stopMistakeReading(mistake.id, target.type);
                                                      return;
                                                    }
                                                    startMistakeReading(mistake, target.type, target.text);
                                                  }}
                                                  title={mistakeReadingAriaLabel(mistakeReadingState, mistake.id, target.type)}
                                                  type="button"
                                                >
                                                  {mistakeReadingIcon(mistakeReadingState, mistake.id, target.type)}
                                                </button>
                                              </div>
                                              <p className="mistake-practice-target-text">
                                                <span>{target.label}</span>
                                                {target.text}
                                              </p>
                                            </div>
                                            {mistakePracticeResults[mistake.id]?.[target.type] ? (
                                              <div className="mistake-practice-result">
                                                <button
                                                  aria-label={`Clear ${target.type} practice result`}
                                                  className="icon-action clear-practice-result-action"
                                                  onClick={() => clearMistakePracticeResult(mistake.id, target.type)}
                                                  title={`Clear ${target.type} practice result`}
                                                  type="button"
                                                >
                                                  <ClearIcon />
                                                </button>
                                                <PronunciationResult
                                                  ariaLabel="Practice result"
                                                  assessment={mistakePracticeResults[mistake.id][target.type].assessment}
                                                />
                                              </div>
                                            ) : null}
                                          </div>
                                        ))}
                                      </div>
                                    ) : mistake.type === 'pronunciation' ? (
                                      <p>{mistake.word || mistake.wrong}</p>
                                    ) : null}
                                  </div>
                                </article>
                              );
                            })}
                          </div>
                        </section>
                      ))}
                    </div>
                  ) : (
                    <p>
                      {activeMistakeTypeFilter
                        ? `No ${activeMistakeTypeFilter} mistakes for this conversation.`
                        : 'No saved mistakes for this conversation.'}
                    </p>
                  )}
                </>
              ) : null}
              </div>
            ) : mistakeBooks.length ? (
              <>
              <div className="mistake-book-toolbar">
                <label className="mistake-book-select-all">
                  <input
                    aria-label="Select all mistake books"
                    checked={selectedMistakeBookIds.size === mistakeBooks.length}
                    onChange={(event) => {
                      if (event.target.checked) {
                        selectAllMistakeBooks();
                      } else {
                        clearSelectedMistakeBooks();
                      }
                    }}
                    type="checkbox"
                  />
                  <span>Select all</span>
                </label>
                <div className="mistake-book-bulk-actions">
                  <span>{selectedMistakeBookIds.size} selected</span>
                  <button
                    className="secondary-action"
                    disabled={!selectedMistakeBookIds.size}
                    onClick={clearSelectedMistakeBooks}
                    type="button"
                  >
                    Clear
                  </button>
                  <button
                    className="delete-button"
                    disabled={!selectedMistakeBookIds.size}
                    onClick={deleteSelectedMistakeBooks}
                    type="button"
                  >
                    Delete selected
                  </button>
                </div>
              </div>
              <div className="mistake-book-list">
                {mistakeBooks.map((book) => (
                  <article className="mistake-book-record" key={book.session_id}>
                    <label className="mistake-book-select">
                      <input
                        aria-label={`Select ${book.title}`}
                        checked={selectedMistakeBookIds.has(book.session_id)}
                        onChange={() => toggleMistakeBookSelection(book.session_id)}
                        type="checkbox"
                      />
                    </label>
                    <button
                      aria-label={`Open ${book.title}`}
                      className="mistake-book-record-main"
                      onClick={() => openMistakeBook(book.session_id)}
                      type="button"
                    >
                      <div>
                        <strong>{book.title}</strong>
                        <SummaryScores summary={book.summary} variant="overall" />
                      </div>
                      <div className="mistake-book-counts" aria-label={`${book.title} counts`}>
                        <span>{book.mistake_count} total</span>
                        <span>Grammar {book.grammar_count}</span>
                        <span>Expression {book.expression_count}</span>
                        <span>Pronunciation {book.pronunciation_count}</span>
                      </div>
                    </button>
                    <button
                      aria-label={`Delete ${book.title}`}
                      className="delete-button mistake-book-delete"
                      onClick={() => deleteMistakeBook(book.session_id)}
                      type="button"
                    >
                      Delete
                    </button>
                  </article>
                ))}
              </div>
              </>
            ) : (
              <p>No conversation mistake books yet.</p>
            )}
          </section>
          <aside className="coach-panel reading-practice-panel" aria-label="Reading Practice">
            <ReadingPracticePanel
              assessedPracticeReferenceText={assessedPracticeReferenceText}
              latestTiming={latestTiming}
              practicePronunciation={practicePronunciation}
              practiceReferenceText={practiceReferenceText}
              readingState={readingState}
              startReadingRecording={startReadingRecording}
              stopReadingRecording={stopReadingRecording}
              summary={summary}
              summaryState={summaryState}
            />
          </aside>
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
            </label>
            {selectedScenarioId === 'custom' ? (
              <label className="custom-scenario-label">
                <textarea
                  aria-label="Custom scenario"
                  disabled={sessionActive}
                  maxLength={2000}
                  onChange={(event) => setCustomScenarioText(event.target.value)}
                  placeholder="Describe the English conversation scenario you want to practice..."
                  rows={1}
                  value={customScenarioText}
                />
              </label>
            ) : (
              <div className="conversation-toolbar-fill" aria-hidden="true" />
            )}
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
            <div className="turn-actions">
              <button
                className={sessionActive ? 'secondary-action session-action' : 'primary-action session-action'}
                disabled={!canStartSession || status === 'Starting' || status === 'Ending'}
                onClick={sessionActive ? endSession : startSession}
                type="button"
              >
                {sessionActionLabel}
              </button>
              <button className="primary-action send-action" disabled={!session || !inputText.trim() || sessionEnded} type="submit">
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
            </div>
          </form>
        </section>

        <ConversationAssessmentPanel
          analysisErrors={analysisErrors}
          session={session}
          turnAssessmentErrors={turnAssessmentErrors}
          turnCorrections={turnCorrections}
          turnPronunciations={turnPronunciations}
        />

        <aside className="coach-panel reading-practice-panel" aria-label="Reading Practice">
          <ReadingPracticePanel
            assessedPracticeReferenceText={assessedPracticeReferenceText}
            latestTiming={latestTiming}
            mistakeCount={mistakes.length}
            openMistakeBook={() => setMainView('mistakes')}
            practicePronunciation={practicePronunciation}
            practiceReferenceText={practiceReferenceText}
            readingState={readingState}
            startReadingRecording={startReadingRecording}
            stopReadingRecording={stopReadingRecording}
            summary={summary}
            summaryState={summaryState}
          />
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

function replaceTurnId(session, oldId, newId) {
  if (!session || !oldId || !newId || oldId === newId) {
    return session;
  }
  if (session.turns.some((existing) => existing.id === newId)) {
    return session;
  }
  return {
    ...session,
    turns: session.turns.map((existing) => (existing.id === oldId ? { ...existing, id: newId } : existing)),
  };
}

function removeMistakePracticeResult(results, mistakeId, targetType) {
  const currentTargets = results[mistakeId] || {};
  if (!currentTargets[targetType]) {
    return results;
  }
  const nextTargets = { ...currentTargets };
  delete nextTargets[targetType];
  const nextResults = { ...results };
  if (Object.keys(nextTargets).length) {
    nextResults[mistakeId] = nextTargets;
  } else {
    delete nextResults[mistakeId];
  }
  return nextResults;
}

function rekeyById(items, oldId, newId) {
  if (!oldId || !newId || oldId === newId || !Object.prototype.hasOwnProperty.call(items, oldId)) {
    return items;
  }
  const next = { ...items };
  next[newId] = next[oldId];
  delete next[oldId];
  return next;
}

function latestUserTurnId(session) {
  return session?.turns?.filter((turn) => turn.speaker === 'user').at(-1)?.id || null;
}

function formatDateTime(value) {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function SummaryScores({ summary, variant = 'detail' }) {
  if (!summary) {
    return <p className="summary-pending">Summary pending</p>;
  }
  const items = variant === 'overall' ? overallScoreItems(summary) : detailScoreItems(summary);
  return (
    <div className="summary-score-row" aria-label={variant === 'overall' ? 'Overall score' : 'Summary scores'}>
      {items.map((item) => (
        <span key={item.label}>
          {item.label} {item.value}
        </span>
      ))}
    </div>
  );
}

function ConversationAssessmentPanel({
  analysisErrors,
  session,
  turnCorrections,
  turnPronunciations,
  turnAssessmentErrors,
}) {
  const assessmentItems = userTurnsWithAssessments(session, turnCorrections, turnPronunciations, turnAssessmentErrors);
  const assessmentListRef = useAutoScrollToBottom(assessmentItems.length);
  return (
    <aside className="coach-panel assessment-panel" aria-label="Conversation Assessment">
      <h2>Conversation Assessment</h2>
      {assessmentItems.length ? (
        <div className="assessment-feed assessment-scroll-list" aria-label="Assessment feedback" ref={assessmentListRef}>
          {assessmentItems.map((item) => (
            <TurnAssessmentItem item={item} key={item.turn.id} />
          ))}
        </div>
      ) : (
        <p className="empty-note">No assessment yet.</p>
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
    </aside>
  );
}

function TurnAssessmentItem({ item }) {
  const { turn, correction, pronunciation, errors } = item;
  return (
    <article className="turn-assessment-item">
      <AssessmentScoreRow assessment={pronunciation} />
      <div className="assessment-original">
        <span>Original</span>
        <p>{renderOriginalWithPronunciationMarks(turn.text, pronunciation)}</p>
      </div>
      <CorrectionBlock correction={correction} originalText={turn.text} />
      <TurnAssessmentErrors errors={errors} turnId={turn.id} />
    </article>
  );
}

function AssessmentScoreRow({ assessment }) {
  if (!assessment) {
    return null;
  }
  return (
    <div className="assessment-score-row" aria-label="Assessment scores">
      <span>Overall {Math.round(assessment.overall)}</span>
      <span>Accuracy {Math.round(assessment.accuracy)}</span>
      <span>Fluency {Math.round(assessment.fluency)}</span>
    </div>
  );
}

function CorrectionBlock({ correction, originalText }) {
  if (!hasMeaningfulCorrection(correction, originalText)) {
    return null;
  }
  const showCorrectedText = Boolean(
    correction?.corrected_text && normalizedText(correction.corrected_text) !== normalizedText(originalText),
  );
  const issues = correction?.issues || [];
  return (
    <div className="assessment-corrected">
      <span>Corrected</span>
      {showCorrectedText ? <p>{correction.corrected_text}</p> : null}
      {issues.length ? (
        <ul className="assessment-issues">
          {issues.map((issue, index) => (
            <li key={`${issue.type || 'issue'}-${index}`}>{issue.explanation_zh || issue.message || issue.type}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function TurnAssessmentErrors({ errors, turnId }) {
  if (!errors.length) {
    return null;
  }
  return (
    <div className="analysis-error-list">
      {errors.map((item, index) => (
        <article className="analysis-error" key={`${turnId}-${item.code}-${index}`}>
          <span>{item.stage}</span>
          <p>{item.user_message_zh || item.code}</p>
        </article>
      ))}
    </div>
  );
}

function ReadingPracticePanel({
  assessedPracticeReferenceText,
  latestTiming,
  mistakeCount,
  openMistakeBook,
  practicePronunciation,
  practiceReferenceText,
  readingState,
  startReadingRecording,
  stopReadingRecording,
  summary,
  summaryState,
}) {
  return (
    <section className="reading-practice-content">
      <h2>Reading Practice</h2>
      <textarea
        aria-label="Read transcript"
        className="read-reference-input"
        placeholder="Your spoken text will appear here after recording"
        readOnly
        rows={3}
        value={practiceReferenceText}
      />
      <button
        className="secondary-action assess-action"
        disabled={readingState === 'assessing'}
        onClick={readingState === 'recording' ? stopReadingRecording : startReadingRecording}
        type="button"
      >
        {readingState === 'recording' ? 'Stop Reading' : readingState === 'assessing' ? 'Assessing' : 'Record Reading'}
      </button>
      <PronunciationResult
        ariaLabel="Practice result"
        assessment={practicePronunciation}
        referenceLabel="Practice result"
        referenceText={assessedPracticeReferenceText}
      />
      {openMistakeBook ? (
        <section className="reading-practice-link">
          <h3>Mistake Book</h3>
          <button className="secondary-action mistake-book-action" onClick={openMistakeBook} type="button">
            Mistake Book ({mistakeCount})
          </button>
        </section>
      ) : null}
      <TimingPanel latestTiming={latestTiming} />
      <SummaryPanel summary={summary} summaryState={summaryState} />
    </section>
  );
}

function TimingPanel({ latestTiming }) {
  const timingItems = latestTiming ? timingRows(latestTiming.timings) : [];
  return (
    <section className="reading-practice-link" aria-label="Timing">
      <h3>Timing</h3>
      {timingItems.length ? (
        <div className="timing-footnote timing-section">
          <ul>
            {timingItems.map(([label, value]) => (
              <li key={label}>
                <span>{label}</span>
                <span>{formatMs(value)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="empty-note">No timing yet.</p>
      )}
    </section>
  );
}

function SummaryPanel({ summary, summaryState }) {
  if (summaryState === 'loading') {
    return (
      <section className="reading-practice-link" aria-label="Summary">
        <h3>Summary</h3>
        <p>Generating summary...</p>
      </section>
    );
  }
  if (summaryState === 'error') {
    return (
      <section className="reading-practice-link" aria-label="Summary">
        <h3>Summary</h3>
        <p>Summary is unavailable for this session.</p>
      </section>
    );
  }
  if (!summary) {
    return null;
  }
  return (
    <section className="reading-practice-link" aria-label="Summary">
      <h3>Summary</h3>
      <dl className="summary-metrics">
        {detailScoreItems(summary).map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function PronunciationResult({
  assessment,
  referenceText = '',
  ariaLabel = 'Pronunciation scores',
  referenceLabel = 'Read',
}) {
  if (!assessment) {
    return null;
  }
  return (
    <div className="pronunciation-result">
      {referenceText ? <p className="practice-reference">{referenceLabel}: {referenceText}</p> : null}
      <p className="score-label">Low-score words</p>
      <div className="word-score-list">
        {assessment.words.map((word) => (
          <span className={word.accuracy < 60 ? 'low-word' : ''} key={word.word}>
            {word.word}
          </span>
        ))}
      </div>
      <div className="score-row" aria-label={ariaLabel}>
        <span>Overall {Math.round(assessment.overall)}</span>
        <span>Accuracy {Math.round(assessment.accuracy)}</span>
        <span>Fluency {Math.round(assessment.fluency)}</span>
      </div>
    </div>
  );
}

function renderOriginalWithPronunciationMarks(text, assessment) {
  if (!assessment?.words?.length || !text) {
    return text;
  }
  const words = assessment.words.map((word) => ({
    normalized: normalizedPronunciationWord(word.word),
    isLowScore: word.accuracy < 60,
  }));
  let wordIndex = 0;
  return text.split(/(\s+)/).map((part, index) => {
    const normalizedPart = normalizedPronunciationWord(part);
    if (!normalizedPart) {
      return part;
    }
    let matchedWord = null;
    for (let index = wordIndex; index < words.length; index += 1) {
      const candidate = words[index];
      if (candidate.normalized === normalizedPart) {
        matchedWord = candidate;
        wordIndex = index + 1;
        break;
      }
    }
    if (!matchedWord?.isLowScore) {
      return part;
    }
    return (
      <span className="low-word" key={`${part}-${index}`}>
        {part}
      </span>
    );
  });
}

function normalizedPronunciationWord(value) {
  return String(value || '')
    .trim()
    .replace(/^[^A-Za-z0-9']+|[^A-Za-z0-9']+$/g, '')
    .toLowerCase();
}

function hasMeaningfulCorrection(correction, originalText) {
  if (!correction) {
    return false;
  }
  if (correction.corrected_text && normalizedText(correction.corrected_text) !== normalizedText(originalText)) {
    return true;
  }
  return Boolean(correction.issues?.length);
}

function normalizedText(value) {
  return String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();
}

function userTurnsWithAssessments(session, turnCorrections, turnPronunciations, turnAssessmentErrors) {
  return (session?.turns || [])
    .filter((turn) => turn.speaker === 'user')
    .map((turn) => ({
      turn,
      correction: turnCorrections[turn.id] || null,
      pronunciation: turnPronunciations[turn.id] || null,
      errors: turnAssessmentErrors[turn.id] || [],
    }))
    .filter(({ correction, pronunciation, errors }) => correction || pronunciation || errors.length);
}

function pronunciationPracticeTargets(mistake) {
  if (mistake?.type !== 'pronunciation') {
    return [];
  }
  const wordTarget = (mistake.word || mistake.wrong || '').trim();
  const sentenceTarget = (mistake.practice_sentence || '').trim();
  const targets = [];
  if (wordTarget) {
    targets.push({
      type: 'word',
      label: 'Word:',
      text: wordTarget,
    });
  }
  if (sentenceTarget) {
    targets.push({
      type: 'sentence',
      label: 'Practice sentence:',
      text: sentenceTarget,
    });
  }
  return targets;
}

function pronunciationPracticeTargetByType(mistake, targetType) {
  return pronunciationPracticeTargets(mistake).find((target) => target.type === targetType) || null;
}

function isCurrentMistakeReading(state, mistakeId, targetType, status = null) {
  const isCurrent = state.mistakeId === mistakeId && state.targetType === targetType;
  return status ? isCurrent && state.status === status : isCurrent;
}

function mistakeReadingAriaLabel(state, mistakeId, targetType) {
  const target = targetType === 'sentence' ? 'sentence' : 'word';
  if (!isCurrentMistakeReading(state, mistakeId, targetType)) {
    return `Record ${target}`;
  }
  if (state.status === 'recording') {
    return `Stop ${target} recording`;
  }
  if (state.status === 'assessing' || state.status === 'requesting') {
    return `Assessing ${target} recording`;
  }
  return `Record ${target}`;
}

function mistakeReadingIcon(state, mistakeId, targetType) {
  if (isCurrentMistakeReading(state, mistakeId, targetType, 'recording')) {
    return <StopIcon />;
  }
  if (
    isCurrentMistakeReading(state, mistakeId, targetType, 'assessing')
    || isCurrentMistakeReading(state, mistakeId, targetType, 'requesting')
  ) {
    return <PendingIcon />;
  }
  return <MicIcon />;
}

function isOtherMistakeReading(state, mistakeId, targetType) {
  return Boolean(
    state.mistakeId
    && state.status !== 'idle'
    && (state.mistakeId !== mistakeId || state.targetType !== targetType),
  );
}

function isMistakeReadingDisabled(state, mistakeId, targetType) {
  if (isOtherMistakeReading(state, mistakeId, targetType)) {
    return true;
  }
  return (
    state.mistakeId === mistakeId
    && state.targetType === targetType
    && !['idle', 'recording'].includes(state.status)
  );
}

function PlayIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">
      <path d="M5 3.7v8.6L11.7 8 5 3.7z" fill="currentColor" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">
      <path
        d="M8 2.2a2 2 0 0 0-2 2v3.4a2 2 0 0 0 4 0V4.2a2 2 0 0 0-2-2z"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
      <path
        d="M3.8 7.2a4.2 4.2 0 0 0 8.4 0M8 11.4v2.4M6.2 13.8h3.6"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">
      <rect fill="currentColor" height="7" rx="1" width="7" x="4.5" y="4.5" />
    </svg>
  );
}

function PendingIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">
      <circle cx="4.5" cy="8" fill="currentColor" r="1" />
      <circle cx="8" cy="8" fill="currentColor" r="1" />
      <circle cx="11.5" cy="8" fill="currentColor" r="1" />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">
      <path
        d="m4.5 4.5 7 7m0-7-7 7"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function SummaryTrend({ progress, sessionId }) {
  const trend = progress?.trend || [];
  const currentIndex = trend.findIndex((point) => point.session_id === sessionId);
  if (currentIndex === -1 || trend.length === 0) {
    return null;
  }
  if (currentIndex === 0) {
    return <p className="summary-trend-note">First scored conversation</p>;
  }
  const current = trend[currentIndex];
  const previous = trend[currentIndex - 1];
  return (
    <div className="summary-trend-row" aria-label="Score changes">
      <span>Change</span>
      {summaryDeltaItems(current, previous).map((item) => (
        <span key={item.label}>
          {item.label} {item.value}
        </span>
      ))}
    </div>
  );
}

function summaryScoreItems(summary) {
  return [
    { label: 'Grammar', value: formatScore(summary.grammar_score) },
    { label: 'Pronunciation', value: formatScore(summary.pronunciation_score) },
    { label: 'Fluency', value: formatScore(summary.fluency_score) },
    { label: 'Vocabulary', value: formatScore(summary.vocabulary_score) },
  ];
}

function overallScoreItems(summary) {
  return [{ label: 'Overall', value: formatScore(overallScore(summary)) }];
}

function detailScoreItems(summary) {
  return [
    ...overallScoreItems(summary),
    ...summaryScoreItems(summary),
  ];
}

function summaryDeltaItems(current, previous) {
  return [
    { label: 'Overall', value: formatDelta(overallScore(current), overallScore(previous)) },
    { label: 'Grammar', value: formatDelta(current.grammar_score, previous.grammar_score) },
    { label: 'Pronunciation', value: formatDelta(current.pronunciation_score, previous.pronunciation_score) },
    { label: 'Fluency', value: formatDelta(current.fluency_score, previous.fluency_score) },
    { label: 'Vocabulary', value: formatDelta(current.vocabulary_score, previous.vocabulary_score) },
  ];
}

function overallScore(summary) {
  if (!summary) {
    return null;
  }
  const weightedScores = [
    { value: summary.grammar_score, weight: 0.35 },
    { value: summary.pronunciation_score, weight: 0.25 },
    { value: summary.fluency_score, weight: 0.2 },
    { value: summary.vocabulary_score, weight: 0.2 },
  ].filter((item) => typeof item.value === 'number');
  const totalWeight = weightedScores.reduce((total, item) => total + item.weight, 0);
  if (!totalWeight) {
    return null;
  }
  return weightedScores.reduce((total, item) => total + item.value * item.weight, 0) / totalWeight;
}

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(1) : '-';
}

function formatDelta(current, previous) {
  if (typeof current !== 'number' || typeof previous !== 'number') {
    return '-';
  }
  const delta = current - previous;
  if (delta === 0) {
    return '0.0';
  }
  const prefix = delta > 0 ? '+' : '';
  return `${prefix}${delta.toFixed(1)}`;
}

function mistakeTypeFilters(record) {
  return [
    { type: 'grammar', label: 'Grammar', count: record.grammar_count },
    { type: 'expression', label: 'Expression', count: record.expression_count },
    { type: 'pronunciation', label: 'Pronunciation', count: record.pronunciation_count },
  ];
}

function filteredTurnGroups(turnGroups, activeType) {
  if (!activeType) {
    return turnGroups;
  }
  return turnGroups
    .map((group) => ({
      ...group,
      mistakes: group.mistakes.filter((mistake) => mistake.type === activeType),
    }))
    .filter((group) => group.mistakes.length > 0);
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

async function resolveEnglishVoice(speechSynthesis, voiceRef) {
  if (voiceRef.current) {
    return voiceRef.current;
  }
  const currentVoices = speechSynthesis.getVoices?.() || [];
  const preferred = choosePreferredEnglishVoice(currentVoices);
  if (preferred) {
    voiceRef.current = preferred;
    return preferred;
  }

  const loadedVoices = await waitForBrowserVoices(speechSynthesis);
  const selected = (
    choosePreferredEnglishVoice(loadedVoices)
    || chooseEnglishVoice(currentVoices)
    || chooseEnglishVoice(loadedVoices)
  );
  if (selected) {
    voiceRef.current = selected;
  }
  return selected;
}

function waitForBrowserVoices(speechSynthesis) {
  return new Promise((resolve) => {
    let settled = false;
    let timeoutId = null;
    const previousOnVoicesChanged = speechSynthesis.onvoiceschanged;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      if (typeof speechSynthesis.removeEventListener === 'function') {
        speechSynthesis.removeEventListener('voiceschanged', finish);
      }
      if (speechSynthesis.onvoiceschanged === finish) {
        speechSynthesis.onvoiceschanged = previousOnVoicesChanged || null;
      }
      resolve(speechSynthesis.getVoices?.() || []);
    };

    if (typeof speechSynthesis.addEventListener === 'function') {
      speechSynthesis.addEventListener('voiceschanged', finish);
    } else if ('onvoiceschanged' in speechSynthesis) {
      speechSynthesis.onvoiceschanged = finish;
    }
    timeoutId = window.setTimeout(finish, BROWSER_VOICE_READY_TIMEOUT_MS);
  });
}

function englishVoices(voices) {
  return voices.filter((voice) => voice.lang?.toLowerCase().startsWith('en'));
}

function choosePreferredEnglishVoice(voices) {
  const candidates = englishVoices(voices);
  return candidates.find((voice) => {
    const name = voice.name.toLowerCase();
    return PREFERRED_ENGLISH_VOICE_NAME_PARTS.some((part) => name.includes(part));
  }) || null;
}

function chooseEnglishVoice(voices) {
  const candidates = englishVoices(voices);
  if (!candidates.length) {
    return null;
  }
  return (
    choosePreferredEnglishVoice(candidates) || candidates[0]
  );
}
