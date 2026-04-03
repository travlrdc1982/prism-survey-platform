import { useState } from 'react';

export default function Checklist({ content, onSubmit }) {
  const items = content.items || content.options || [];
  const varPrefix = content.var || 'checklist';
  const minSelections = content.min_selections || 0;
  const maxSelections = content.max_selections || items.length;

  const [selected, setSelected] = useState(new Set());

  const handleToggle = (idx) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        if (next.size < maxSelections) {
          next.add(idx);
        }
      }
      return next;
    });
  };

  const canSubmit = selected.size >= minSelections;

  const handleSubmit = () => {
    const result = {};
    items.forEach((item, i) => {
      const key = typeof item === 'object' && item.var ? item.var : `${varPrefix}_${i + 1}`;
      result[key] = selected.has(i) ? 1 : 0;
    });
    onSubmit(result);
  };

  return (
    <div className="survey-card">
      {content.question_text && <div className="question-text">{content.question_text}</div>}
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div className="option-list" style={{ marginTop: 8 }}>
        {items.map((item, i) => {
          const label = typeof item === 'string' ? item : item.text || item.label || item.name;
          const isSelected = selected.has(i);
          return (
            <div
              key={i}
              className={`option-item${isSelected ? ' selected' : ''}`}
              onClick={() => handleToggle(i)}
            >
              <div style={{
                width: 20,
                height: 20,
                borderRadius: 4,
                border: `2px solid ${isSelected ? 'var(--radio-selected-green)' : 'var(--border-medium)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                background: isSelected ? 'var(--radio-selected-green)' : 'transparent',
                color: '#fff',
                fontSize: 12,
                fontWeight: 700,
              }}>
                {isSelected && '\u2713'}
              </div>
              <span>{label}</span>
            </div>
          );
        })}
      </div>

      {maxSelections < items.length && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8 }}>
          Select up to {maxSelections} ({selected.size} selected)
        </div>
      )}

      <button className="btn-next" disabled={!canSubmit} onClick={handleSubmit}>
        Next
      </button>
    </div>
  );
}
