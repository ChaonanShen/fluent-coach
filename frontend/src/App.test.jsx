import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import App from './App.jsx';

const scenario = {
  id: 'interview',
  name: 'Job Interview',
  ai_role: 'Hiring manager',
  user_role: 'Candidate',
  opening_line: 'Good morning. Could you start by briefly introducing yourself?',
  conversation_goals: ['Introduce professional background clearly'],
  target_expressions: ['I have worked on...'],
  correction_focus: ['past tense'],
  summary_rubric: { grammar: 'Accuracy' },
};

const openingTurn = {
  id: 'turn_ai_1',
  session_id: 'session_1',
  speaker: 'ai',
  text: scenario.opening_line,
  created_at: '2026-06-05T00:00:00Z',
  mode: 'text',
  audio_path: null,
  asr_confidence: null,
};

let pronunciationUploadFails = false;
let cloudTtsEnabled = false;
let sessionRequestBodies = [];

beforeEach(() => {
  pronunciationUploadFails = false;
  cloudTtsEnabled = false;
  sessionRequestBodies = [];
  window.speechSynthesis = {
    cancel: vi.fn(),
    getVoices: vi.fn(() => [
      { name: 'Compact Voice', lang: 'en-US' },
      { name: 'Google US English', lang: 'en-US' },
      { name: 'Mandarin', lang: 'zh-CN' },
    ]),
    speak: vi.fn(),
  };
  window.SpeechSynthesisUtterance = vi.fn(function utterance(text) {
    this.text = text;
  });
  window.Audio = vi.fn(function audio(src) {
    this.src = src;
    this.play = vi.fn(() => Promise.resolve());
  });
  global.fetch = vi.fn(async (url, options = {}) => {
    if (url === '/api/scenarios') {
      return jsonResponse({ scenarios: [scenario] });
    }
    if (url === '/api/mistakes') {
      return jsonResponse({
        mistakes: [
          {
            id: 'mistake_1',
            type: 'grammar',
            wrong: 'am working',
            correct: 'have been working',
            explanation_zh: '时态错误。',
            practice_sentence: 'I have been working in this field for three years.',
            word: null,
            phoneme: null,
            mastery: 0.1,
            review_count: 0,
            created_at: '2026-06-05T00:00:04Z',
          },
        ],
      });
    }
    if (url === '/api/tts/synthesize') {
      if (cloudTtsEnabled) {
        return jsonResponse({
          provider: 'openai_compatible',
          text: JSON.parse(options.body).text,
          audio_url: null,
          audio_base64: 'YXVkaW8=',
          mime_type: 'audio/mpeg',
          fallback_applied: false,
        });
      }
      return jsonResponse({
        provider: 'browser',
        text: JSON.parse(options.body).text,
        audio_url: null,
        audio_base64: null,
        mime_type: null,
        fallback_applied: true,
      });
    }
    if (url === '/api/mistakes/mistake_1/review') {
      return jsonResponse({
        id: 'mistake_1',
        type: 'grammar',
        wrong: 'am working',
        correct: 'have been working',
        explanation_zh: '时态错误。',
        practice_sentence: 'I have been working in this field for three years.',
        word: null,
        phoneme: null,
        mastery: 0.25,
        review_count: 1,
        created_at: '2026-06-05T00:00:04Z',
      });
    }
    if (url === '/api/sessions') {
      const requestBody = JSON.parse(options.body);
      sessionRequestBodies.push(requestBody);
      if (requestBody.scenario_id === 'custom') {
        const customScenario = {
          ...scenario,
          id: 'custom_airport',
          name: 'Custom',
          user_role: `Learner practicing: ${requestBody.custom_topic}`,
          opening_line: `Let's practice ${requestBody.custom_topic}. Could you start with what you want to say first?`,
          conversation_goals: [`Practice a realistic conversation about ${requestBody.custom_topic}`],
        };
        return jsonResponse({
          session: {
            id: 'session_1',
            scenario_id: 'custom_airport',
            custom_scenario: customScenario,
            status: 'active',
            created_at: '2026-06-05T00:00:00Z',
            ended_at: null,
            turns: [{
              ...openingTurn,
              text: customScenario.opening_line,
            }],
          },
          scenario: customScenario,
          opening_line: customScenario.opening_line,
          conversation_goals: customScenario.conversation_goals,
          target_expressions: customScenario.target_expressions,
        });
      }
      return jsonResponse({
        session: {
          id: 'session_1',
          scenario_id: 'interview',
          custom_scenario: null,
          status: 'active',
          created_at: '2026-06-05T00:00:00Z',
          ended_at: null,
          turns: [openingTurn],
        },
        scenario,
        opening_line: scenario.opening_line,
        conversation_goals: scenario.conversation_goals,
        target_expressions: scenario.target_expressions,
      });
    }
    if (url === '/api/sessions/session_1/turns/text') {
      const body = JSON.parse(options.body);
      return jsonResponse({
        session: {
          id: 'session_1',
          scenario_id: 'interview',
          status: 'active',
          created_at: '2026-06-05T00:00:00Z',
          ended_at: null,
          turns: [
            openingTurn,
            {
              id: 'turn_user_1',
              session_id: 'session_1',
              speaker: 'user',
              text: body.text,
              created_at: '2026-06-05T00:00:01Z',
              mode: 'text',
              audio_path: null,
              asr_confidence: null,
            },
            {
              id: 'turn_ai_2',
              session_id: 'session_1',
              speaker: 'ai',
              text: 'Great. Which project is most relevant to this role?',
              created_at: '2026-06-05T00:00:02Z',
              mode: 'text',
              audio_path: null,
              asr_confidence: null,
            },
          ],
        },
        user_turn: {},
        ai_turn: {},
        current_goal: scenario.conversation_goals[0],
        next_intent: 'continue_fixture_dialogue',
        grammar_result: grammarCorrection(),
      });
    }
    if (url === '/api/sessions/session_1/end') {
      return jsonResponse({
        session: {
          id: 'session_1',
          scenario_id: 'interview',
          status: 'ended',
          created_at: '2026-06-05T00:00:00Z',
          ended_at: '2026-06-05T00:00:09Z',
          turns: [openingTurn],
        },
        scenario,
        opening_line: scenario.opening_line,
        conversation_goals: scenario.conversation_goals,
        target_expressions: scenario.target_expressions,
      });
    }
    if (url === '/api/sessions/session_1/summary') {
      return jsonResponse({
        id: 'summary_1',
        session_id: 'session_1',
        grammar_score: 100,
        pronunciation_score: null,
        fluency_score: 70,
        vocabulary_score: 76,
        task_completion_rate: 0.5,
        top_issues: [],
        next_drills: ['Practice using: I have worked on...'],
        created_at: '2026-06-05T00:00:10Z',
      });
    }
    if (url === '/api/pronunciation/assess/upload') {
      if (pronunciationUploadFails) {
        return Promise.resolve({
          ok: false,
          status: 502,
          json: () => Promise.resolve({
            detail: {
              stage: 'pronunciation',
              code: 'provider_timeout',
              user_message_zh: '腾讯云发音评测超时，请稍后重试。',
              severity: 'warning',
              fallback_applied: false,
            },
          }),
        });
      }
      const body = JSON.parse(options.body);
      if (!body.audio_base64 || body.reference_text !== 'THEN HE WENT TO THEME PARK') {
        throw new Error('Invalid pronunciation upload payload');
      }
      return jsonResponse({
        id: 'assessment_1',
        provider: 'mock',
        reference_text: 'THEN HE WENT TO THEME PARK',
        audio_file: 'audio/public/speechocean762_subset/speechocean_000010113.wav',
        overall: 50,
        accuracy: 60,
        fluency: 90,
        prosody: 80,
        completeness: 100,
        words: [
          { word: 'THEN', accuracy: 100, fluency: null, phonemes: [], issue: null },
          { word: 'THEME', accuracy: 20, fluency: null, phonemes: [], issue: 'low_accuracy' },
        ],
        issues: [],
        created_at: '2026-06-05T00:00:05Z',
      });
    }
    throw new Error(`Unhandled request: ${url}`);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test('loads scenarios and starts a session', async () => {
  render(<App />);

  expect(await screen.findByRole('heading', { name: 'Speaking Coach' })).toBeInTheDocument();
  expect(await screen.findByRole('combobox', { name: 'Scenario' })).toHaveValue('interview');
  expect(screen.queryByText('XEngineer')).not.toBeInTheDocument();
  expect(screen.queryByText('Candidate')).not.toBeInTheDocument();
  expect(screen.queryByText('Introduce professional background clearly')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Mistake Book (1)' })).toBeInTheDocument();
  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  expect(screen.queryByText('Progress')).not.toBeInTheDocument();
  expect(screen.queryByText('Sessions')).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Conversation' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Conversation history')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText(scenario.opening_line)).toBeInTheDocument();
  expect(screen.queryByText('AI')).not.toBeInTheDocument();
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
  expect(window.speechSynthesis.speak.mock.calls.at(-1)[0].text).toBe(scenario.opening_line);
  expect(screen.getByRole('button', { name: 'End' })).toBeInTheDocument();
});

test('starts a custom scenario from the conversation toolbar', async () => {
  render(<App />);

  fireEvent.change(await screen.findByRole('combobox', { name: 'Scenario' }), {
    target: { value: 'custom' },
  });
  expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Custom scenario'), {
    target: { value: 'airport check-in' },
  });
  expect(screen.queryByText('Practice a realistic conversation about airport check-in')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText("Let's practice airport check-in. Could you start with what you want to say first?"))
    .toBeInTheDocument();
  expect(sessionRequestBodies.at(-1)).toEqual({
    scenario_id: 'custom',
    custom_topic: 'airport check-in',
  });
});

test('sends a text turn and shows correction feedback', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  expect(await screen.findByText('Great. Which project is most relevant to this role?')).toBeInTheDocument();
  expect(screen.getByText('I have been working in this field for three years.')).toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalledWith('/api/grammar/check', expect.any(Object));
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
  const utterance = window.speechSynthesis.speak.mock.calls.at(-1)[0];
  expect(utterance.lang).toBe('en-US');
  expect(utterance.rate).toBe(0.94);
  expect(utterance.voice.name).toBe('Google US English');
});

