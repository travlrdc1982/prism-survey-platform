import PrismLogo from './PrismLogo';

export default function TypingIntro({ batteryType, onStart }) {
  const isGOP = batteryType === 'GOP';
  const isDEM = batteryType === 'DEM';

  return (
    <div className="survey-card typing-intro">
      <div className="typing-intro-logo">
        <PrismLogo size="lg" />
      </div>

      <h2 className="typing-intro-title">PRISM Typing Tool</h2>

      <div className="typing-intro-body">
        <p>
          You will now be shown a series of cards, each containing <strong>4 statements</strong>.
        </p>
        <p>
          For each card, please select the statement that is <strong>MOST like you</strong> and
          the statement that is <strong>LEAST like you</strong>.
        </p>
        <p>
          There are no right or wrong answers — we are simply interested in your honest opinions.
        </p>
        {(isGOP || isDEM) && (
          <p className="typing-intro-battery-note">
            This section is tailored to your political perspective. Please answer as honestly as you can.
          </p>
        )}
      </div>

      <button className="btn-next btn-enjoy" onClick={onStart}>
        ENJOY!
      </button>
    </div>
  );
}
