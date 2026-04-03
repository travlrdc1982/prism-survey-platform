import { useState, useMemo } from 'react';

function shuffleArray(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function CardShuffle({ content, onSubmit }) {
  const items = content.items || [];
  const options = content.options || [];
  const scalePoints = content.scale_points || options.length;
  const shouldShuffle = content.shuffle !== false;
  const varPrefix = content.var || 'card';

  const orderedItems = useMemo(
    () => (shouldShuffle ? shuffleArray(items.map((item, i) => ({ item, idx: i }))) : items.map((item, i) => ({ item, idx: i }))),
    [items, shouldShuffle]
  );

  const [currentIndex, setCurrentIndex] = useState(0);
  const [responses, setResponses] = useState({});
  const [selectedScale, setSelectedScale] = useState(null);

  const currentItem = orderedItems[currentIndex];
  const itemLabel = typeof currentItem?.item === 'string' ? currentItem.item : currentItem?.item?.text || currentItem?.item?.label || '';

  const scaleLabels = options.length > 0
    ? options
    : Array.from({ length: scalePoints }, (_, i) => String(i + 1));

  const handleScaleSelect = (value) => {
    setSelectedScale(value);
  };

  const handleNext = () => {
    const newResponses = { ...responses, [currentItem.idx]: selectedScale };
    setResponses(newResponses);
    setSelectedScale(null);

    if (currentIndex < orderedItems.length - 1) {
      setCurrentIndex(currentIndex + 1);
    } else {
      const result = {};
      orderedItems.forEach(({ idx }) => {
        const item = items[idx];
        const key = typeof item === 'object' && item.var ? item.var : `${varPrefix}_${idx + 1}`;
        result[key] = newResponses[idx];
      });
      onSubmit(result);
    }
  };

  const progress = items.length > 0 ? ((currentIndex) / items.length) * 100 : 0;

  return (
    <div className="survey-card">
      <div className="question-text">{content.question_text}</div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}

      <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        {currentIndex + 1} of {items.length}
      </div>
      <div className="progress-bar" style={{ marginBottom: '16px' }}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="card-shuffle-item">
        <div className="question-text">{itemLabel}</div>
        <div className="scale-row">
          {scaleLabels.map((label, i) => (
            <button
              key={i}
              className={`scale-btn${selectedScale === i + 1 ? ' selected' : ''}`}
              onClick={() => handleScaleSelect(i + 1)}
            >
              {typeof label === 'string' ? label : label.text || label.label || (i + 1)}
            </button>
          ))}
        </div>
      </div>

      <button className="btn-next" disabled={selectedScale === null} onClick={handleNext}>
        {currentIndex < orderedItems.length - 1 ? 'Next' : 'Continue'}
      </button>
    </div>
  );
}