test('keeps the latest message visible when new turns arrive near the bottom', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  const history = screen.getByLabelText('Conversation history');
  setScrollMetrics(history, { clientHeight: 320, scrollHeight: 900 });
  history.scrollTop = 580;
  fireEvent.scroll(history);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  setScrollMetrics(history, { clientHeight: 320, scrollHeight: 1250 });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  await screen.findByText('Great. Which project is most relevant to this role?');
  await waitFor(() => expect(history.scrollTop).toBe(1250));
});

test('does not force-scroll delayed replies when the user is reading older messages', async () => {
  const voice = installVoiceMocks({ delayedReply: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  const history = screen.getByLabelText('Conversation history');
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));
  await screen.findByText('I have worked on backend systems for three years.');

  setScrollMetrics(history, { clientHeight: 320, scrollHeight: 900 });
  history.scrollTop = 100;
  fireEvent.scroll(history);
  setScrollMetrics(history, { clientHeight: 320, scrollHeight: 1250 });

  await screen.findByText('Thanks for sharing that project. What impact did it have?');
  expect(history.scrollTop).toBe(100);
});

test('plays cloud TTS audio when the backend returns audio', async () => {
  cloudTtsEnabled = true;
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I have worked on backend systems for three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  await waitFor(() => expect(window.Audio).toHaveBeenCalledWith('data:audio/mpeg;base64,YXVkaW8='));
  expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(0);
});

