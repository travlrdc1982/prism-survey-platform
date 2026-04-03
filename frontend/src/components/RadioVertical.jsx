import { useState } from 'react';

export default function RadioVertical({ content, onSubmit }) {
  const [selected, setSelected] = useState(null);
  const varName = content.var;
  const options = content.options || [];

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}
      <div className="option-list">
        {options.map((opt, i) => (
          <div
            key={i}
            className={`option-item${selected === i + 1 ? ' selected' : ''}`}
            onClick={() => setSelected(i + 1)}
          >
            <div className="option-radio" />
            <span>{typeof opt === 'string' ? opt : opt.text || opt.label}</span>
          </div>
        ))}
      </div>
      <button className="btn-next" disabled={selected === null} onClick={() => onSubmit({ [varName]: selected })}>
        Next
      </button>
    </div>
  );
}
