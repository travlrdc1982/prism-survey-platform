import { useState } from 'react';

export default function DropdownGrid({ content, onSubmit }) {
  const items = content.items || [];
  const options = content.options || [];
  const varPrefix = content.var || 'dropdown';

  const [responses, setResponses] = useState({});

  const handleChange = (itemIdx, value) => {
    setResponses(prev => ({ ...prev, [itemIdx]: value }));
  };

  const allAnswered = items.length > 0 && items.every((_, i) => responses[i] !== undefined && responses[i] !== '');

  const handleSubmit = () => {
    const result = {};
    items.forEach((item, i) => {
      const key = typeof item === 'object' && item.var ? item.var : `${varPrefix}_${i + 1}`;
      result[key] = parseInt(responses[i], 10) || responses[i];
    });
    onSubmit(result);
  };

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div className="option-list">
        {items.map((item, i) => {
          const label = typeof item === 'string' ? item : item.text || item.label || item.name;
          return (
            <div key={i} style={{ marginBottom: '12px' }}>
              <div style={{ fontSize: '14px', marginBottom: '6px', fontWeight: 500 }}>{label}</div>
              <select
                className="dropdown-select"
                value={responses[i] || ''}
                onChange={(e) => handleChange(i, e.target.value)}
              >
                <option value="">-- Select --</option>
                {options.map((opt, oi) => {
                  const optLabel = typeof opt === 'string' ? opt : opt.text || opt.label;
                  const optValue = typeof opt === 'object' && opt.value !== undefined ? opt.value : oi + 1;
                  return (
                    <option key={oi} value={optValue}>{optLabel}</option>
                  );
                })}
              </select>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!allAnswered} onClick={handleSubmit}>
        Next
      </button>
    </div>
  );
}
