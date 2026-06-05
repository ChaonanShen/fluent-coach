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
    throw new Error(`Unhandled request: ${url}`);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
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
});

test('reviews a saved mistake', async () => {
  render(<App />);

  const review = await screen.findByRole('button', { name: 'Review 0' });
  fireEvent.click(review);

  expect(await screen.findByRole('button', { name: 'Review 1' })).toBeInTheDocument();
});

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  });
}
