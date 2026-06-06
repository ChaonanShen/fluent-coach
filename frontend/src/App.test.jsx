import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
let deletedMistakeIds = new Set();
let deletedBookSessionIds = new Set();
let extraMistakeBookEnabled = false;

function mockGrammarMistake(overrides = {}) {
  return {
    id: 'mistake_1',
    type: 'grammar',
    session_id: 'session_1',
    turn_id: 'turn_user_1',
    source_stage: 'grammar',
    source_id: 'correction_1',
    subtype: 'tense',
    severity: 'major',
    tags: ['interview', 'tense'],
    wrong: 'am working',
    correct: 'have been working',
    explanation_zh: '时态错误。',
    practice_sentence: 'I have been working in this field for three years.',
    word: null,
    phoneme: null,
    mastery: 0.1,
    review_count: 0,
    created_at: '2026-06-05T00:00:04Z',
    last_seen_at: '2026-06-05T00:00:04Z',
    next_review_at: null,
    ...overrides,
  };
}

function mockExpressionMistake(overrides = {}) {
  return {
    id: 'mistake_2',
    type: 'expression',
    session_id: 'session_1',
    turn_id: 'turn_user_1',
    source_stage: 'expression',
    source_id: 'correction_1',
    subtype: 'natural_expression',
    severity: 'minor',
    tags: ['interview', 'natural_expression'],
    wrong: 'since three years',
    correct: 'for the past three years',
    explanation_zh: '表达可以更自然。',
    practice_sentence: 'I have spent the past three years working in this field.',
    word: null,
    phoneme: null,
    mastery: 0.2,
    review_count: 0,
    created_at: '2026-06-05T00:00:05Z',
    last_seen_at: '2026-06-05T00:00:05Z',
    next_review_at: null,
    ...overrides,
  };
}

function mockPronunciationMistake(overrides = {}) {
  return {
    id: 'mistake_3',
    type: 'pronunciation',
    session_id: 'session_2',
    turn_id: 'turn_user_2',
    source_stage: 'pronunciation',
    source_id: 'assessment_2',
    subtype: 'low_accuracy',
    severity: 'minor',
    tags: ['low_accuracy'],
    wrong: 'systems',
    correct: 'systems',
    explanation_zh: '这个词发音准确度偏低。',
    practice_sentence: 'I have worked on backend systems for three years.',
    word: 'systems',
    phoneme: null,
    mastery: 0.3,
    review_count: 0,
    created_at: '2026-06-05T00:01:04Z',
    last_seen_at: '2026-06-05T00:01:04Z',
    next_review_at: null,
    ...overrides,
  };
}

function mockMistakes() {
  const mistakes = deletedBookSessionIds.has('session_1') ? [] : [mockGrammarMistake(), mockExpressionMistake()];
  if (extraMistakeBookEnabled && !deletedBookSessionIds.has('session_2')) {
    mistakes.push(mockPronunciationMistake());
  }
  return mistakes.filter((mistake) => !deletedMistakeIds.has(mistake.id));
}

function mockMistakesForSession(sessionId) {
  return mockMistakes().filter((mistake) => mistake.session_id === sessionId);
}

function mockSummary(sessionId = 'session_1') {
  if (sessionId === 'session_2') {
    return {
      id: 'summary_2',
      session_id: 'session_2',
      grammar_score: 96,
      pronunciation_score: 72,
      fluency_score: 75,
      vocabulary_score: 82,
      task_completion_rate: 1,
      top_issues: ['pronunciation: systems'],
      next_drills: ['Practice pronouncing systems in one short sentence.'],
      created_at: '2026-06-05T00:01:10Z',
    };
  }
  return {
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
  };
}

function mockMistakeBookRecord(sessionId = 'session_1') {
  const currentMistakes = mockMistakesForSession(sessionId);
  const meta = sessionId === 'session_2'
    ? {
        title: 'Presentation Practice - 2026-06-05 00:01 UTC',
        scenario_id: 'presentation',
        scenario_name: 'Presentation Practice',
        created_at: '2026-06-05T00:01:00Z',
      }
    : {
        title: 'Job Interview - 2026-06-05 00:00 UTC',
        scenario_id: 'interview',
        scenario_name: 'Job Interview',
        created_at: '2026-06-05T00:00:00Z',
      };
  return {
    session_id: sessionId,
    title: meta.title,
    scenario_id: meta.scenario_id,
    scenario_name: meta.scenario_name,
    status: 'active',
    created_at: meta.created_at,
    ended_at: null,
    mistake_count: currentMistakes.length,
    grammar_count: currentMistakes.filter((mistake) => mistake.type === 'grammar').length,
    expression_count: currentMistakes.filter((mistake) => mistake.type === 'expression').length,
    pronunciation_count: currentMistakes.filter((mistake) => mistake.type === 'pronunciation').length,
    lowest_mastery: currentMistakes.length ? Math.min(...currentMistakes.map((mistake) => mistake.mastery)) : null,
    due_count: 0,
    summary: mockSummary(sessionId),
  };
}

