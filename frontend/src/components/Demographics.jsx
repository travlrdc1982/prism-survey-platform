import { useState } from 'react';

export default function Demographics({ content, onSubmit }) {
  const questions = content.questions || [];
  const [responses, setResponses] = useState({});

  // If no structured questions, just show a placeholder with a continue button
  if (questions.length === 0) {
    return (
      <div className="survey-card">
        <div className="question-text">{content.question_text || 'Demographics'}</div>
        {content.comments_text && <div className="comments-text">{content.comments_text}</div>}
        <button className="btn-next" onClick={() => onSubmit({})}>
          Continue
        </button>
      </div>
    );
  }

  const handleSelect = (qKey, value) => {
    setResponses(prev => ({ ...prev, [qKey]: value }));
  };

  const allAnswered = questions.every(q => responses[q.key] !== undefined);

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text || 'Demographics'}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      {questions.map((q, qi) => (
        <div key={qi} style={{ marginBottom: '24px' }}>
          <div style={{ fontSize: '15px', fontWeight: 500, marginBottom: '10px' }}>{q.text}</div>
          <div className="option-list">
            {(q.options || []).map((opt, oi) => {
              const label = typeof opt === 'string' ? opt : opt.text || opt.label;
              return (
                <div
                  key={oi}
                  className={`option-item${responses[q.key] === oi + 1 ? ' selected' : ''}`}
                  onClick={() => handleSelect(q.key, oi + 1)}
                >
                  <div className="option-radio" />
                  <span>{label}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <button className="btn-next" disabled={!allAnswered} onClick={() => onSubmit(responses)}>
        Continue
      </button>
    </div>
  );
}
