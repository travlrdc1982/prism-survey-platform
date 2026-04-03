import { useState } from 'react';

export default function RankSort({ content, onSubmit }) {
  const items = content.items || [];
  const rankPositions = content.rank_positions || items.length;
  const minRanks = content.min_ranks || rankPositions;
  const varName = content.var || 'rank';

  // ranks: { itemIndex: rankNumber } e.g. { 0: 1, 2: 2 }
  const [ranks, setRanks] = useState({});

  const nextRank = () => {
    const usedRanks = Object.values(ranks);
    for (let r = 1; r <= rankPositions; r++) {
      if (!usedRanks.includes(r)) return r;
    }
    return null;
  };

  const handleClick = (itemIdx) => {
    setRanks(prev => {
      const copy = { ...prev };
      if (copy[itemIdx] !== undefined) {
        // Remove this rank and shift others down
        const removedRank = copy[itemIdx];
        delete copy[itemIdx];
        // Decrement ranks above the removed one
        Object.keys(copy).forEach(key => {
          if (copy[key] > removedRank) {
            copy[key] = copy[key] - 1;
          }
        });
        return copy;
      }
      const nr = nextRank();
      if (nr === null) return prev;
      return { ...copy, [itemIdx]: nr };
    });
  };

  const assignedCount = Object.keys(ranks).length;
  const canSubmit = assignedCount >= minRanks;

  const handleSubmit = () => {
    const result = {};
    items.forEach((item, i) => {
      const key = typeof item === 'object' && item.var ? item.var : `${varName}_${i + 1}`;
      result[key] = ranks[i] !== undefined ? ranks[i] : null;
    });
    onSubmit(result);
  };

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}
      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
        Click items to rank them 1 through {rankPositions}. Click again to remove.
      </div>

      <div className="option-list">
        {items.map((item, i) => {
          const label = typeof item === 'string' ? item : item.text || item.label || item.name;
          const rank = ranks[i];
          return (
            <div
              key={i}
              className="rank-item"
              onClick={() => handleClick(i)}
              style={rank !== undefined ? { borderColor: 'var(--brand-green)', background: 'var(--card-selected-green)' } : {}}
            >
              {rank !== undefined ? (
                <div className="rank-number">{rank}</div>
              ) : (
                <div className="rank-number" style={{ background: 'var(--border-light)', color: 'var(--text-secondary)' }}>-</div>
              )}
              <span>{label}</span>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!canSubmit} onClick={handleSubmit}>
        Next
      </button>
    </div>
  );
}
