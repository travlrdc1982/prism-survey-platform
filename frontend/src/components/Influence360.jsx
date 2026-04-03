import { useState } from 'react';

/**
 * Influence 360 — page.group.6
 *
 * Multi-screen flow:
 *  1. Intro screen
 *  2. STYLE.CHECKLIST: "How have you made your voice heard?" with "None of these" exclusive
 *  3. Upgrade modules: conditional checklists based on gateway responses
 *  4. Social media followers: STYLE.BUTTONSELECT
 *  5. Social influence card shuffle: 3 cards with frequency scale
 */

const VOICE_HEARD_OPTIONS = [
  { key: 'contacted_official', label: 'Contacted an elected official (email, phone, letter)' },
  { key: 'attended_rally', label: 'Attended a political rally, march, or protest' },
  { key: 'donated_campaign', label: 'Donated to a political campaign or cause' },
  { key: 'volunteered', label: 'Volunteered for a campaign or political organization' },
  { key: 'posted_social', label: 'Posted about politics on social media' },
  { key: 'signed_petition', label: 'Signed a petition (online or in person)' },
  { key: 'wrote_media', label: 'Wrote a letter to the editor or op-ed' },
  { key: 'none', label: 'None of these', exclusive: true },
];

const FOLLOWER_RANGES = [
  { value: '0', label: '0 None' },
  { value: '<500', label: '<500' },
  { value: '500-2000', label: '500-2,000' },
  { value: '2000-10000', label: '2,000-10,000' },
  { value: '10000-50000', label: '10,000-50,000' },
  { value: '50000+', label: '50,000+' },
];

const SOCIAL_CARDS = [
  { key: 'created_post', label: 'Created an original post about a political or social issue' },
  { key: 'shared_reposted', label: 'Shared or reposted content about a political or social issue' },
  { key: 'commented_replied', label: 'Commented on or replied to a post about a political or social issue' },
];

const FREQUENCY_OPTIONS = [
  { value: 'never', label: 'Never' },
  { value: 'not_30', label: 'Not in past 30 days' },
  { value: 'once', label: 'One time' },
  { value: '2-4', label: '2-4 times' },
  { value: '5+', label: '5+ times' },
];

function IntroScreen({ onContinue }) {
  return (
    <div className="survey-card influence-intro">
      <div className="section-header">SECTION 1: INFLUENCE ENGAGEMENT</div>
      <div className="question-text">Influence 360</div>
      <div className="comments-text">
        In this section we would like to learn about the different ways you engage with
        politics and public life. There are no right or wrong answers — we are interested
        in your real experiences.
      </div>
      <button className="btn-next" onClick={onContinue}>
        CONTINUE &gt;
      </button>
    </div>
  );
}

function VoiceHeardChecklist({ onSubmit }) {
  const [selected, setSelected] = useState(new Set());

  const handleToggle = (key, isExclusive) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (isExclusive) {
        // If toggling "None of these", clear others
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.clear();
          next.add(key);
        }
      } else {
        // Remove "none" if selecting a real option
        next.delete('none');
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
      }
      return next;
    });
  };

  const canSubmit = selected.size > 0;

  return (
    <div className="survey-card">
      <div className="question-counter">1 of 5 Questions</div>
      <div className="question-text">How have you made your voice heard?</div>
      <div className="comments-text">Select all that apply.</div>

      <div className="influence-checklist">
        {VOICE_HEARD_OPTIONS.map(opt => {
          const isSelected = selected.has(opt.key);
          return (
            <div
              key={opt.key}
              className={`checklist-item${isSelected ? ' selected' : ''}${opt.exclusive ? ' exclusive-option' : ''}`}
              onClick={() => handleToggle(opt.key, opt.exclusive)}
            >
              <div className={`checklist-checkbox${isSelected ? ' checked' : ''}`}>
                {isSelected && '\u2713'}
              </div>
              <span>{opt.label}</span>
            </div>
          );
        })}
      </div>

      <button className="btn-next" disabled={!canSubmit} onClick={() => onSubmit(Object.fromEntries(
        VOICE_HEARD_OPTIONS.map(o => [o.key, selected.has(o.key) ? 1 : 0])
      ))}>
        CONTINUE &gt;
      </button>
    </div>
  );
}

