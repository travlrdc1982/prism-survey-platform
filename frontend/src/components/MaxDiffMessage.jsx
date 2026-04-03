import { useState } from 'react';

export default function MaxDiffMessage({ content, onSubmit }) {
  const bibdTasks = content.bibd_tasks || [];
  const itemTexts = content.item_texts || [];
  const nTasks = content.n_tasks || bibdTasks.length;
  const varPrefix = content.var || 'md';

  const [currentTask, setCurrentTask] = useState(0);
  const [responses, setResponses] = useState([]); // array of { best, worst } per task
  const [best, setBest] = useState(null);
  const [worst, setWorst] = useState(null);

  const task = bibdTasks[currentTask] || [];

  const handleBest = (itemIdx) => {
    if (worst === itemIdx) return; // cannot select same for both
    setBest(itemIdx);
  };

  const handleWorst = (itemIdx) => {
    if (best === itemIdx) return;
    setWorst(itemIdx);
  };

  const canAdvance = best !== null && worst !== null;

  const handleNext = () => {
    const newResponses = [...responses, { best, worst, task: currentTask }];
    setResponses(newResponses);
    setBest(null);
    setWorst(null);

    if (currentTask < nTasks - 1) {
      setCurrentTask(currentTask + 1);
    } else {
      // Build result
      const result = {};
      newResponses.forEach((r, ti) => {
        result[`${varPrefix}_t${ti + 1}_best`] = r.best;
        result[`${varPrefix}_t${ti + 1}_worst`] = r.worst;
      });
      onSubmit(result);
    }
  };

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
        Task {currentTask + 1} of {nTasks}
      </div>
      <div className="progress-bar" style={{ marginBottom: '20px' }}>
        <div className="progress-fill" style={{ width: `${(currentTask / nTasks) * 100}%` }} />
      </div>

      <div className="maxdiff-task">
        <div className="maxdiff-task-header">
          <span style={{ color: 'var(--text-green)' }}>Most Compelling</span>
          <span style={{ color: 'var(--text-red)' }}>Least Compelling</span>
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
                className={`maxdiff-radio-best${isBest ? ' selected' : ''}`}
                onClick={() => handleBest(itemIdx)}
              />
              <div className="maxdiff-item-text">{text}</div>
              <div
                className={`maxdiff-radio-worst${isWorst ? ' selected' : ''}`}
                onClick={() => handleWorst(itemIdx)}
              />
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!canAdvance} onClick={handleNext}>
        {currentTask < nTasks - 1 ? 'Next Task' : 'Continue'}
      </button>
    </div>
  );
}
