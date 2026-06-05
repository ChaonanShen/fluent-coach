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

beforeEach(() => {
  window.speechSynthesis = {
    cancel: vi.fn(),
    speak: vi.fn(),
  };
  window.SpeechSynthesisUtterance = vi.fn(function utterance(text) {
    this.text = text;
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
      return jsonResponse({
        session: {
          id: 'session_1',
          scenario_id: 'interview',
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
      });
    }
    if (url === '/api/grammar/check') {
      return jsonResponse({
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
      });
    }
    if (url === '/api/pronunciation/assess') {
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

  expect(await screen.findByRole('button', { name: 'Job Interview' })).toBeInTheDocument();
  expect(screen.getByText('am working')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText(scenario.opening_line)).toBeInTheDocument();
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
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith('/api/grammar/check', expect.any(Object)));
  expect(window.speechSynthesis.speak).toHaveBeenCalled();
});

test('reviews a saved mistake', async () => {
  render(<App />);

  const review = await screen.findByRole('button', { name: 'Review 0' });
  fireEvent.click(review);

  expect(await screen.findByRole('button', { name: 'Review 1' })).toBeInTheDocument();
});

test('runs read aloud assessment', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Assess Reading' }));

  expect(await screen.findByText('Overall')).toBeInTheDocument();
  expect(screen.getByText('THEME')).toHaveClass('low-word');
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
  await waitFor(() => {
    expect(voice.sentMessages.some((payload) => payload instanceof ArrayBuffer)).toBe(true);
    expect(voice.sentMessages.some((payload) => eventType(payload) === 'start_turn')).toBe(true);
    expect(voice.sentMessages.some((payload) => eventType(payload) === 'end_turn')).toBe(true);
  });
  expect(window.speechSynthesis.speak).toHaveBeenCalled();
});

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  });
}

function installVoiceMocks() {
  const sentMessages = [];
  const getUserMedia = vi.fn(async () => ({
    getTracks: () => [{ stop: vi.fn() }],
  }));

  Object.defineProperty(window.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });

  class FakeMediaRecorder {
    constructor(stream) {
      this.stream = stream;
      this.state = 'inactive';
    }

    start() {
      this.state = 'recording';
    }

    requestData() {
      this.ondataavailable?.({
        data: {
          size: 11,
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
          this.onmessage?.({
            data: JSON.stringify({
              type: 'asr.final',
              text: 'I have worked on backend systems for three years.',
              user_turn_id: 'turn_user_voice_1',
            }),
          });
          this.onmessage?.({
            data: JSON.stringify({
              type: 'reply.text',
              text: 'Thanks for sharing that project. What impact did it have?',
              turn_id: 'turn_ai_voice_1',
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
        }, 0);
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
