import { useState } from 'react';

export default function ButtonHorizontal({ content, onSubmit }) {
  const [selected, setSelected] = useState(null);
  const options = content.options || [];
  const varName = content.var || 'button';

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div className="scale-row">
        {options.map((opt, i) => {
          const label = typeof opt === 'string' ? opt : opt.text || opt.label || (i + 1);
          return (
            <button
              key={i}
              className={`scale-btn${selected === i + 1 ? ' selected' : ''}`}
              onClick={() => setSelected(i + 1)}
            >
              {label}
            </button>
          );
        })}
      </div>

      <button className="btn-next" disabled={selected === null} onClick={() => onSubmit({ [varName]: selected })}>
        Next
      </button>
    </div>
  );
}
