import { useState } from 'react';

export default function InvestmentStimulus({ content, onSubmit }) {
  const [awareness, setAwareness] = useState(null);
  const varName = content.var || 'awareness';
  const options = content.options || ['Yes', 'No', 'Not sure'];

  return (
    <div className="survey-card">
      {content.stimulus_text && (
        <div style={{
          background: 'var(--bg-page)',
          border: '1.5px solid var(--border-light)',
          borderRadius: '8px',
          padding: '20px',
          marginBottom: '24px',
          fontSize: '15px',
          lineHeight: '1.6',
        }}>
          {content.stimulus_text}
        </div>
      )}

      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div className="option-list">
        {options.map((opt, i) => {
          const label = typeof opt === 'string' ? opt : opt.text || opt.label;
          return (
            <div
              key={i}
              className={`option-item${awareness === i + 1 ? ' selected' : ''}`}
              onClick={() => setAwareness(i + 1)}
            >
              <div className="option-radio" />
              <span>{label}</span>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={awareness === null} onClick={() => onSubmit({ [varName]: awareness })}>
        Next
      </button>
    </div>
  );
}
