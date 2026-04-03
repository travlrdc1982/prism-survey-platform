import { useState } from 'react';

export default function OpenText({ content, onSubmit }) {
  const [text, setText] = useState('');
  const varName = content.var || 'open_text';
  const minLength = content.min_length || 0;

  const canSubmit = text.trim().length >= minLength;

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <textarea
        className="open-text-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={content.placeholder || 'Type your response here...'}
      />

      {minLength > 0 && (
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '8px' }}>
          Minimum {minLength} characters ({text.trim().length} entered)
        </div>
      )}

      <button className="btn-next" disabled={!canSubmit} onClick={() => onSubmit({ [varName]: text.trim() })}>
        Next
      </button>
    </div>
  );
}
