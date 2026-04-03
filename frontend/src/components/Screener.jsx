import { useState, useCallback, useRef, useEffect } from 'react';
import PrismLogo from './PrismLogo';

/* ── Party value encoding ──
   r1 = Strong Republican
   r2 = Not-so-strong Republican
   r3 = Lean Republican
   r4 = Independent / Other (no lean)
   r5 = Lean Democrat
   r6 = Not-so-strong Democrat
   r7 = Strong Democrat
*/

function DigitBoxes({ count, value, onChange, id }) {
  const refs = useRef([]);

  const handleChange = (idx, e) => {
    const char = e.target.value.replace(/\D/g, '').slice(-1);
    const arr = (value || '').split('');
    arr[idx] = char;
    const next = arr.join('').slice(0, count);
    onChange(next);
    if (char && idx < count - 1) {
      refs.current[idx + 1]?.focus();
    }
  };

  const handleKeyDown = (idx, e) => {
    if (e.key === 'Backspace' && !value[idx] && idx > 0) {
      refs.current[idx - 1]?.focus();
    }
  };

  return (
    <div className="digit-boxes" data-testid={id}>
      {Array.from({ length: count }, (_, i) => (
        <input
          key={i}
          ref={el => (refs.current[i] = el)}
          type="text"
          inputMode="numeric"
          maxLength={1}
          className="digit-box"
          value={(value || '')[i] || ''}
          onChange={e => handleChange(i, e)}
          onKeyDown={e => handleKeyDown(i, e)}
          autoFocus={i === 0}
        />
      ))}
    </div>
  );
}