function mockMistakeBookRecords() {
  const sessionIds = extraMistakeBookEnabled ? ['session_1', 'session_2'] : ['session_1'];
  return sessionIds
    .filter((sessionId) => mockMistakesForSession(sessionId).length)
    .map((sessionId) => mockMistakeBookRecord(sessionId));
}

function mockMistakeBookDetail(sessionId = 'session_1') {
  const currentMistakes = mockMistakesForSession(sessionId);
  const turn = sessionId === 'session_2'
    ? {
        id: 'turn_user_2',
        session_id: 'session_2',
        speaker: 'user',
        text: 'I have worked on backend systems for three years.',
        created_at: '2026-06-05T00:01:01Z',
        mode: 'voice',
        audio_path: null,
        asr_confidence: 0.91,
      }
    : {
        id: 'turn_user_1',
        session_id: 'session_1',
        speaker: 'user',
        text: 'I am working in this field since three years.',
        created_at: '2026-06-05T00:00:01Z',
        mode: 'text',
        audio_path: null,
        asr_confidence: null,
      };
  return {
    record: mockMistakeBookRecord(sessionId),
    turn_groups: currentMistakes.length
      ? [
          {
            turn,
            mistakes: currentMistakes,
          },
        ]
      : [],
  };
}

function mockProgress() {
  const trend = [
    {
      session_id: 'session_previous',
      scenario_id: 'interview',
      created_at: '2026-06-04T00:00:00Z',
      grammar_score: 92,
      pronunciation_score: 68,
      fluency_score: 65,
      vocabulary_score: 70,
      task_completion_rate: 0.25,
    },
    {
      session_id: 'session_1',
      scenario_id: 'interview',
      created_at: '2026-06-05T00:00:00Z',
      grammar_score: 100,
      pronunciation_score: null,
      fluency_score: 70,
      vocabulary_score: 76,
      task_completion_rate: 0.5,
    },
  ];
  if (extraMistakeBookEnabled) {
    trend.push({
      session_id: 'session_2',
      scenario_id: 'presentation',
      created_at: '2026-06-05T00:01:00Z',
      grammar_score: 96,
      pronunciation_score: 72,
      fluency_score: 75,
      vocabulary_score: 82,
      task_completion_rate: 1,
    });
  }
  return {
    session_count: trend.length,
    average_grammar_score: 96,
    average_pronunciation_score: 70,
    average_fluency_score: 70,
    average_vocabulary_score: 76,
    average_task_completion_rate: 0.58,
    trend,
  };
}

