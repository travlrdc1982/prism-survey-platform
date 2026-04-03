import { useState } from 'react';

export default function MatrixGrid({ content, onSubmit }) {
  const items = content.items || content.items_always || [];
  const scale = content.scale || 11;
  const leftAnchor = content.left_anchor || '0';
  const rightAnchor = content.right_anchor || '10';
  const hasNotFamiliar = content.has_not_familiar || false;
  const varPrefix = content.var || 'matrix';

  const [responses, setResponses] = useState({});

  const scalePoints = Array.from({ length: scale }, (_, i) => i);

  const handleSelect = (itemIdx, value) => {
    setResponses(prev => ({ ...prev, [itemIdx]: value }));
  };

  const allAnswered = items.length > 0 && items.every((_, i) => responses[i] !== undefined);

  const handleSubmit = () => {
    const result = {};
    items.forEach((item, i) => {
      const key = typeof item === 'object' ? item.var || `${varPrefix}_${i + 1}` : `${varPrefix}_${i + 1}`;
      result[key] = responses[i];
    });
    onSubmit(result);
  };

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div style={{ overflowX: 'auto' }}>
        <table className="matrix-table">
          <thead>
            <tr>
              <th></th>
              {scalePoints.map(p => (
                <th key={p} className="matrix-cell" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {p === 0 ? leftAnchor : p === scale - 1 ? rightAnchor : p}
                </th>
              ))}
              {hasNotFamiliar && (
                <th className="matrix-cell" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>N/F</th>
              )}
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const label = typeof item === 'string' ? item : item.text || item.label || item.name;
              return (
                <tr key={i} className="matrix-row">
                  <td className="matrix-item-label" title={label}>{label}</td>
                  {scalePoints.map(p => (
                    <td key={p} className="matrix-cell">
                      <div
                        className={`matrix-radio${responses[i] === p ? ' selected' : ''}`}
                        onClick={() => handleSelect(i, p)}
                      />
                    </td>
                  ))}
                  {hasNotFamiliar && (
                    <td className="matrix-cell">
                      <div
                        className={`matrix-radio not-familiar${responses[i] === 99 ? ' selected' : ''}`}
                        onClick={() => handleSelect(i, 99)}
                      />
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button className="btn-next" disabled={!allAnswered} onClick={handleSubmit}>
        Next
      </button>
    </div>
  );
}
