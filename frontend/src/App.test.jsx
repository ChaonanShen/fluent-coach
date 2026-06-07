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
let progressNeverResolves = false;

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
    practice_sentence: 'The team reviewed the backend systems before launch.',
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
  progressNeverResolves = false;
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
      if (progressNeverResolves) {
        return new Promise(() => {});
      }
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
    if (url === '/api/known-info/pdf') {
      return jsonResponse({
        source: {
          name: 'resume.pdf',
          kind: 'pdf',
          text_preview: 'Resume PDF text',
          char_count: 'Resume PDF text'.length,
        },
        text: 'Resume PDF text',
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
      const openingText = requestBody.known_info_text
        ? 'I reviewed the background you shared. Could you walk me through one project that best matches this role?'
        : scenario.opening_line;
      return jsonResponse({
        session: {
          id: 'session_1',
          scenario_id: 'interview',
          custom_scenario: null,
          status: 'active',
          created_at: '2026-06-05T00:00:00Z',
          ended_at: null,
          turns: [{ ...openingTurn, text: openingText }],
        },
        scenario,
        opening_line: openingText,
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
    if (url === '/api/sessions/session_1/analysis') {
      return jsonResponse({
        session_id: 'session_1',
        grammar_results: [grammarCorrection()],
        pronunciation_results: [],
        errors: [],
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
      if (!body.audio_base64 || body.session_id) {
        throw new Error('Invalid pronunciation practice payload');
      }
      const referenceText = body.reference_text || 'THEN HE WENT TO THEME PARK';
      return jsonResponse({
        id: 'assessment_1',
        provider: 'mock',
        reference_text: referenceText,
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

  const legacyBrand = ['X', 'Engineer'].join('');
  expect(await screen.findByRole('heading', { name: 'Speaking Coach' })).toBeInTheDocument();
  expect(await screen.findByRole('combobox', { name: 'Scenario' })).toHaveValue('interview');
  expect(screen.queryByText(legacyBrand)).not.toBeInTheDocument();
  expect(screen.queryByText('Candidate')).not.toBeInTheDocument();
  expect(screen.queryByText('Introduce professional background clearly')).not.toBeInTheDocument();
  const readingPracticePanel = screen.getByLabelText('Reading Practice');
  expect(readingPracticePanel).toBeInTheDocument();
  expect(screen.getByLabelText('Read transcript')).toHaveAttribute('readonly');
  expect(screen.queryByRole('heading', { name: 'Coach' })).not.toBeInTheDocument();
  expect(screen.queryByDisplayValue('THEN HE WENT TO THEME PARK')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record Reading' })).toBeEnabled();
  expect(within(readingPracticePanel).getByRole('button', { name: 'Mistake Book (2)' })).toBeInTheDocument();
  expect(screen.queryByText('am working')).not.toBeInTheDocument();
  expect(screen.queryByText('Progress')).not.toBeInTheDocument();
  expect(screen.queryByText('Sessions')).not.toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Conversation' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Conversation history')).toBeInTheDocument();
  const assessmentPanel = screen.getByLabelText('Conversation Assessment');
  expect(within(assessmentPanel).queryByRole('heading', { name: 'Grammar / Expression Correction' })).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByRole('heading', { name: 'Pronunciation' })).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByRole('heading', { name: 'Timing' })).not.toBeInTheDocument();
  expect(within(readingPracticePanel).getByRole('heading', { name: 'Timing' })).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('No assessment yet.')).toBeInTheDocument();
  expect(within(readingPracticePanel).getByText('No timing yet.')).toBeInTheDocument();
  expect(within(assessmentPanel).queryByRole('button', { name: 'Mistake Book (2)' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText(scenario.opening_line)).toBeInTheDocument();
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
  expect(window.speechSynthesis.speak.mock.calls.at(-1)[0].text).toBe(scenario.opening_line);
  expect(screen.getByRole('button', { name: 'End' })).toBeInTheDocument();
});

test('keeps browser TTS on one voice after voices load asynchronously', async () => {
  installTextConversationMock();
  const compactVoice = { name: 'Compact Voice', lang: 'en-US' };
  const googleVoice = { name: 'Google US English', lang: 'en-US' };
  let voicesLoaded = false;
  let voicesChangedHandler = null;
  window.speechSynthesis.getVoices = vi.fn(() => (voicesLoaded ? [compactVoice, googleVoice] : [compactVoice]));
  window.speechSynthesis.addEventListener = vi.fn((event, handler) => {
    if (event === 'voiceschanged') {
      voicesChangedHandler = handler;
    }
  });
  window.speechSynthesis.removeEventListener = vi.fn();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await waitFor(() => expect(window.speechSynthesis.addEventListener).toHaveBeenCalledWith('voiceschanged', expect.any(Function)));
  voicesLoaded = true;
  voicesChangedHandler();

  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1));
  const openingUtterance = window.speechSynthesis.speak.mock.calls[0][0];
  expect(openingUtterance.text).toBe(scenario.opening_line);
  expect(openingUtterance.voice).toBe(googleVoice);

  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  await screen.findByText('Great. Which project is most relevant to this role?');
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(2));
  const replyUtterance = window.speechSynthesis.speak.mock.calls[1][0];
  expect(replyUtterance.voice).toBe(openingUtterance.voice);
});

test('starts a custom scenario from the scenario briefing', async () => {
  render(<App />);

  fireEvent.change(await screen.findByRole('combobox', { name: 'Scenario' }), {
    target: { value: 'custom' },
  });
  // Custom no longer has its own toolbar textarea; the briefing below is the single input.
  expect(screen.queryByLabelText('Custom scenario')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Known background'), {
    target: { value: 'airport check-in' },
  });
  expect(screen.getByRole('button', { name: 'Start' })).not.toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  expect(await screen.findByText("Let's practice airport check-in. Could you start with what you want to say first?"))
    .toBeInTheDocument();
  expect(sessionRequestBodies.at(-1)).toEqual({
    scenario_id: 'custom',
    custom_prompt: 'airport check-in',
    known_info_text: 'airport check-in',
  });
});

test('shows collapsible scenario briefing for builtin scenarios', async () => {
  render(<App />);

  expect(await screen.findByLabelText('Scenario Briefing')).toBeInTheDocument();
  expect(screen.getByLabelText('Known background')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Known background'), {
    target: { value: 'I am preparing for a backend interview.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Collapse' }));

  expect(screen.queryByLabelText('Known background')).not.toBeInTheDocument();
  expect(screen.getByText('39 chars · 0 PDF')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
  expect(screen.getByDisplayValue('I am preparing for a backend interview.')).toBeInTheDocument();
});

test('uploads one briefing PDF and includes it in start payload', async () => {
  render(<App />);

  await screen.findByLabelText('Scenario Briefing');
  fireEvent.change(screen.getByLabelText('Known background'), {
    target: { value: 'Typed background' },
  });
  const file = new File(['fake pdf'], 'resume.pdf', { type: 'application/pdf' });
  fireEvent.change(screen.getByLabelText('Upload briefing PDF'), {
    target: { files: [file] },
  });

  expect(await screen.findByText('resume.pdf')).toBeInTheDocument();
  expect(screen.getByText('1 PDF attached')).toBeInTheDocument();
  expect(screen.getByLabelText('Upload briefing PDF')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  await screen.findByText(/I reviewed the background you shared/);
  expect(sessionRequestBodies.at(-1)).toMatchObject({
    scenario_id: 'interview',
    known_info_text: 'Typed background\n\nResume PDF text',
    known_info_sources: [
      {
        name: 'resume.pdf',
        kind: 'pdf',
        text_preview: 'Resume PDF text',
        char_count: 'Resume PDF text'.length,
      },
    ],
  });
  expect(screen.queryByLabelText('Known background')).not.toBeInTheDocument();
});

test('removing a briefing PDF removes its text from start payload', async () => {
  render(<App />);

  await screen.findByLabelText('Scenario Briefing');
  fireEvent.change(screen.getByLabelText('Known background'), {
    target: { value: 'Typed background' },
  });
  fireEvent.change(screen.getByLabelText('Upload briefing PDF'), {
    target: { files: [new File(['fake pdf'], 'resume.pdf', { type: 'application/pdf' })] },
  });
  expect(await screen.findByText('resume.pdf')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Remove resume.pdf' }));
  expect(screen.queryByText('resume.pdf')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  await screen.findByText(/I reviewed the background you shared/);
  expect(sessionRequestBodies.at(-1)).toMatchObject({
    scenario_id: 'interview',
    known_info_text: 'Typed background',
  });
  expect(sessionRequestBodies.at(-1)).not.toHaveProperty('known_info_sources');
  expect(sessionRequestBodies.at(-1).known_info_text).not.toContain('Resume PDF text');
});

test('custom scenario uses briefing text as prompt and merges PDF into known info', async () => {
  render(<App />);

  fireEvent.change(await screen.findByRole('combobox', { name: 'Scenario' }), {
    target: { value: 'custom' },
  });
  fireEvent.change(screen.getByLabelText('Upload briefing PDF'), {
    target: { files: [new File(['fake pdf'], 'resume.pdf', { type: 'application/pdf' })] },
  });
  expect(await screen.findByText('resume.pdf')).toBeInTheDocument();
  // A PDF alone does not describe the custom scenario, so Start stays disabled.
  expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled();

  fireEvent.change(screen.getByLabelText('Known background'), {
    target: { value: 'airport check-in' },
  });
  expect(screen.getByRole('button', { name: 'Start' })).not.toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));

  await screen.findByText("Let's practice airport check-in. Could you start with what you want to say first?");
  expect(sessionRequestBodies.at(-1)).toMatchObject({
    scenario_id: 'custom',
    custom_prompt: 'airport check-in',
    known_info_text: 'airport check-in\n\nResume PDF text',
  });
  expect(sessionRequestBodies.at(-1).known_info_sources).toHaveLength(1);
});

test('New conversation clears the session, assessment and briefing', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));
  expect(await screen.findByDisplayValue('THEN HE WENT TO THEME PARK')).toBeInTheDocument();
  expect(await screen.findByLabelText('Practice result')).toHaveTextContent('Overall 50');

  fireEvent.change(await screen.findByLabelText('Known background'), {
    target: { value: 'I am preparing for a backend interview.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Start' }));
  // Briefing is set, so the mock returns a context-aware opening line.
  await screen.findByText('I reviewed the background you shared. Could you walk me through one project that best matches this role?');

  fireEvent.click(screen.getByRole('button', { name: 'End' }));
  const restart = await screen.findByRole('button', { name: 'New conversation' });
  // History stays visible after End, until the user restarts.
  expect(screen.getByText(scenario.opening_line)).toBeInTheDocument();

  fireEvent.click(restart);

  await waitFor(() => {
    expect(screen.queryByText(scenario.opening_line)).not.toBeInTheDocument();
  });
  expect(screen.queryByRole('button', { name: 'New conversation' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  // Briefing reopened and emptied (text + any PDFs gone).
  expect(screen.getByLabelText('Known background')).toHaveValue('');
  expect(screen.getByLabelText('Read transcript')).toHaveValue('');
  expect(screen.queryByLabelText('Practice result')).not.toBeInTheDocument();
});

test('sends a text turn and shows correction feedback', async () => {
  const textSocket = installTextConversationMock();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  expect(await screen.findByText('Great. Which project is most relevant to this role?')).toBeInTheDocument();
  await waitFor(() => {
    expect(textSocket.sentMessages.some((payload) => eventType(payload) === 'text_turn')).toBe(true);
  });
  expect(global.fetch).not.toHaveBeenCalledWith('/api/sessions/session_1/turns/text', expect.any(Object));
  const assessmentPanel = screen.getByLabelText('Conversation Assessment');
  const assessmentFeedback = within(assessmentPanel).getByLabelText('Assessment feedback');
  expect(assessmentFeedback).toHaveClass('assessment-scroll-list');
  expect(within(assessmentFeedback).getByText('Original')).toBeInTheDocument();
  expect(within(assessmentFeedback).getByText('Corrected')).toBeInTheDocument();
  expect(within(assessmentFeedback).getByText('I am working in this field since three years.')).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('I have been working in this field for three years.')).toBeInTheDocument();
  expect(within(assessmentPanel).getByText('谈论从过去持续到现在的经历，应使用现在完成进行时。')).toBeInTheDocument();
  expect(within(assessmentPanel).queryByText('Pronunciation pending.')).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByRole('heading', { name: 'Grammar / Expression Correction' })).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByText('Low-score words')).not.toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalledWith('/api/grammar/check', expect.any(Object));
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
  const utterance = window.speechSynthesis.speak.mock.calls.at(-1)[0];
  expect(utterance.lang).toBe('en-US');
  expect(utterance.rate).toBe(0.94);
  expect(utterance.voice.name).toBe('Google US English');
});