beforeEach(() => {
  pronunciationUploadFails = false;
  cloudTtsEnabled = false;
  sessionRequestBodies = [];
  deletedMistakeIds = new Set();
  deletedBookSessionIds = new Set();
  extraMistakeBookEnabled = false;
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
        mistakes: mockMistakes(),
      });
    }
    if (url === '/api/mistake-books') {
      return jsonResponse({
        books: mockMistakeBookRecords(),
      });
    }
    if (url === '/api/mistake-books/delete' && options.method === 'POST') {
      const sessionIds = JSON.parse(options.body).session_ids;
      const deletedCount = sessionIds.reduce(
        (total, sessionId) => total + mockMistakesForSession(sessionId).length,
        0,
      );
      sessionIds.forEach((sessionId) => deletedBookSessionIds.add(sessionId));
      return jsonResponse({ deleted_count: deletedCount });
    }
    if (url.startsWith('/api/mistake-books/') && options.method === 'DELETE') {
      const sessionId = url.split('/').at(-1);
      const deletedCount = mockMistakesForSession(sessionId).length;
      deletedBookSessionIds.add(sessionId);
      return jsonResponse({ deleted_count: deletedCount });
    }
    if (url === '/api/mistake-books/session_1') {
      return jsonResponse(mockMistakeBookDetail('session_1'));
    }
    if (url === '/api/mistake-books/session_2') {
      return jsonResponse(mockMistakeBookDetail('session_2'));
    }
    if (url === '/api/progress') {
      return jsonResponse(mockProgress());
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
    if (url.startsWith('/api/mistakes/') && options.method === 'DELETE') {
      const mistakeId = url.split('/').at(-1);
      deletedMistakeIds.add(mistakeId);
      return jsonResponse({ deleted_count: 1 });
    }
    if (url === '/api/sessions') {
      const requestBody = JSON.parse(options.body);
      sessionRequestBodies.push(requestBody);
      if (requestBody.scenario_id === 'custom') {
        const customPrompt = requestBody.custom_prompt;
        const customScenario = {
          ...scenario,
          id: 'custom_airport',
          name: 'Custom',
          user_role: `Learner practicing: ${customPrompt}`,
          opening_line: `Let's practice ${customPrompt}. Could you start with what you want to say first?`,
          conversation_goals: [`Practice a realistic conversation about ${customPrompt}`],
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
      return jsonResponse(mockSummary('session_1'));
    }
    if (url === '/api/pronunciation/practice/upload') {
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
      if (!body.audio_base64 || !body.reference_text || body.session_id) {
        throw new Error('Invalid pronunciation practice payload');
      }
      return jsonResponse({
        id: 'assessment_1',
        provider: 'mock',
        reference_text: body.reference_text,
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
  expect(screen.getByLabelText('Reading Practice')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Coach' })).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue('THEN HE WENT TO THEME PARK')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record Reading' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Mistake Book (2)' })).toBeInTheDocument();
  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  expect(screen.queryByText('Progress')).not.toBeInTheDocument();
  expect(screen.queryByText('Sessions')).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Conversation' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Conversation history')).toBeInTheDocument();
  const assessmentPanel = screen.getByLabelText('Conversation Assessment');
  expect(within(assessmentPanel).getByRole('heading', { name: 'Grammar / Expression Correction' })).toBeInTheDocument();
  expect(within(assessmentPanel).getByRole('heading', { name: 'Pronunciation' })).toBeInTheDocument();
  expect(within(assessmentPanel).getByRole('heading', { name: 'Timing' })).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('No correction yet.')).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('No pronunciation result yet.')).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('No timing yet.')).toBeInTheDocument();
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
  expect(screen.queryByText('Custom scenario')).not.toBeInTheDocument();
  expect(screen.getByPlaceholderText('Describe the English conversation scenario you want to practice...')).toBeInTheDocument();
  expect(screen.getByLabelText('Custom scenario')).toHaveAttribute('rows', '1');
  fireEvent.change(screen.getByLabelText('Custom scenario'), {
    target: { value: 'airport check-in' },
  });
  expect(screen.queryByText('Practice a realistic conversation about airport check-in')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText("Let's practice airport check-in. Could you start with what you want to say first?"))
    .toBeInTheDocument();
  expect(sessionRequestBodies.at(-1)).toEqual({
    scenario_id: 'custom',
    custom_prompt: 'airport check-in',
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
  const assessmentPanel = screen.getByLabelText('Conversation Assessment');
  expect(within(assessmentPanel).getByText('I have been working in this field for three years.')).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('谈论从过去持续到现在的经历，应使用现在完成进行时。')).toBeInTheDocument();
  expect(within(assessmentPanel).queryByText('Pronunciation pending.')).not.toBeInTheDocument();
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

test('keeps ASR partial transcription out of the visible conversation', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  await waitFor(() => {
    expect(voice.sentMessages.some((payload) => eventType(payload) === 'start_turn')).toBe(true);
  });
  expect(screen.queryByText(/Partial:/)).not.toBeInTheDocument();
  expect(screen.queryByText('I have worked on')).not.toBeInTheDocument();

  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  await waitFor(() => {
    expect(within(screen.getByLabelText('Conversation history')).getByText('I have worked on backend systems for three years.'))
      .toBeInTheDocument();
  });
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

test('shows saved mistake details without review actions', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));
  expect(await screen.findByRole('heading', { name: 'Mistake Book' })).toBeInTheDocument();
  expect(screen.getByLabelText('Reading Practice')).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));
  expect(await screen.findByText('am working')).toBeInTheDocument();
  expect(screen.getByText('I am working in this field since three years.')).toBeInTheDocument();
  expect(screen.getByText('时态错误。')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Review/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('heading', { name: 'Speaking Coach' })).toBeInTheDocument();
});

