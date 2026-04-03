import { useState } from 'react';

export default function OptIn({ content, onSubmit }) {
  const [optIn, setOptIn] = useState(null);
  const [email, setEmail] = useState('');
  const varName = content.var || 'opt_in';

  const canSubmit = optIn !== null && (optIn === 2 || (optIn === 1 && email.trim().length > 0));

  const handleSubmit = () => {
    const result = { [varName]: optIn };
    if (optIn === 1) {
      result[`${varName}_email`] = email.trim();
    }
    onSubmit(result);
  };

  return (
    <div className="survey-card">
      {content.question_text && <div className="question-text">{content.question_text}</div>}
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div className="option-list" style={{ marginTop: 16 }}>
        <div
          className={`option-item${optIn === 1 ? ' selected' : ''}`}
          onClick={() => setOptIn(1)}
        >
          <div className="option-radio" />
          <span>Yes, I would like to participate</span>
        </div>
        <div
          className={`option-item${optIn === 2 ? ' selected' : ''}`}
          onClick={() => setOptIn(2)}
        >
          <div className="option-radio" />
          <span>No, thank you</span>
        </div>
      </div>

      {optIn === 1 && (
        <div style={{ marginTop: 16 }}>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Enter your email address"
            style={{
              width: '100%',
              padding: '12px 16px',
              border: '1.5px solid var(--border-light)',
              borderRadius: 8,
              fontFamily: 'var(--font-secondary)',
              fontSize: 15,
            }}
          />
        </div>
      )}

      <button className="btn-next" disabled={!canSubmit} onClick={handleSubmit}>
        Next
      </button>
    </div>
  );
}