test('reviews a saved mistake', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (1)' }));
  expect(await screen.findByRole('heading', { name: 'Mistake Book' })).toBeInTheDocument();
  expect(screen.getByText('am working')).toBeInTheDocument();
  expect(screen.getByText('时态错误。')).toBeInTheDocument();
  const review = await screen.findByRole('button', { name: 'Review 0' });
  fireEvent.click(review);

  expect(await screen.findByRole('button', { name: 'Review 1' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('heading', { name: 'Speaking Coach' })).toBeInTheDocument();
});

test('records read aloud audio and uploads it for assessment', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(screen.getByRole('heading', { name: 'Pronunciation' })).toBeInTheDocument();
  expect(await screen.findByLabelText('Pronunciation scores')).toHaveTextContent('Overall 50');
  expect(screen.getByLabelText('Pronunciation scores')).toHaveTextContent('Accuracy 60');
  expect(screen.getByLabelText('Pronunciation scores')).toHaveTextContent('Fluency 90');
  expect(screen.getByText('Low-score words')).toBeInTheDocument();
  expect(screen.getByText('THEME')).toHaveClass('low-word');
  expect(global.fetch).toHaveBeenCalledWith('/api/pronunciation/assess/upload', expect.any(Object));
});

test('shows provider pronunciation errors inline', async () => {
  pronunciationUploadFails = true;
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByText('pronunciation')).toBeInTheDocument();
  expect(screen.getAllByText('腾讯云发音评测超时，请稍后重试。').length).toBeGreaterThan(0);
});