test('shows summary scores on mistake book records and details', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));

  const listScores = await screen.findByLabelText('Overall score');
  expect(listScores).toHaveTextContent('Overall 85.6');
  expect(listScores).not.toHaveTextContent('Grammar');
  expect(listScores).not.toHaveTextContent('Pronunciation');
  expect(listScores).not.toHaveTextContent('Fluency');
  expect(listScores).not.toHaveTextContent('Vocabulary');
  expect(listScores).not.toHaveTextContent('Tasks');
  expect(screen.queryByText(/Job Interview - 06\/05/)).not.toBeInTheDocument();

  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));

  const detailScores = await screen.findByLabelText('Summary scores');
  expect(detailScores).toHaveTextContent('Overall 85.6');
  expect(detailScores).toHaveTextContent('Grammar 100.0');
  expect(detailScores).toHaveTextContent('Pronunciation -');
  expect(detailScores).toHaveTextContent('Fluency 70.0');
  expect(detailScores).toHaveTextContent('Vocabulary 76.0');
  expect(detailScores).not.toHaveTextContent('Tasks');
  const scoreChanges = await screen.findByLabelText('Score changes');
  expect(scoreChanges).toHaveTextContent('Overall +9.4');
  expect(scoreChanges).toHaveTextContent('Grammar +8.0');
  expect(scoreChanges).toHaveTextContent('Pronunciation -');
  expect(scoreChanges).toHaveTextContent('Fluency +5.0');
  expect(scoreChanges).toHaveTextContent('Vocabulary +6.0');
  expect(scoreChanges).not.toHaveTextContent('Tasks');
  expect(screen.queryByText(/Job Interview - 06\/05/)).not.toBeInTheDocument();
});