function UpgradeModules({ gatewayResponses, onSubmit }) {
  const [responses, setResponses] = useState({});

  // Show upgrade checklists based on what they selected in gateway
  const activeKeys = Object.entries(gatewayResponses)
    .filter(([k, v]) => v === 1 && k !== 'none')
    .map(([k]) => k);

  if (activeKeys.length === 0) {
    // Skip upgrade if nothing selected (or only "none")
    return (
      <div className="survey-card">
        <div className="question-text">Thank you. Let's continue.</div>
        <button className="btn-next" onClick={() => onSubmit({})}>
          CONTINUE &gt;
        </button>
      </div>
    );
  }

  const UPGRADE_QUESTIONS = {
    contacted_official: {
      question: 'Which of the following did you contact an elected official about?',
      options: ['Healthcare', 'Immigration', 'Economy / Jobs', 'Environment / Climate', 'Education', 'Gun policy', 'Other'],
    },
    attended_rally: {
      question: 'What type of event did you attend?',
      options: ['Campaign rally', 'Town hall meeting', 'Protest / March', 'Fundraiser', 'Other'],
    },
    donated_campaign: {
      question: 'To which type of organization did you donate?',
      options: ['Presidential campaign', 'Congressional campaign', 'State/local campaign', 'Political action committee (PAC)', 'Issue advocacy group', 'Other'],
    },
    posted_social: {
      question: 'On which platforms have you posted about politics?',
      options: ['Facebook', 'X (Twitter)', 'Instagram', 'TikTok', 'Reddit', 'YouTube', 'Other'],
    },
  };

  // Only show upgrades we have definitions for
  const upgradeKeys = activeKeys.filter(k => UPGRADE_QUESTIONS[k]);

  if (upgradeKeys.length === 0) {
    return (
      <div className="survey-card">
        <div className="question-text">Thank you. Let's continue.</div>
        <button className="btn-next" onClick={() => onSubmit({})}>
          CONTINUE &gt;
        </button>
      </div>
    );
  }

  const handleToggle = (upgradeKey, optIdx) => {
    setResponses(prev => {
      const key = `${upgradeKey}_${optIdx}`;
      return { ...prev, [key]: prev[key] ? 0 : 1 };
    });
  };

  const handleSubmit = () => {
    onSubmit(responses);
  };

  return (
    <div className="survey-card">
      <div className="question-counter">2 of 5 Questions</div>
      <div className="question-text">Tell us more about your engagement.</div>

      {upgradeKeys.map(uKey => {
        const def = UPGRADE_QUESTIONS[uKey];
        return (
          <div key={uKey} className="upgrade-module">
            <div className="upgrade-question">{def.question}</div>
            <div className="influence-checklist">
              {def.options.map((opt, oi) => {
                const rKey = `${uKey}_${oi}`;
                const isSelected = !!responses[rKey];
                return (
                  <div
                    key={oi}
                    className={`checklist-item${isSelected ? ' selected' : ''}`}
                    onClick={() => handleToggle(uKey, oi)}
                  >
                    <div className={`checklist-checkbox${isSelected ? ' checked' : ''}`}>
                      {isSelected && '\u2713'}
                    </div>
                    <span>{opt}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      <button className="btn-next" onClick={handleSubmit}>
        CONTINUE &gt;
      </button>
    </div>
  );
}

function SocialFollowers({ onSubmit }) {
  const [selected, setSelected] = useState(null);

  return (
    <div className="survey-card">
      <div className="question-counter">3 of 5 Questions</div>
      <div className="question-text">
        Approximately how many total followers or connections do you have across all your social media accounts?
      </div>

      <div className="button-select-row">
        {FOLLOWER_RANGES.map(opt => (
          <button
            key={opt.value}
            type="button"
            className={`button-select-btn${selected === opt.value ? ' selected' : ''}`}
            onClick={() => setSelected(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <button
        className="btn-next"
        disabled={selected === null}
        onClick={() => onSubmit({ social_followers: selected })}
      >
        CONTINUE &gt;
      </button>
    </div>
  );
}

function SocialCardShuffle({ onSubmit }) {
  const [currentCard, setCurrentCard] = useState(0);
  const [responses, setResponses] = useState({});
  const [selectedFreq, setSelectedFreq] = useState(null);

  const card = SOCIAL_CARDS[currentCard];

  const handleNext = () => {
    const newResponses = { ...responses, [card.key]: selectedFreq };
    setResponses(newResponses);
    setSelectedFreq(null);

    if (currentCard < SOCIAL_CARDS.length - 1) {
      setCurrentCard(currentCard + 1);
    } else {
      onSubmit(newResponses);
    }
  };

  return (
    <div className="survey-card">
      <div className="question-counter">
        {currentCard + 4} of 5 Questions
      </div>
      <div className="question-text">
        In the past 30 days, how often have you done the following on social media?
      </div>

      <div className="social-card-shuffle">
        <div className="social-card-counter">
          {currentCard + 1} of {SOCIAL_CARDS.length} Cards
        </div>

        <div className="social-card-item">
          <p className="social-card-label">{card.label}</p>

          <div className="frequency-options">
            {FREQUENCY_OPTIONS.map(opt => (
              <div
                key={opt.value}
                className={`frequency-option${selectedFreq === opt.value ? ' selected' : ''}`}
                onClick={() => setSelectedFreq(opt.value)}
              >
                <div className="option-radio" />
                <span>{opt.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <button className="btn-next" disabled={selectedFreq === null} onClick={handleNext}>
        {currentCard < SOCIAL_CARDS.length - 1 ? 'CONTINUE >' : 'CONTINUE >'}
      </button>
    </div>
  );
}

export default function Influence360({ onSubmit }) {
  const [step, setStep] = useState('intro');
  const [allResponses, setAllResponses] = useState({});

  const advance = (stepData, nextStep) => {
    setAllResponses(prev => ({ ...prev, ...stepData }));
    setStep(nextStep);
  };

  switch (step) {
    case 'intro':
      return <IntroScreen onContinue={() => setStep('voice')} />;

    case 'voice':
      return (
        <VoiceHeardChecklist
          onSubmit={data => advance(data, 'upgrade')}
        />
      );

    case 'upgrade':
      return (
        <UpgradeModules
          gatewayResponses={allResponses}
          onSubmit={data => advance(data, 'followers')}
        />
      );

    case 'followers':
      return (
        <SocialFollowers
          onSubmit={data => advance(data, 'card_shuffle')}
        />
      );

    case 'card_shuffle':
      return (
        <SocialCardShuffle
          onSubmit={data => {
            const finalData = { ...allResponses, ...data };
            onSubmit(finalData);
          }}
        />
      );

    default:
      return null;
  }
}