function HorizontalRadio({ options, value, onChange }) {
  return (
    <div className="horizontal-radio-group">
      {options.map((opt) => {
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

function PreferNotToRespond({ checked, onChange }) {
  return (
    <label className="prefer-not-respond">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
      />
      <span>Prefer not to respond</span>
    </label>
  );
}

function QuestionCard({ number, visible, children, title }) {
  if (!visible) return null;
  return (
    <div className="screener-question" data-question={number}>
      <div className="screener-question-label">Q{number}</div>
      <div className="screener-question-title">{title}</div>
      <div className="screener-question-body">{children}</div>
    </div>
  );
}

const TERM_REASONS = {
  qvote: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
  zip: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
  age: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
  gender: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
  vote2024: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
  party3_nolean: 'Thank you for your interest. Unfortunately, you do not qualify for this survey.',
};

export default function Screener({ onSubmit, onTerminate }) {
  const [answers, setAnswers] = useState({});
  const [preferNot, setPreferNot] = useState({});
  const [terminated, setTerminated] = useState(null);
  const bottomRef = useRef(null);

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

  // Scroll to bottom when a new question reveals
  useEffect(() => {
    const timer = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, 100);
    return () => clearTimeout(timer);
  }, [answers]);

  const terminate = (reason) => {
    setTerminated(reason);
    onTerminate?.(reason, answers);
  };

  // Compute visibility: progressive disclosure
  const hasAnswer = (key) => answers[key] !== undefined;

  // Check termination conditions
  const checkTermAfterQvote = () => {
    if (answers.qvote === 'NO' || answers.qvote === 'NOT_SURE') return true;
    return false;
  };

  const checkTermAfterZip = () => {
    if (preferNot.zip) return true;
    return false;
  };

  const checkTermAfterAge = () => {
    if (preferNot.age) return true;
    const ageNum = parseInt(answers.age, 10);
    if (!answers.age || answers.age === '__PNR__') return true;
    if (isNaN(ageNum) || ageNum < 18 || ageNum > 96) return true;
    return false;
  };

  const checkTermAfterGender = () => {
    if (preferNot.gender || !answers.gender || answers.gender === '__PNR__') return true;
    return false;
  };

  const checkTermAfterVote2024 = () => {
    if (preferNot.vote2024 || !answers.vote2024 || answers.vote2024 === '__PNR__') return true;
    return false;
  };

  // Visibility flags
  const showZip = hasAnswer('qvote') && !checkTermAfterQvote();
  const zipComplete = answers.zip && answers.zip.length === 5 && /^\d{5}$/.test(answers.zip);
  const showAge = showZip && (zipComplete || preferNot.zip) && !checkTermAfterZip();
  const ageComplete = answers.age && answers.age.length === 2 && /^\d{2}$/.test(answers.age);
  const ageNum = parseInt(answers.age, 10);
  const ageValid = ageComplete && ageNum >= 18 && ageNum <= 96;
  const showGender = showAge && (ageValid || preferNot.age) && !checkTermAfterAge();
  const showVote2024 = showGender && hasAnswer('gender') && !checkTermAfterGender();
  const showParty1 = showVote2024 && hasAnswer('vote2024') && !checkTermAfterVote2024();
  const showParty2 = showParty1 && hasAnswer('party1') && (answers.party1 === 'GOP' || answers.party1 === 'DEM');
  const showParty3 = showParty1 && hasAnswer('party1') && answers.party1 === 'IND';

  // Compute final party value
  const computePartyValue = () => {
    const p1 = answers.party1;
    if (p1 === 'GOP') {
      return answers.party2 === 'STRONG' ? 'r1' : 'r2';
    }
    if (p1 === 'DEM') {
      return answers.party2 === 'STRONG' ? 'r7' : 'r6';
    }
    if (p1 === 'IND') {
      if (answers.party3 === 'GOP_LEAN') return 'r3';
      if (answers.party3 === 'DEM_LEAN') return 'r5';
      if (answers.party3 === 'NO_LEAN') return 'r4';
    }
    return null;
  };

  const canSubmit = () => {
    // Need party resolution complete
    if (!showParty1 || !hasAnswer('party1')) return false;
    const p1 = answers.party1;
    if (p1 === 'GOP' || p1 === 'DEM') {
      return hasAnswer('party2');
    }
    if (p1 === 'IND') {
      return hasAnswer('party3');
    }
    return false;
  };

  const handleSubmit = () => {
    // Check party3 no-lean termination
    if (answers.party3 === 'NO_LEAN') {
      terminate('party3_nolean');
      return;
    }

    const partyValue = computePartyValue();

    // Map frontend labels to backend numeric codes
    const BALLOT_MAP = { TRUMP: 1, HARRIS: 2, OTHER: 3, DID_NOT_VOTE: 4 };
    const GENDER_MAP = { MALE: 1, FEMALE: 2, OTHER: 3 };
    const PARTY_MAP = { r1: 1, r2: 2, r3: 3, r4: 4, r5: 5, r6: 6, r7: 7 };

    const result = {
      qvote: answers.qvote === 'YES' ? 1 : 2,
      qballot: BALLOT_MAP[answers.vote2024] || 3,
      qparty: PARTY_MAP[partyValue] || 4,
      qgender: GENDER_MAP[answers.gender] || 3,
      qage: parseInt(answers.age, 10) || null,
      qzip: answers.zip || null,
    };
    onSubmit(result);
  };

  // If terminated, show termination screen
  if (terminated) {
    return (
      <div className="survey-card screener-terminated">
        <PrismLogo size="lg" />
        <div className="question-text" style={{ marginTop: 24, textAlign: 'center' }}>
          {TERM_REASONS[terminated] || 'Thank you for your interest.'}
        </div>
      </div>
    );
  }

  // Count answered visible questions for progress
  const totalQuestions = 8;
  let answeredCount = 0;
  if (hasAnswer('qvote')) answeredCount++;
  if (hasAnswer('zip')) answeredCount++;
  if (hasAnswer('age')) answeredCount++;
  if (hasAnswer('gender')) answeredCount++;
  if (hasAnswer('vote2024')) answeredCount++;
  if (hasAnswer('party1')) answeredCount++;
  if (hasAnswer('party2')) answeredCount++;
  if (hasAnswer('party3')) answeredCount++;
  const progress = (answeredCount / totalQuestions) * 100;

  return (
    <div className="screener-page">
      <div className="screener-header">
        <PrismLogo size="md" />
        <div className="screener-header-text">
          <h2 className="screener-title">PRISM Survey</h2>
          <p className="screener-subtitle">Screener Qualification</p>
        </div>
      </div>

      <div className="progress-bar" style={{ marginBottom: 24 }}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Q1: QVOTE */}
      <QuestionCard number={1} visible={true} title="Are you registered to vote?">
        <HorizontalRadio
          value={answers.qvote}
          onChange={val => {
            set('qvote', val);
            if (val === 'NO' || val === 'NOT_SURE') {
              setTimeout(() => terminate('qvote'), 400);
            }
          }}
          options={[
            { value: 'YES', label: 'Yes', icon: '\u2713' },
            { value: 'NO', label: 'No' },
            { value: 'NOT_SURE', label: 'Not Sure' },
          ]}
        />
      </QuestionCard>

      {/* Q2: ZIP */}
      <QuestionCard number={2} visible={showZip} title="Please enter your 5-digit Zip Code">
        <DigitBoxes
          count={5}
          value={answers.zip || ''}
          onChange={val => set('zip', val)}
          id="zip-input"
        />
        <PreferNotToRespond
          checked={!!preferNot.zip}
          onChange={checked => {
            setPnr('zip', checked);
            if (checked) {
              setTimeout(() => terminate('zip'), 400);
            }
          }}
        />
      </QuestionCard>

      {/* Q3: AGE */}
      <QuestionCard number={3} visible={showAge} title="What is your age?">
        <DigitBoxes
          count={2}
          value={answers.age || ''}
          onChange={val => set('age', val)}
          id="age-input"
        />
        <PreferNotToRespond
          checked={!!preferNot.age}
          onChange={checked => {
            setPnr('age', checked);
            if (checked) {
              setTimeout(() => terminate('age'), 400);
            }
          }}
        />
        {answers.age && answers.age !== '__PNR__' && answers.age.length === 2 && (() => {
          const n = parseInt(answers.age, 10);
          if (n < 18) return <div className="screener-validation-msg">You must be at least 18 to participate.</div>;
          if (n > 96) return <div className="screener-validation-msg">Age must be 96 or under.</div>;
          return null;
        })()}
      </QuestionCard>

      {/* Q4: GENDER */}
      <QuestionCard number={4} visible={showGender} title="What is your gender?">
        <HorizontalRadio
          value={answers.gender}
          onChange={val => set('gender', val)}
          options={[
            { value: 'MALE', label: 'Male' },
            { value: 'FEMALE', label: 'Female' },
            { value: 'OTHER', label: 'Other' },
          ]}
        />
        <PreferNotToRespond
          checked={!!preferNot.gender}
          onChange={checked => {
            setPnr('gender', checked);
            if (checked) {
              setTimeout(() => terminate('gender'), 400);
            }
          }}
        />
      </QuestionCard>

      {/* Q5: VOTE2024 */}
      <QuestionCard number={5} visible={showVote2024} title="Who did you vote for in the latest (2024) Presidential election?">
        <div className="ballot-options">
          {[
            { value: 'TRUMP', label: 'Donald J Trump (R)', party: 'R' },
            { value: 'HARRIS', label: 'Kamala Harris (D)', party: 'D' },
            { value: 'OTHER', label: 'Another Candidate' },
            { value: 'DID_NOT_VOTE', label: "I didn't have the chance to vote in this election" },
          ].map(opt => (
            <div
              key={opt.value}
              className={`ballot-option${answers.vote2024 === opt.value ? ' selected' : ''}${opt.party ? ` party-${opt.party}` : ''}`}
              onClick={() => set('vote2024', opt.value)}
            >
              <div className="option-radio" />
              <span>{opt.label}</span>
            </div>
          ))}
        </div>
        <PreferNotToRespond
          checked={!!preferNot.vote2024}
          onChange={checked => {
            setPnr('vote2024', checked);
            if (checked) {
              setTimeout(() => terminate('vote2024'), 400);
            }
          }}
        />
      </QuestionCard>

      {/* Q6: PARTY1 */}
      <QuestionCard number={6} visible={showParty1} title="In politics today, do you consider yourself a...?">
        <HorizontalRadio
          value={answers.party1}
          onChange={val => {
            set('party1', val);
            // Clear dependent answers
            setAnswers(prev => {
              const copy = { ...prev, party1: val };
              delete copy.party2;
              delete copy.party3;
              return copy;
            });
          }}
          options={[
            { value: 'GOP', label: 'Republican', icon: '\uD83D\uDC18' },
            { value: 'DEM', label: 'Democrat', icon: '\uD83E\uDD93' },
            { value: 'IND', label: 'Independent / Other' },
          ]}
        />
        <PreferNotToRespond
          checked={!!preferNot.party1}
          onChange={checked => setPnr('party1', checked)}
        />
      </QuestionCard>

      {/* Q7: PARTY2 (conditional: GOP or DEM) */}
      <QuestionCard
        number={7}
        visible={showParty2}
        title={`Would you say you are a strong or not-so-strong ${answers.party1 === 'GOP' ? 'Republican' : 'Democrat'}?`}
      >
        <HorizontalRadio
          value={answers.party2}
          onChange={val => set('party2', val)}
          options={[
            { value: 'STRONG', label: `Strong ${answers.party1 === 'GOP' ? 'Republican' : 'Democrat'}` },
            { value: 'NOT_STRONG', label: `Not-so-strong ${answers.party1 === 'GOP' ? 'Republican' : 'Democrat'}` },
          ]}
        />
      </QuestionCard>

      {/* Q8: PARTY3 (conditional: Independent) */}
      <QuestionCard
        number={8}
        visible={showParty3}
        title="Do you lean toward the..."
      >
        <HorizontalRadio
          value={answers.party3}
          onChange={val => set('party3', val)}
          options={[
            { value: 'GOP_LEAN', label: 'Republicans' },
            { value: 'DEM_LEAN', label: 'Democrats' },
            { value: 'NO_LEAN', label: 'I do not lean toward either' },
          ]}
        />
      </QuestionCard>

      {/* CONTINUE button */}
      {canSubmit() && (
        <button className="btn-next btn-continue-cta" onClick={handleSubmit}>
          CONTINUE &gt;
        </button>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
