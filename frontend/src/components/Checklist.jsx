import { useState } from 'react';

/**
 * Generic Checklist component — STYLE.CHECKLIST
 * Supports:
 * - min/max selections
 * - "exclusive" items (like "None of these") that clear all others
 * - "Prefer not to respond" checkbox
 */
export default function Checklist({ content, onSubmit }) {
  const items = content.items || content.options || [];
  const varPrefix = content.var || 'checklist';
  const minSelections = content.min_selections || 0;
  const maxSelections = content.max_selections || items.length;
  const showPnr = content.show_prefer_not !== false;

  const [selected, setSelected] = useState(new Set());
  const [preferNot, setPreferNot] = useState(false);

  const handleToggle = (idx) => {
    const item = items[idx];
    const isExclusive = typeof item === 'object' && item.exclusive;

    setSelected(prev => {
      const next = new Set(prev);

      if (isExclusive) {
        if (next.has(idx)) {
          next.delete(idx);
        } else {
          next.clear();
          next.add(idx);
        }
      } else {
        // Remove any exclusive items when selecting non-exclusive
        items.forEach((it, i) => {
          if (typeof it === 'object' && it.exclusive) next.delete(i);
        });

        if (next.has(idx)) {
          next.delete(idx);
        } else {
          if (next.size < maxSelections) {
            next.add(idx);
          }
        }
      }
      return next;
    });
    setPreferNot(false);
  };

  const handlePnr = (checked) => {
    setPreferNot(checked);
    if (checked) {
      setSelected(new Set());
    }
  };

  const canSubmit = preferNot || selected.size >= minSelections;

  const handleSubmit = () => {
    if (preferNot) {
      onSubmit({ [`${varPrefix}_pnr`]: 1 });
      return;
    }
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

      <div className="influence-checklist" style={{ marginTop: 8 }}>
        {items.map((item, i) => {
          const label = typeof item === 'string' ? item : item.text || item.label || item.name;
          const isExclusive = typeof item === 'object' && item.exclusive;
          const isSelected = selected.has(i);
          return (
            <div
              key={i}
              className={`checklist-item${isSelected ? ' selected' : ''}${isExclusive ? ' exclusive-option' : ''}`}
              onClick={() => !preferNot && handleToggle(i)}
              style={preferNot ? { opacity: 0.5, pointerEvents: 'none' } : {}}
            >
              <div className={`checklist-checkbox${isSelected ? ' checked' : ''}`}>
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

      {showPnr && (
        <label className="prefer-not-respond">
          <input type="checkbox" checked={preferNot} onChange={e => handlePnr(e.target.checked)} />
          <span>Prefer not to respond</span>
        </label>
      )}

      <button className="btn-next" disabled={!canSubmit} onClick={handleSubmit}>
        CONTINUE &gt;
      </button>
    </div>
  );
}
