import { useState } from 'react';

/**
 * DEM Attitude Vectors — page.group.4 (TYPINGTOOL.VECTORS.DEM)
 *
 * 7-point scale matrix (Strongly Disagree to Strongly Agree)
 * 2 statements: VECTOR_JUSTICE and VECTOR_INDUSTRY
 * "Prefer not to respond" checkbox
 * Only shown to DEM battery respondents.
 */

const SCALE_LABELS = [
  'Strongly Disagree',
  'Disagree',
  'Somewhat Disagree',
  'Neither Agree nor Disagree',
  'Somewhat Agree',
  'Agree',
  'Strongly Agree',
];

const SCALE_SHORT = ['SD', 'D', 'SwD', 'N', 'SwA', 'A', 'SA'];

const DEFAULT_STATEMENTS = [
  {
    key: 'VECTOR_JUSTICE',
    text: 'Social justice and equity should be the primary focus of government policy.',
  },
  {
    key: 'VECTOR_INDUSTRY',
    text: 'American industry and manufacturing need to be protected and revitalized.',
  },
];

export default function DemAttitudeVectors({ content, onSubmit }) {
  const statements = content?.statements || DEFAULT_STATEMENTS;
  const [responses, setResponses] = useState({});
  const [preferNot, setPreferNot] = useState(false);

  const handleSelect = (statementKey, value) => {
    setResponses(prev => ({ ...prev, [statementKey]: value }));
  };

  const allAnswered = preferNot || statements.every(s => responses[s.key] !== undefined);

  const handleSubmit = () => {
    if (preferNot) {
      const result = {};
      statements.forEach(s => {
        result[s.key] = '__PNR__';
      });
      onSubmit(result);
    } else {
      onSubmit(responses);
    }
  };

  return (
    <div className="survey-card vectors-card">
      <div className="section-header">ATTITUDE VECTORS</div>
      <div className="question-text">
        {content?.question_text || 'Please indicate how much you agree or disagree with each statement.'}
      </div>
      {content?.comments_text && <div className="comments-text">{content.comments_text}</div>}

      {/* Scale header (desktop) */}
      <div className="vectors-scale-header">
        <div className="vectors-statement-col" />
        {SCALE_LABELS.map((label, i) => (
          <div key={i} className="vectors-scale-col">
            <span className="vectors-scale-label-full">{label}</span>
            <span className="vectors-scale-label-short">{SCALE_SHORT[i]}</span>
          </div>
        ))}
      </div>

      {/* Statement rows */}
      {statements.map((stmt) => (
        <div key={stmt.key} className="vectors-row">
          <div className="vectors-statement-col">
            <p className="vectors-statement-text">{stmt.text}</p>
          </div>
          <div className="vectors-scale-cells">
            {SCALE_LABELS.map((label, i) => {
              const value = i + 1;
              const isSelected = responses[stmt.key] === value;
              return (
                <div
                  key={i}
                  className={`vectors-scale-cell${isSelected ? ' selected' : ''}`}
                  onClick={() => !preferNot && handleSelect(stmt.key, value)}
                  title={label}
                >
                  <div className={`vectors-radio${isSelected ? ' selected' : ''}`}>
                    {isSelected && <span className="vectors-radio-dot" />}
                  </div>
                  <span className="vectors-scale-mobile-label">{SCALE_SHORT[i]}</span>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Prefer not to respond */}
      <label className="prefer-not-respond">
        <input
          type="checkbox"
          checked={preferNot}
          onChange={e => setPreferNot(e.target.checked)}
        />
        <span>Prefer not to respond</span>
      </label>

      <button className="btn-next" disabled={!allAnswered} onClick={handleSubmit}>
        CONTINUE &gt;
      </button>
    </div>
  );
}