test('links read aloud assessment to the active session', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByLabelText('Pronunciation scores')).toHaveTextContent('Overall 50');
  const uploadCall = global.fetch.mock.calls.find(([url]) => url === '/api/pronunciation/assess/upload');
  expect(JSON.parse(uploadCall[1].body).session_id).toBe('session_1');
});

test('disables turn and recording controls after ending a session', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I have worked on backend systems for three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'End' }));

  expect(await screen.findByText('Practice using: I have worked on...')).toBeInTheDocument();
  expect(screen.getByLabelText('Your reply')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Record Reading' })).toBeDisabled();
});

test('records microphone audio over the session websocket', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('Thanks for sharing that project. What impact did it have?')).toBeInTheDocument();
  expect(screen.getByText('I have worked on backend systems for three years.')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Timing' })).not.toBeInTheDocument();
  expect(screen.getByText('Timing:')).toBeInTheDocument();
  expect(screen.getByText('ASR')).toBeInTheDocument();
  expect(screen.getByText('123 ms')).toBeInTheDocument();
  expect(await screen.findByText('TTS')).toBeInTheDocument();
  await waitFor(() => {
    expect(voice.sentMessages.some((payload) => payload instanceof ArrayBuffer)).toBe(true);
    expect(voice.sentMessages.some((payload) => eventType(payload) === 'start_turn')).toBe(true);
    expect(voice.sentMessages.some((payload) => eventType(payload) === 'end_turn')).toBe(true);
  });
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
});

