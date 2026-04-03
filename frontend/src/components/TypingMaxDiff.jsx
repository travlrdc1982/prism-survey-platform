import { useState, useRef } from 'react';

/**
 * MaxDiff Typing Tool — page.group.3
 *
 * Large 3D sphere buttons. Green fill for MOST, red fill for LEAST.
 * Row backgrounds change on selection. Centered statement text.
 * Card flip animation on advance. Section header + card counter.
 */
export default function TypingMaxDiff({ battery, onSubmit }) {
  const bibdTasks = battery?.bibd_tasks || [];
  const itemTexts = battery?.item_texts || [];
  const nTasks = battery?.n_tasks || bibdTasks.length;

  const [currentTask, setCurrentTask] = useState(0);
  const [responses, setResponses] = useState([]);
  const [best, setBest] = useState(null);
  const [worst, setWorst] = useState(null);
  const [flipDirection, setFlipDirection] = useState(null);
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

    setFlipDirection('flip-left');

    setTimeout(() => {
      setResponses(newResponses);
      setBest(null);
      setWorst(null);
      setFlipDirection(null);

      if (currentTask < nTasks - 1) {
        setCurrentTask(currentTask + 1);
      } else {
        const itemIds = battery?.item_ids || {};
        const nItems = Object.keys(itemIds).length;
        const bwScores = {};
        for (let i = 1; i <= nItems; i++) bwScores[i] = 0;
        newResponses.forEach(r => {
          bwScores[r.best] = (bwScores[r.best] || 0) + 1;
          bwScores[r.worst] = (bwScores[r.worst] || 0) - 1;
        });
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
      {/* Section header */}
      <div className="maxdiff-section-header">
        <span className="maxdiff-section-title">SECTION 2: VALUES &amp; ATTITUDES</span>
        <span className="maxdiff-section-counter">3 of 6 Questions</span>
      </div>

      <div className="progress-bar" style={{ marginBottom: 16 }}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Card counter right-aligned */}
      <div className="maxdiff-task-counter">
        {currentTask + 1} of {nTasks} Cards
      </div>

      <div className="question-text">
        {battery?.question_text || 'From the set of short statements expressing different points of view about politics, culture and health.'}
      </div>

      {/* Instruction line with arrows */}
      <div className="maxdiff-instruction-line">
        <span className="maxdiff-arrow-red">&#x25C0;</span>
        <span className="maxdiff-instruction-text">
          Select one statement that sounds <strong>MOST</strong> like your own point of view,
          and the one statement that sounds <strong>LEAST</strong> like you
        </span>
        <span className="maxdiff-arrow-green">&#x25B6;</span>
      </div>

      {/* MaxDiff card with flip */}
      <div
        ref={cardRef}
        className={`maxdiff-task${flipDirection ? ` ${flipDirection}` : ''}`}
      >
        <div className="maxdiff-task-header">
          <span className="maxdiff-header-worst">LEAST<br/>LIKE ME</span>
          <span className="maxdiff-header-best">MOST<br/>LIKE ME</span>
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
                className={`maxdiff-sphere-btn maxdiff-sphere-worst${isWorst ? ' selected' : ''}`}
                onClick={() => handleWorst(itemIdx)}
                role="radio"
                aria-checked={isWorst}
                aria-label={`Least like me: ${text}`}
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleWorst(itemIdx); }}
              >
                {isWorst && <span className="sphere-check">&#x2713;</span>}
              </div>
              <div className="maxdiff-item-text">{text}</div>
              <div
                className={`maxdiff-sphere-btn maxdiff-sphere-best${isBest ? ' selected' : ''}`}
                onClick={() => handleBest(itemIdx)}
                role="radio"
                aria-checked={isBest}
                aria-label={`Most like me: ${text}`}
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') handleBest(itemIdx); }}
              >
                {isBest && <span className="sphere-check">&#x2713;</span>}
              </div>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!canAdvance} onClick={handleNext}>
        CONTINUE &gt;
      </button>
    </div>
  );
}