test('shows local text turn before delayed streamed reply and assessment', async () => {
  installTextConversationMock({ delayedReply: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  expect(await screen.findByText('I am working in this field since three years.')).toBeInTheDocument();
  expect(screen.getByText('AI is thinking...')).toBeInTheDocument();
  expect(screen.queryByText('Great. Which project is most relevant to this role?')).not.toBeInTheDocument();
  expect(within(screen.getByLabelText('Conversation Assessment')).getByText('No assessment yet.')).toBeInTheDocument();

  expect(await screen.findByText('Great. Which project is most relevant to this role?')).toBeInTheDocument();
  expect(screen.queryByText('AI is thinking...')).not.toBeInTheDocument();
});

test('hydrates text assessment if websocket closes after reply before analysis', async () => {
  installTextConversationMock({ disconnectBeforeAnalysis: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.change(screen.getByLabelText('Your reply'), {
    target: { value: 'I am working in this field since three years.' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));

  expect(await screen.findByText('Great. Which project is most relevant to this role?')).toBeInTheDocument();
  const assessmentPanel = screen.getByLabelText('Conversation Assessment');
  expect(await within(assessmentPanel).findByText('I have been working in this field for three years.')).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith('/api/sessions/session_1/analysis', expect.any(Object));
});

test('keeps the latest message visible when new turns arrive near the bottom', async () => {
  installTextConversationMock();
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

test('shows voice ASR text and typing before delayed streamed reply', async () => {
  const voice = installVoiceMocks({ delayedStreamingReply: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('I have worked on backend systems for three years.')).toBeInTheDocument();
  expect(screen.getByText('AI is thinking...')).toBeInTheDocument();
  expect(screen.queryByText('Thanks for sharing that project. What impact did it have?')).not.toBeInTheDocument();
  expect(within(screen.getByLabelText('Conversation Assessment')).getByText('No assessment yet.')).toBeInTheDocument();

  expect(await screen.findByText('Thanks for sharing that project. What impact did it have?')).toBeInTheDocument();
  expect(screen.queryByText('AI is thinking...')).not.toBeInTheDocument();
});

test('renders compatibility reply.text without leaving typing placeholder', async () => {
  const voice = installVoiceMocks({ replyTextCompat: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  expect(await screen.findByText('Thanks for sharing that project. What impact did it have?')).toBeInTheDocument();
  expect(screen.queryByText('AI is thinking...')).not.toBeInTheDocument();
});

test('plays cloud TTS audio when the backend returns audio', async () => {
  installTextConversationMock();
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
  expect(screen.getByText('am working').closest('.mistake-item').querySelector('.mistake-item-header .delete-button'))
    .toHaveTextContent('Delete');
  expect(screen.queryByText('I am working in this field since three years.')).not.toBeInTheDocument();
  expect(screen.getByText('时态错误。')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Review/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Back to Practice' }));
  expect(await screen.findByRole('heading', { name: 'Speaking Coach' })).toBeInTheDocument();
});

test('shows mistake book detail even when progress is still loading', async () => {
  progressNeverResolves = true;
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));
  fireEvent.click(await screen.findByRole('button', { name: /Open Job Interview/ }));

  expect(await screen.findByText('am working')).toBeInTheDocument();
  expect(screen.queryByText('Loading mistake book...')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Score changes')).not.toBeInTheDocument();
});

test('shows summary scores on mistake book records and details', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Mistake Book (2)' }));

  // Overall is now a highlighted chip inline with the other count chips, not a separate row.
  const overallChip = await screen.findByText('Overall 85.6');
  expect(overallChip).toHaveClass('count-chip--score');
  expect(screen.queryByLabelText('Overall score')).not.toBeInTheDocument();
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
  expect(screen.queryByText('I have worked on backend systems for three years.')).not.toBeInTheDocument();
  expect(screen.getByText('Word:')).toBeInTheDocument();
  expect(screen.getByText('Practice sentence:')).toBeInTheDocument();
  expect(screen.getByText('systems').closest('.mistake-item').querySelector('strong')).toBeNull();
  expect(screen.getByRole('button', { name: 'Play word pronunciation' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Play sentence pronunciation' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record word' })).toHaveTextContent('');
  expect(screen.getByRole('button', { name: 'Record sentence' })).toHaveTextContent('');
  window.speechSynthesis.speak.mockClear();
  fireEvent.click(screen.getByRole('button', { name: 'Play word pronunciation' }));
  await waitFor(() => expect(window.speechSynthesis.speak).toHaveBeenCalled());
  expect(window.speechSynthesis.speak.mock.calls.at(-1)[0].text).toBe('systems');
  fireEvent.click(screen.getByRole('button', { name: 'Record word' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  expect(await screen.findByRole('button', { name: 'Stop word recording' })).toHaveTextContent('');
  fireEvent.click(screen.getByRole('button', { name: 'Stop word recording' }));

  const wordScores = await screen.findByLabelText('Practice result');
  const wordResult = wordScores.closest('.mistake-practice-result');
  expect(wordScores).toHaveTextContent('Overall 50');
  expect(wordResult).not.toHaveTextContent('Word:');
  expect(screen.getByRole('button', { name: 'Clear word practice result' })).toBeInTheDocument();
  expect(screen.getAllByText('systems').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: 'Pronunciation 1' })).toBeInTheDocument();
  const uploadCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(uploadCalls.at(-1)[1].body)).toMatchObject({
    reference_text: 'systems',
    mode: 'word',
  });
  fireEvent.click(screen.getByRole('button', { name: 'Clear word practice result' }));
  await waitFor(() => expect(screen.queryByLabelText('Practice result')).not.toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: 'Record sentence' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop sentence recording' }));

  const sentenceScores = await screen.findByLabelText('Practice result');
  const sentenceResult = sentenceScores.closest('.mistake-practice-result');
  expect(sentenceScores).toHaveTextContent('Overall 50');
  expect(sentenceResult).not.toHaveTextContent('Practice sentence:');
  expect(screen.getByRole('button', { name: 'Clear sentence practice result' })).toBeInTheDocument();
  const nextUploadCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(nextUploadCalls.at(-1)[1].body)).toMatchObject({
    reference_text: 'The team reviewed the backend systems before launch.',
    mode: 'sentence',
  });
  fireEvent.click(screen.getByRole('button', { name: 'Clear sentence practice result' }));
  await waitFor(() => expect(screen.queryByLabelText('Practice result')).not.toBeInTheDocument());
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

  expect(screen.getByRole('button', { name: 'Record Reading' })).toBeEnabled();
  fireEvent.click(await screen.findByRole('button', { name: 'Record Reading' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  expect(await screen.findByRole('button', { name: 'Stop Reading' })).toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: 'Stop Reading' }));

  expect(screen.getByRole('heading', { name: 'Reading Practice' })).toBeInTheDocument();
  expect(await screen.findByDisplayValue('THEN HE WENT TO THEME PARK')).toBeInTheDocument();
  expect(await screen.findByText('Practice result: THEN HE WENT TO THEME PARK')).toBeInTheDocument();
  expect(await screen.findByLabelText('Practice result')).toHaveTextContent('Overall 50');
  expect(screen.getByLabelText('Practice result')).toHaveTextContent('Accuracy 60');
  expect(screen.getByLabelText('Practice result')).toHaveTextContent('Fluency 90');
  expect(screen.getByText('Low-score words')).toBeInTheDocument();
  const practiceResult = screen.getByLabelText('Practice result').closest('.pronunciation-result');
  expect(
    within(practiceResult).getByText('Low-score words')
      .compareDocumentPosition(within(practiceResult).getByLabelText('Practice result'))
      & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(screen.getByText('THEME')).toHaveClass('low-word');
  const uploadCall = global.fetch.mock.calls.find(([url]) => url === '/api/pronunciation/practice/upload');
  expect(JSON.parse(uploadCall[1].body)).toMatchObject({
    mime_type: 'audio/webm',
  });
  expect(JSON.parse(uploadCall[1].body)).not.toHaveProperty('reference_text');
  expect(JSON.parse(uploadCall[1].body)).not.toHaveProperty('session_id');
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

test('keeps read aloud practice independent from the active session', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  const fetchCountBeforePractice = global.fetch.mock.calls.length;
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

  const readingPracticePanel = screen.getByLabelText('Reading Practice');
  await within(readingPracticePanel).findByRole('heading', { name: 'Summary' });
  expect(screen.queryByText('Practice using: I have worked on...')).not.toBeInTheDocument();
  const summaryBlock = within(readingPracticePanel).getByRole('heading', { name: 'Summary' }).closest('section');
  expect(summaryBlock.querySelector('.summary-metrics')).toBeInTheDocument();
  expect(within(summaryBlock).getByText('Overall').nextElementSibling).toHaveTextContent('85.6');
  expect(within(summaryBlock).getByText('Grammar').nextElementSibling).toHaveTextContent('100.0');
  expect(within(summaryBlock).getByText('Pronunciation').nextElementSibling).toHaveTextContent('-');
  expect(within(summaryBlock).getByText('Fluency').nextElementSibling).toHaveTextContent('70.0');
  expect(within(summaryBlock).getByText('Vocabulary').nextElementSibling).toHaveTextContent('76.0');
  expect(within(screen.getByLabelText('Conversation Assessment')).queryByRole('heading', { name: 'Summary' }))
    .not.toBeInTheDocument();
  expect(screen.queryByText('Tasks')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Your reply')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'New conversation' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Record' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Record Reading' })).toBeEnabled();
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
  const readingPracticePanel = screen.getByLabelText('Reading Practice');
  expect(within(readingPracticePanel).getByRole('heading', { name: 'Timing' })).toBeInTheDocument();
  expect(within(screen.getByLabelText('Conversation Assessment')).queryByRole('heading', { name: 'Timing' }))
    .not.toBeInTheDocument();
  expect(within(readingPracticePanel).getByText('ASR')).toBeInTheDocument();
  expect(within(readingPracticePanel).getByText('123 ms')).toBeInTheDocument();
  await waitFor(() => expect(within(readingPracticePanel).getByText('TTS')).toBeInTheDocument());
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

test('New conversation ignores stale voice websocket callbacks after reset', async () => {
  const voice = installVoiceMocks();
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  await waitFor(() => expect(voice.sockets).toHaveLength(1));
  const staleSocket = voice.sockets[0];

  fireEvent.click(screen.getByRole('button', { name: 'End' }));
  const restart = await screen.findByRole('button', { name: 'New conversation' });
  fireEvent.click(restart);
  await waitFor(() => expect(screen.queryByText(scenario.opening_line)).not.toBeInTheDocument());

  staleSocket.onmessage?.({
    data: JSON.stringify({
      type: 'asr.final',
      text: 'This old voice turn should be ignored.',
      user_turn_id: 'stale_user_turn',
    }),
  });
  staleSocket.onmessage?.({
    data: JSON.stringify({
      type: 'reply.delta',
      text: 'Old AI text',
    }),
  });
  staleSocket.onmessage?.({
    data: JSON.stringify({
      type: 'analysis.result',
      stage: 'grammar',
      turn_id: 'stale_user_turn',
      result: grammarCorrection({ user_text: 'This old voice turn should be ignored.' }),
    }),
  });
  staleSocket.onclose?.();

  expect(screen.queryByText('This old voice turn should be ignored.')).not.toBeInTheDocument();
  expect(screen.queryByText('Old AI text')).not.toBeInTheDocument();
  expect(within(screen.getByLabelText('Conversation Assessment')).getByText('No assessment yet.')).toBeInTheDocument();
  expect(screen.getByText('Ready')).toBeInTheDocument();
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
  await waitFor(() => expect(within(assessmentPanel).getByLabelText('Assessment feedback')).toHaveClass('assessment-scroll-list'));
  const assessmentFeedback = within(assessmentPanel).getByLabelText('Assessment feedback');
  await waitFor(() => expect(within(assessmentFeedback).getByLabelText('Assessment scores')).toHaveTextContent('Overall 72'));
  expect(within(assessmentPanel).queryByRole('heading', { name: 'Pronunciation' })).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByText('Low-score words')).not.toBeInTheDocument();
  expect(within(assessmentPanel).queryByText('Pronunciation pending.')).not.toBeInTheDocument();
  expect(within(assessmentFeedback).getByText('Original')).toBeInTheDocument();
  expect(within(assessmentFeedback).getByText('systems')).toHaveClass('low-word');
});

test('keeps the latest assessment visible when pronunciation updates an existing turn', async () => {
  const voice = installVoiceMocks({ voicePronunciationResult: true, delayedPronunciationResult: true });
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Start' }));
  await screen.findByText(scenario.opening_line);
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));

  await waitFor(() => expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  const assessmentPanel = await screen.findByLabelText('Conversation Assessment');
  await waitFor(() => expect(within(assessmentPanel).getByLabelText('Assessment feedback')).toBeInTheDocument());
  const assessmentFeedback = within(assessmentPanel).getByLabelText('Assessment feedback');
  expect(within(assessmentFeedback).queryByLabelText('Assessment scores')).not.toBeInTheDocument();
  setScrollMetrics(assessmentFeedback, { clientHeight: 220, scrollHeight: 900 });
  assessmentFeedback.scrollTop = 100;

  await waitFor(() => expect(within(assessmentFeedback).getByLabelText('Assessment scores')).toHaveTextContent('Overall 72'));
  expect(assessmentFeedback.scrollTop).toBe(900);
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
  const sockets = [];
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
      sockets.push(this);
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
          const replyText = options.streamingReply
            ? 'That sounds useful. What did you own?'
            : 'Thanks for sharing that project. What impact did it have?';
          const sendReplyTiming = () => {
            this.onmessage?.({
              data: JSON.stringify({
                type: 'debug.timing',
                stage: 'reply',
                timings: {
                  asr_ms: 123,
                  dialogue_reply_ms: 45,
                  end_turn_to_reply_text_ms: 190,
                  end_turn_to_reply_done_ms: 190,
                },
              }),
            });
          };
          const sendAnalysisAfterReply = () => {
            if (options.delayedAnalysis) {
              setTimeout(() => this.sendAnalysisResult(), 80);
              return;
            }
            this.sendAnalysisResult();
          };
          const sendTextReply = () => {
            this.onmessage?.({
              data: JSON.stringify({
                type: 'reply.text',
                text: replyText,
                turn_id: 'turn_ai_voice_1',
                user_turn_id: 'turn_user_voice_1',
              }),
            });
            sendReplyTiming();
            sendAnalysisAfterReply();
          };
          const sendStreamingReply = () => {
            const splitAt = Math.min(
              replyText.length,
              Math.max(1, replyText.indexOf(' ') + 1 || 1),
            );
            this.onmessage?.({
              data: JSON.stringify({ type: 'reply.delta', text: replyText.slice(0, splitAt) }),
            });
            this.onmessage?.({
              data: JSON.stringify({ type: 'reply.delta', text: replyText.slice(splitAt) }),
            });
            this.onmessage?.({
              data: JSON.stringify({
                type: 'reply.done',
                text: replyText,
                turn_id: options.streamingReply ? 'turn_ai_stream_1' : 'turn_ai_voice_1',
                user_turn_id: 'turn_user_voice_1',
              }),
            });
            sendReplyTiming();
            sendAnalysisAfterReply();
          };
          if (options.delayedReply || options.replyTextCompat) {
            if (options.delayedReply) {
              setTimeout(sendTextReply, 80);
              return;
            }
            sendTextReply();
            return;
          }
          if (options.delayedStreamingReply) {
            setTimeout(sendStreamingReply, 120);
            return;
          }
          sendStreamingReply();
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
        if (options.delayedPronunciationResult) {
          setTimeout(() => this.sendPronunciationResult(), 80);
          return;
        }
        this.sendPronunciationResult();
      }
    }

    sendPronunciationResult() {
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

    close() {
      this.readyState = FakeWebSocket.CLOSED;
      this.onclose?.();
    }
  }

  vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
  vi.stubGlobal('WebSocket', FakeWebSocket);

  return { getUserMedia, sentMessages, sockets };
}

function installTextConversationMock(options = {}) {
  const sentMessages = [];

  class FakeTextWebSocket {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 3;

    constructor(url) {
      this.url = url;
      this.readyState = FakeTextWebSocket.CONNECTING;
      setTimeout(() => {
        this.readyState = FakeTextWebSocket.OPEN;
        this.onopen?.();
      }, 0);
    }

    send(payload) {
      sentMessages.push(payload);
      if (eventType(payload) !== 'text_turn') {
        return;
      }
      const text = JSON.parse(payload).text;
      setTimeout(() => this.sendTextTurn(text), 0);
    }

    sendTextTurn(text) {
      this.onmessage?.({
        data: JSON.stringify({
          type: 'user.final',
          text,
          turn_id: 'turn_user_text_1',
          user_turn_id: 'turn_user_text_1',
        }),
      });
      const sendReply = () => {
        const replyText = 'Great. Which project is most relevant to this role?';
        this.onmessage?.({
          data: JSON.stringify({ type: 'reply.delta', text: 'Great. ' }),
        });
        this.onmessage?.({
          data: JSON.stringify({ type: 'reply.delta', text: 'Which project is most relevant to this role?' }),
        });
        this.onmessage?.({
          data: JSON.stringify({
            type: 'reply.done',
            text: replyText,
            turn_id: 'turn_ai_text_1',
            user_turn_id: 'turn_user_text_1',
          }),
        });
        this.onmessage?.({
          data: JSON.stringify({
            type: 'debug.timing',
            stage: 'reply',
            timings: {
              text_turn_to_user_final_ms: 1,
              reply_first_delta_ms: 10,
              reply_delta_count: 2,
              text_turn_to_reply_done_ms: 20,
            },
          }),
        });
        this.onmessage?.({
          data: JSON.stringify({ type: 'analysis.pending', stages: ['grammar'] }),
        });
        if (options.disconnectBeforeAnalysis) {
          this.close();
          return;
        }
        if (options.delayedAnalysis) {
          setTimeout(() => this.sendAnalysisResult(), 80);
          return;
        }
        this.sendAnalysisResult();
      };
      if (options.delayedReply) {
        setTimeout(sendReply, 120);
        return;
      }
      sendReply();
    }

    sendAnalysisResult() {
      this.onmessage?.({
        data: JSON.stringify({
          type: 'analysis.result',
          stage: 'grammar',
          turn_id: 'turn_user_text_1',
          result: grammarCorrection(),
        }),
      });
      this.close();
    }

    close() {
      this.readyState = FakeTextWebSocket.CLOSED;
      this.onclose?.();
    }
  }

  vi.stubGlobal('WebSocket', FakeTextWebSocket);
  return { sentMessages };
}

function eventType(payload) {
  if (typeof payload !== 'string') {
    return null;
  }
  return JSON.parse(payload).type;
}
