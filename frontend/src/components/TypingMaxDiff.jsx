import { useState, useRef } from 'react';

/**
 * MaxDiff Typing Tool — page.group.3
 *
 * Shows cards of 4 statements each. User picks MOST LIKE ME (green, left)
 * and LEAST LIKE ME (red, right). Cards flip from right to left on advance.
 * Cannot select same row for both. CONTINUE disabled until both chosen.
 */
export default function TypingMaxDiff({ battery, onSubmit }) {
  const bibdTasks = battery?.bibd_tasks || [];
  const itemTexts = battery?.item_texts || [];
  const nTasks = battery?.n_tasks || bibdTasks.length;
  const varPrefix = battery?.var || 'md';

  const [currentTask, setCurrentTask] = useState(0);
  const [responses, setResponses] = useState([]);
  const [best, setBest] = useState(null);
  const [worst, setWorst] = useState(null);
  const [flipDirection, setFlipDirection] = useState(null); // 'flip-left' | null
  const cardRef = useRef(null);

  const task = bibdTasks[currentTask] || [];

  const handleBest = (itemIdx) => {
    if (worst === itemIdx) return;
    setBest(itemIdx);
  };

  const handleWorst = (itemIdx) => {
    if (best === itemIdx) return;
    setWorst(itemIdx);
  };

  const canAdvance = best !== null && worst !== null;

  const handleNext = () => {
    const newResponses = [...responses, { best, worst, task: currentTask }];

    // Trigger flip animation
    setFlipDirection('flip-left');

    setTimeout(() => {
      setResponses(newResponses);
      setBest(null);
      setWorst(null);
      setFlipDirection(null);

      if (currentTask < nTasks - 1) {
        setCurrentTask(currentTask + 1);
      } else {
        // Reconstruct B-W scores per item, then map to item_ids
        const itemIds = battery?.item_ids || {};
        const nItems = Object.keys(itemIds).length;
        const bwScores = {};
        for (let i = 1; i <= nItems; i++) bwScores[i] = 0;
        newResponses.forEach(r => {
          bwScores[r.best] = (bwScores[r.best] || 0) + 1;
          bwScores[r.worst] = (bwScores[r.worst] || 0) - 1;
        });
        // Convert to {item_id: raw_score} for typing API
        const result = {};
        Object.entries(bwScores).forEach(([itemNum, score]) => {
          const itemId = itemIds[parseInt(itemNum)];
          if (itemId) result[itemId] = score;
        });
        onSubmit(result);
      }
    }, 350);
  };

  if (!bibdTasks.length) {
    return (
      <div className="survey-card">
        <div className="question-text">Loading typing battery...</div>
      </div>
    );
  }

  const progress = ((currentTask) / nTasks) * 100;

  return (
    <div className="survey-card typing-maxdiff-card">
      <div className="question-text">
        {battery?.question_text || 'Which of these is MOST and LEAST like you?'}
      </div>
      {battery?.comments_text && <div className="comments-text">{battery.comments_text}</div>}

      {/* Task counter */}
      <div className="maxdiff-task-counter">
        {currentTask + 1} of {nTasks} Cards
      </div>
      <div className="progress-bar" style={{ marginBottom: 20 }}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* MaxDiff card */}
      <div
        ref={cardRef}
        className={`maxdiff-task${flipDirection ? ` ${flipDirection}` : ''}`}
      >
        <div className="maxdiff-task-header">
          <span className="maxdiff-header-best">MOST LIKE ME</span>
          <span className="maxdiff-header-worst">LEAST LIKE ME</span>
        </div>

        {task.map((itemIdx, ri) => {
          const text = itemTexts[itemIdx] || `Item ${itemIdx}`;
          const isBest = best === itemIdx;
          const isWorst = worst === itemIdx;
          let rowClass = 'maxdiff-row';
          if (isBest) rowClass += ' best-selected';
          if (isWorst) rowClass += ' worst-selected';

          return (
            <div key={ri} className={rowClass}>
              <div
                className={`maxdiff-sphere-btn maxdiff-sphere-best${isBest ? ' selected' : ''}`}
                onClick={() => handleBest(itemIdx)}
                role="radio"
                aria-checked={isBest}
                aria-label={`Most like me: ${text}`}
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleBest(itemIdx); }}
              >
                {isBest && <span className="sphere-check">{'\u2713'}</span>}
              </div>
              <div className="maxdiff-item-text">{text}</div>
              <div
                className={`maxdiff-sphere-btn maxdiff-sphere-worst${isWorst ? ' selected' : ''}`}
                onClick={() => handleWorst(itemIdx)}
                role="radio"
                aria-checked={isWorst}
                aria-label={`Least like me: ${text}`}
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleWorst(itemIdx); }}
              >
                {isWorst && <span className="sphere-check">{'\u2713'}</span>}
              </div>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!canAdvance} onClick={handleNext}>
        {currentTask < nTasks - 1 ? 'CONTINUE >' : 'CONTINUE >'}
      </button>
    </div>
  );
}