test('filters a mistake book detail by mistake type', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));

  expect(await screen.findByText('am working')).toBeInTheDocument();
  expect(screen.getByText('since three years')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Grammar 1' }));

  expect(screen.getByText('am working')).toBeInTheDocument();
  expect(screen.queryByText('since three years')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Grammar 1' }));

  expect(await screen.findByText('since three years')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Expression 1' }));

  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  expect(screen.getByText('since three years')).toBeInTheDocument();
});

test('deletes one mistake from a conversation detail and refreshes counts', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));
  expect(await screen.findByText('am working')).toBeInTheDocument();

  fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]);

  await waitFor(() => expect(screen.queryByText('am working')).not.toBeInTheDocument());
  expect(await screen.findByRole('button', { name: 'Grammar 0' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Expression 1' })).toBeInTheDocument();
  expect(screen.getByText('since three years')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('button', { name: 'Mistake Book (1)' })).toBeInTheDocument();
});

test('deletes the current mistake book from detail', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));
  expect(await screen.findByText('am working')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Delete Book' }));

  expect(await screen.findByText('No conversation mistake books yet.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('button', { name: 'Mistake Book (0)' })).toBeInTheDocument();
});

test('selects one mistake book without opening it and deletes the selection', async () => {
  extraMistakeBookEnabled = true;
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (3)' }));
  expect(await screen.findByRole('button', { name: /Open Job Interview/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Open Presentation Practice/ })).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText('Select Job Interview - 2026-06-05 00:00 UTC'));

  expect(screen.getByText('1 selected')).toBeInTheDocument();
  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }));

  expect(screen.getByText('0 selected')).toBeInTheDocument();
  expect(screen.getByLabelText('Select Job Interview - 2026-06-05 00:00 UTC')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Select Job Interview - 2026-06-05 00:00 UTC'));
  expect(screen.getByText('1 selected')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete selected' }));

  await waitFor(() => {
    expect(screen.queryByRole('button', { name: /Open Job Interview/ })).not.toBeInTheDocument();
  });
  expect(screen.getByRole('button', { name: /Open Presentation Practice/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('button', { name: 'Mistake Book (1)' })).toBeInTheDocument();
});

test('reassesses a pronunciation mistake without changing the saved mistake', async () => {
  extraMistakeBookEnabled = true;
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (3)' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open Presentation Practice/ }));

  expect((await screen.findAllByText('systems')).length).toBeGreaterThan(0);
  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  expect(screen.getByText('Word:')).toBeInTheDocument();
  expect(screen.getByText('Practice sentence:')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Read word' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Read sentence' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Read word' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByText('Read word: systems')).toBeInTheDocument();
  expect(await screen.findByLabelText('Practice result')).toHaveTextContent('Overall 50');
  expect(screen.getAllByText('systems').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: 'Pronunciation 1' })).toBeInTheDocument();
  const uploadCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(uploadCalls.at(-1)[1].body)).toMatchObject({
    reference_text: 'systems',
  });

  fireEvent.click(screen.getByRole('button', { name: 'Read sentence' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByText('Read sentence: I have worked on backend systems for three years.')).toBeInTheDocument();
  const nextUploadCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(nextUploadCalls.at(-1)[1].body)).toMatchObject({
    reference_text: 'I have worked on backend systems for three years.',
  });
});

test('selects all mistake books and bulk deletes them', async () => {
  extraMistakeBookEnabled = true;
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (3)' }));
  expect(await screen.findByRole('button', { name: /Open Job Interview/ })).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText('Select all mistake books'));

  expect(screen.getByText('2 selected')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete selected' }));

  expect(await screen.findByText('No conversation mistake books yet.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('button', { name: 'Mistake Book (0)' })).toBeInTheDocument();
});

test('records read aloud audio and uploads it for assessment', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.change(await screen.findByLabelText('Text to read'), {
    target: { value: 'backend systems' },
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(screen.getByRole('heading', { name: 'Reading Practice' })).toBeInTheDocument();
  expect(await screen.findByText('Practice result: backend systems')).toBeInTheDocument();
  expect(await screen.findByLabelText('Practice result')).toHaveTextContent('Overall 50');
  expect(screen.getByLabelText('Practice result')).toHaveTextContent('Accuracy 60');
  expect(screen.getByLabelText('Practice result')).toHaveTextContent('Fluency 90');
  expect(screen.getByText('Low-score words')).toBeInTheDocument();
  expect(screen.getByText('THEME')).toHaveClass('low-word');
  const uploadCall = global.fetch.mock.calls.find(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(uploadCall[1].body)).toMatchObject({
    reference_text: 'backend systems',
    mime_type: 'audio/webm',
  });
  expect(JSON.parse(uploadCall[1].body)).not.toHaveProperty('session_id');
});

test('shows provider pronunciation errors inline', async () => {
  pronunciationUploadFails = true;
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.change(await screen.findByLabelText('Text to read'), {
    target: { value: 'backend systems' },
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByText('pronunciation')).toBeInTheDocument();
  expect(screen.getAllByText('腾讯云发音评测超时，请稍后重试。').length).toBeGreaterThan(0);
});

test('keeps read aloud practice independent from the active session', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  const fetchCountBeforePractice = global.fetch.mock.calls.length;
  fireEvent.change(await screen.findByLabelText('Text to read'), {
    target: { value: 'backend systems' },
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(await screen.findByLabelText('Practice result')).toHaveTextContent('Overall 50');
  const practiceCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/pronunciation/practice/upload');
  expect(practiceCalls).toHaveLength(1);
  expect(JSON.parse(practiceCalls[0][1].body)).not.toHaveProperty('session_id');
  const practiceFetches = global.fetch.mock.calls.slice(fetchCountBeforePractice).map(([url]) => url);
  expect(practiceFetches).not.toContain('/api/mistakes');
  expect(practiceFetches).not.toContain('/api/mistake-books');
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
  const summaryBlock = screen.getByRole('heading', { name: 'Summary' }).closest('section');
  expect(within(summaryBlock).getByText('Grammar').nextElementSibling).toHaveTextContent('100.0');
  expect(within(summaryBlock).getByText('Pronunciation').nextElementSibling).toHaveTextContent('-');
  expect(within(summaryBlock).getByText('Fluency').nextElementSibling).toHaveTextContent('70.0');
  expect(within(summaryBlock).getByText('Vocabulary').nextElementSibling).toHaveTextContent('76.0');
  expect(screen.queryByText('Tasks')).not.toBeInTheDocument();
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
  expect(within(screen.getByLabelText('Conversation history')).getByText('I have worked on backend systems for three years.'))
    .toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Timing' })).toBeInTheDocument();
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

  const assessmentPanel = await screen.findByLabelText('Conversation Assessment');
  await waitFor(() => expect(within(assessmentPanel).getByLabelText('Pronunciation scores')).toHaveTextContent('Overall 72'));
  expect(within(assessmentPanel).getByText('SYSTEMS')).toHaveClass('low-word');
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

test('clears previous turn issues when a new voice turn starts', async () => {
  const failedVoice = installVoiceMocks({ websocketAnalysisError: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  await waitFor(() => expect(failedVoice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));
  expect(await screen.findByText('asr')).toBeInTheDocument();

  const cleanVoice = installVoiceMocks();
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(cleanVoice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  expect(screen.queryByText('asr')).not.toBeInTheDocument();
  expect(screen.queryByText('语音识别暂时不可用，请稍后重试。')).not.toBeInTheDocument();
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
                  user_turn_id: 'turn_user_voice_1',
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
                user_turn_id: 'turn_user_voice_1',
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
              user_turn_id: 'turn_user_voice_1',
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
          turn_id: 'turn_user_voice_1',
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
            turn_id: 'turn_user_voice_1',
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