test('voice control becomes available after reply before delayed analysis', async () => {
  const voice = installVoiceMocks({ delayedAnalysis: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('Thanks for sharing that project. What impact did it have?')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record' })).toBeInTheDocument();
});

test('renders streaming voice reply deltas and finalizes the turn', async () => {
  const voice = installVoiceMocks({ streamingReply: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('That sounds useful. What did you own?')).toBeInTheDocument();
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
});

test('renders pronunciation analysis from a voice turn', async () => {
  const voice = installVoiceMocks({ voicePronunciationResult: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByLabelText('Pronunciation scores')).toHaveTextContent('Overall 72');
  expect(screen.getByText('SYSTEMS')).toHaveClass('low-word');
});

test('shows microphone permission errors clearly', async () => {
  const voice = installVoiceMocks({ getUserMediaError: new Error('Permission denied') });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  expect(await screen.findByText('Permission denied')).toBeInTheDocument();
});

test('shows websocket analysis errors inline', async () => {
  const voice = installVoiceMocks({ websocketAnalysisError: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('asr')).toBeInTheDocument();
  expect(screen.getAllByText('语音识别暂时不可用，请稍后重试。').length).toBeGreaterThan(0);
});

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  });
}

function grammarCorrection() {
  return {
    id: 'correction_1',
    scenario_id: 'interview',
    user_text: 'I am working in this field since three years.',
    corrected_text: 'I have been working in this field for three years.',
    better_expression: 'I have spent the past three years working in this field.',
    issues: [
      {
        error_type: 'tense',
        original_span: 'am working',
        corrected_span: 'have been working',
        severity: 'major',
        explanation_zh: '谈论从过去持续到现在的经历，应使用现在完成进行时。',
      },
    ],
    overall_severity: 'major',
    correction_timing: 'after_turn',
    naturalness_reason_zh: null,
    created_at: '2026-06-05T00:00:03Z',
  };
}

function setScrollMetrics(element, { clientHeight, scrollHeight }) {
  Object.defineProperty(element, 'clientHeight', {
    configurable: true,
    value: clientHeight,
  });
  Object.defineProperty(element, 'scrollHeight', {
    configurable: true,
    value: scrollHeight,
  });
}

function installVoiceMocks(options = {}) {
  const sentMessages = [];
  const getUserMedia = vi.fn(async () => {
    if (options.getUserMediaError) {
      throw options.getUserMediaError;
    }
    return {
      getTracks: () => [{ stop: vi.fn() }],
    };
  });

  Object.defineProperty(window.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });

  class FakeMediaRecorder {
    constructor(stream) {
      this.stream = stream;
      this.state = 'inactive';
      this.mimeType = 'audio/webm';
    }

    start() {
      this.state = 'recording';
    }

    requestData() {
      this.ondataavailable?.({
        data: {
          size: 11,
          type: 'audio/webm',
          arrayBuffer: () => Promise.resolve(new Uint8Array([1, 2, 3, 4]).buffer),
        },
      });
    }

    stop() {
      this.state = 'inactive';
      this.onstop?.();
    }
  }

  class FakeWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 3;

    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.CONNECTING;
      setTimeout(() => {
        this.readyState = FakeWebSocket.OPEN;
        this.onopen?.();
      }, 0);
    }

    send(payload) {
      sentMessages.push(payload);
      if (eventType(payload) === 'start_turn') {
        setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({ type: 'asr.partial', text: 'I have worked on' }),
          });
        }, 0);
      }
      if (eventType(payload) === 'end_turn') {
        setTimeout(() => {
          if (options.websocketAnalysisError) {
            this.onmessage?.({
              data: JSON.stringify({
                type: 'analysis.error',
                stage: 'asr',
                error: {
                  stage: 'asr',
                  code: 'provider_request_failed',
                  user_message_zh: '语音识别暂时不可用，请稍后重试。',
                  severity: 'warning',
                  fallback_applied: false,
                },
              }),
            });
            return;
          }
          this.onmessage?.({
            data: JSON.stringify({
              type: 'asr.final',
              text: 'I have worked on backend systems for three years.',
              user_turn_id: 'turn_user_voice_1',
            }),
          });
          if (options.delayedReply) {
            setTimeout(() => {
              this.onmessage?.({
                data: JSON.stringify({
                  type: 'reply.text',
                  text: 'Thanks for sharing that project. What impact did it have?',
                  turn_id: 'turn_ai_voice_1',
                }),
              });
              this.onmessage?.({
                data: JSON.stringify({
                  type: 'debug.timing',
                  stage: 'reply',
                  timings: {
                    asr_ms: 123,
                    dialogue_reply_ms: 45,
                    end_turn_to_reply_text_ms: 190,
                  },
                }),
              });
              this.sendAnalysisResult();
            }, 80);
            return;
          }
          if (options.streamingReply) {
            this.onmessage?.({
              data: JSON.stringify({ type: 'reply.delta', text: 'That sounds useful. ' }),
            });
            this.onmessage?.({
              data: JSON.stringify({ type: 'reply.delta', text: 'What did you own?' }),
            });
            this.onmessage?.({
              data: JSON.stringify({
                type: 'reply.done',
                text: 'That sounds useful. What did you own?',
                turn_id: 'turn_ai_stream_1',
              }),
            });
            this.onmessage?.({
              data: JSON.stringify({
                type: 'debug.timing',
                stage: 'reply',
                timings: {
                  asr_ms: 123,
                  dialogue_reply_ms: 45,
                  end_turn_to_reply_text_ms: 190,
                },
              }),
            });
            this.sendAnalysisResult();
            return;
          }
          this.onmessage?.({
            data: JSON.stringify({
              type: 'reply.text',
              text: 'Thanks for sharing that project. What impact did it have?',
              turn_id: 'turn_ai_voice_1',
            }),
          });
          this.onmessage?.({
            data: JSON.stringify({
              type: 'debug.timing',
              stage: 'reply',
              timings: {
                asr_ms: 123,
                dialogue_reply_ms: 45,
                end_turn_to_reply_text_ms: 190,
              },
            }),
          });
          if (options.delayedAnalysis) {
            setTimeout(() => this.sendAnalysisResult(), 80);
            return;
          }
          this.sendAnalysisResult();
        }, 0);
      }
    }

    sendAnalysisResult() {
      this.onmessage?.({
        data: JSON.stringify({
          type: 'debug.timing',
          stage: 'grammar',
          timings: {
            asr_ms: 123,
            dialogue_reply_ms: 45,
            grammar_ms: 67,
            end_turn_to_reply_text_ms: 190,
          },
        }),
      });
      this.onmessage?.({
        data: JSON.stringify({
          type: 'analysis.result',
          stage: 'grammar',
          result: {
            id: 'correction_voice_1',
            scenario_id: 'interview',
            user_text: 'I have worked on backend systems for three years.',
            corrected_text: 'I have worked on backend systems for three years.',
            better_expression: null,
            issues: [],
            overall_severity: 'minor',
            correction_timing: 'delayed_summary',
            naturalness_reason_zh: null,
            created_at: '2026-06-05T00:00:06Z',
          },
        }),
      });
      if (options.voicePronunciationResult) {
        this.onmessage?.({
          data: JSON.stringify({
            type: 'debug.timing',
            stage: 'pronunciation',
            timings: {
              pronunciation_ms: 222,
            },
          }),
        });
        this.onmessage?.({
          data: JSON.stringify({
            type: 'analysis.result',
            stage: 'pronunciation',
            result: {
              id: 'assessment_voice_1',
              provider: 'mock-real',
              reference_text: 'I have worked on backend systems for three years.',
              audio_file: '/tmp/audio.wav',
              overall: 72,
              accuracy: 70,
              fluency: 75,
              prosody: null,
              completeness: null,
              words: [
                { word: 'I', accuracy: 95, fluency: null, phonemes: [], issue: null },
                { word: 'SYSTEMS', accuracy: 40, fluency: null, phonemes: [], issue: 'low_accuracy' },
              ],
              issues: [],
              created_at: '2026-06-05T00:00:07Z',
            },
          }),
        });
      }
    }

    close() {
      this.readyState = FakeWebSocket.CLOSED;
      this.onclose?.();
    }
  }

  vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
  vi.stubGlobal('WebSocket', FakeWebSocket);

  return { getUserMedia, sentMessages };
}

function eventType(payload) {
  if (typeof payload !== 'string') {
    return null;
  }
  return JSON.parse(payload).type;
}
