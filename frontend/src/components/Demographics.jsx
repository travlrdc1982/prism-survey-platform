import { useState, useCallback } from 'react';

/**
 * Demographics — page.group.x
 *
 * Full demographics section with:
 * - Intro screen
 * - ETHNIO: Hispanic background (YES/NO horizontal)
 * - RACE: radio list (White, Black, Asian, Other + specify)
 * - VET: Military service (Active Duty / Veteran / No) horizontal with icons
 * - UNION: Labor union (YES/NO) horizontal with icons
 * - EDUCATION: highest degree (9 options in 3x3 grid)
 * - REL: religion dropdown with PNR
 * - REL2: conditional born-again/evangelical if Protestant
 * - HHI: household income dropdown
 * All have "Prefer not to respond" checkbox
 */

function PreferNotToRespond({ checked, onChange }) {
  return (
    <label className="prefer-not-respond">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      <span>Prefer not to respond</span>
    </label>
  );
}

function HorizontalRadio({ options, value, onChange }) {
  return (
    <div className="horizontal-radio-group">
      {options.map(opt => {
        const isSelected = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            className={`horizontal-radio-btn${isSelected ? ' selected' : ''}`}
            onClick={() => onChange(opt.value)}
          >
            <span className="horizontal-radio-circle">
              {isSelected && <span className="horizontal-radio-dot" />}
            </span>
            {opt.icon && <span className="horizontal-radio-icon">{opt.icon}</span>}
            <span className="horizontal-radio-label">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function DemographicQuestion({ title, children, questionNum, totalQuestions }) {
  return (
    <div className="survey-card demo-question-card">
      {questionNum && totalQuestions && (
        <div className="question-counter">{questionNum} of {totalQuestions} Questions</div>
      )}
      <div className="question-text">{title}</div>
      <div className="demo-question-body">{children}</div>
    </div>
  );
}

const EDUCATION_OPTIONS = [
  'Less than high school',
  'Some high school',
  'High school diploma / GED',
  'Some college',
  'Associate degree',
  "Bachelor's degree",
  "Master's degree",
  'Professional degree (JD, MD)',
  'Doctorate (PhD, EdD)',
];

const RELIGION_OPTIONS = [
  'Protestant',
  'Roman Catholic',
  'Mormon / LDS',
  'Orthodox Christian',
  'Jewish',
  'Muslim',
  'Buddhist',
  'Hindu',
  'Atheist',
  'Agnostic',
  'Nothing in particular',
  'Other',
];

const HHI_OPTIONS = [
  'Under $15,000',
  '$15,000 - $24,999',
  '$25,000 - $34,999',
  '$35,000 - $49,999',
  '$50,000 - $74,999',
  '$75,000 - $99,999',
  '$100,000 - $149,999',
  '$150,000 - $199,999',
  '$200,000 or more',
];

export default function Demographics({ onSubmit }) {
  const [step, setStep] = useState('intro');
  const [answers, setAnswers] = useState({});
  const [preferNot, setPreferNot] = useState({});
  const [raceOtherText, setRaceOtherText] = useState('');

  const set = useCallback((key, val) => {
    setAnswers(prev => ({ ...prev, [key]: val }));
    setPreferNot(prev => ({ ...prev, [key]: false }));
  }, []);

  const setPnr = useCallback((key, checked) => {
    setPreferNot(prev => ({ ...prev, [key]: checked }));
    if (checked) {
      setAnswers(prev => ({ ...prev, [key]: '__PNR__' }));
    } else {
      setAnswers(prev => {
        const copy = { ...prev };
        if (copy[key] === '__PNR__') delete copy[key];
        return copy;
      });
    }
  }, []);

  const hasAnswer = (key) => answers[key] !== undefined;
  const canAdvance = (key) => hasAnswer(key) || preferNot[key];

  const advance = (nextStep) => setStep(nextStep);

  switch (step) {
    case 'intro':
      return (
        <div className="survey-card demo-intro">
          <div className="section-header">DEMOGRAPHICS</div>
          <div className="question-text">We promise this is the last stretch.</div>
          <div className="comments-text">
            Please answer a few more questions about yourself. Your responses help us ensure
            our research is representative and accurate.
          </div>
          <button className="btn-next" onClick={() => advance('ethnio')}>
            CONTINUE &gt;
          </button>
        </div>
      );

    case 'ethnio':
      return (
        <DemographicQuestion title="Are you of Hispanic, Latino, or Spanish background?" questionNum={1} totalQuestions={8}>
          <HorizontalRadio
            value={answers.ethnio}
            onChange={val => set('ethnio', val)}
            options={[
              { value: 'YES', label: 'Yes', icon: '\u2713' },
              { value: 'NO', label: 'No' },
            ]}
          />
          <PreferNotToRespond checked={!!preferNot.ethnio} onChange={c => setPnr('ethnio', c)} />
          <button className="btn-next" disabled={!canAdvance('ethnio')} onClick={() => advance('race')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'race':
      return (
        <DemographicQuestion title="Which best describes your race?" questionNum={2} totalQuestions={8}>
          <div className="option-list">
            {[
              { value: 'WHITE', label: 'White' },
              { value: 'BLACK', label: 'Black or African American' },
              { value: 'ASIAN', label: 'Asian' },
              { value: 'OTHER', label: 'Other (please specify)' },
            ].map(opt => (
              <div
                key={opt.value}
                className={`option-item${answers.race === opt.value ? ' selected' : ''}`}
                onClick={() => set('race', opt.value)}
              >
                <div className="option-radio" />
                <span>{opt.label}</span>
              </div>
            ))}
          </div>
          {answers.race === 'OTHER' && (
            <input
              type="text"
              className="demo-text-input"
              placeholder="Please specify..."
              value={raceOtherText}
              onChange={e => setRaceOtherText(e.target.value)}
            />
          )}
          <PreferNotToRespond checked={!!preferNot.race} onChange={c => setPnr('race', c)} />
          <button className="btn-next" disabled={!canAdvance('race')} onClick={() => advance('vet')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'vet':
      return (
        <DemographicQuestion title="Have you ever served in the United States military?" questionNum={3} totalQuestions={8}>
          <HorizontalRadio
            value={answers.vet}
            onChange={val => set('vet', val)}
            options={[
              { value: 'ACTIVE', label: 'Yes, Active Duty', icon: '\u2B50' },
              { value: 'VETERAN', label: 'Yes, Veteran', icon: '\uD83C\uDFC5' },
              { value: 'NO', label: 'No' },
            ]}
          />
          <PreferNotToRespond checked={!!preferNot.vet} onChange={c => setPnr('vet', c)} />
          <button className="btn-next" disabled={!canAdvance('vet')} onClick={() => advance('union')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'union':
      return (
        <DemographicQuestion title="Are you, or is anyone in your household, a member of a labor union?" questionNum={4} totalQuestions={8}>
          <HorizontalRadio
            value={answers.union}
            onChange={val => set('union', val)}
            options={[
              { value: 'YES', label: 'Yes', icon: '\uD83E\uDD1D' },
              { value: 'NO', label: 'No' },
            ]}
          />
          <PreferNotToRespond checked={!!preferNot.union} onChange={c => setPnr('union', c)} />
          <button className="btn-next" disabled={!canAdvance('union')} onClick={() => advance('education')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'education':
      return (
        <DemographicQuestion title="What is the highest level of education you have completed?" questionNum={5} totalQuestions={8}>
          <div className="education-grid">
            {EDUCATION_OPTIONS.map((opt, i) => (
              <button
                key={i}
                type="button"
                className={`education-btn${answers.education === i + 1 ? ' selected' : ''}`}
                onClick={() => set('education', i + 1)}
              >
                {opt}
              </button>
            ))}
          </div>
          <PreferNotToRespond checked={!!preferNot.education} onChange={c => setPnr('education', c)} />
          <button className="btn-next" disabled={!canAdvance('education')} onClick={() => advance('rel')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'rel':
      return (
        <DemographicQuestion title="What is your present religion, if any?" questionNum={6} totalQuestions={8}>
          <select
            className="dropdown-select"
            value={answers.rel || ''}
            onChange={e => set('rel', e.target.value)}
          >
            <option value="">-- Select --</option>
            {RELIGION_OPTIONS.map((opt, i) => (
              <option key={i} value={opt}>{opt}</option>
            ))}
          </select>
          <PreferNotToRespond checked={!!preferNot.rel} onChange={c => setPnr('rel', c)} />
          <button
            className="btn-next"
            disabled={!canAdvance('rel')}
            onClick={() => {
              if (answers.rel === 'Protestant') {
                advance('rel2');
              } else {
                advance('hhi');
              }
            }}
          >
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'rel2':
      return (
        <DemographicQuestion title="Would you describe yourself as a born-again or evangelical Christian?" questionNum={7} totalQuestions={8}>
          <HorizontalRadio
            value={answers.rel2}
            onChange={val => set('rel2', val)}
            options={[
              { value: 'YES', label: 'Yes' },
              { value: 'NO', label: 'No' },
            ]}
          />
          <PreferNotToRespond checked={!!preferNot.rel2} onChange={c => setPnr('rel2', c)} />
          <button className="btn-next" disabled={!canAdvance('rel2')} onClick={() => advance('hhi')}>
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    case 'hhi':
      return (
        <DemographicQuestion title="What is your total annual household income before taxes?" questionNum={8} totalQuestions={8}>
          <select
            className="dropdown-select"
            value={answers.hhi || ''}
            onChange={e => set('hhi', e.target.value)}
          >
            <option value="">-- Select --</option>
            {HHI_OPTIONS.map((opt, i) => (
              <option key={i} value={opt}>{opt}</option>
            ))}
          </select>
          <PreferNotToRespond checked={!!preferNot.hhi} onChange={c => setPnr('hhi', c)} />
          <button
            className="btn-next"
            disabled={!canAdvance('hhi')}
            onClick={() => {
              const result = { ...answers };
              if (raceOtherText && answers.race === 'OTHER') {
                result.race_other = raceOtherText;
              }
              Object.keys(result).forEach(k => {
                if (result[k] === '__PNR__') result[k] = 'PREFER_NOT_TO_RESPOND';
              });
              onSubmit(result);
            }}
          >
            CONTINUE &gt;
          </button>
        </DemographicQuestion>
      );

    default:
      return null;
  }
}
