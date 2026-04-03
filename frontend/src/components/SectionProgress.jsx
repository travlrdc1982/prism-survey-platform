/**
 * Progress bar with green fill and section labels.
 * Shows which section the respondent is currently in.
 */
const SECTIONS = [
  { key: 'screener', label: 'Screener' },
  { key: 'typing', label: 'Typing Tool' },
  { key: 'vectors', label: 'Attitudes' },
  { key: 'influence', label: 'Influence 360' },
  { key: 'demographics', label: 'Demographics' },
];

export default function SectionProgress({ currentSection, progressPercent = 0 }) {
  const currentIdx = SECTIONS.findIndex(s => s.key === currentSection);

  return (
    <div className="section-progress">
      <div className="section-progress-bar">
        <div
          className="section-progress-fill"
          style={{ width: `${Math.min(progressPercent, 100)}%` }}
        />
      </div>
      <div className="section-progress-labels">
        {SECTIONS.map((section, i) => (
          <span
            key={section.key}
            className={`section-label${i === currentIdx ? ' active' : ''}${i < currentIdx ? ' completed' : ''}`}
          >
            {section.label}
          </span>
        ))}
      </div>
    </div>
  );
}
