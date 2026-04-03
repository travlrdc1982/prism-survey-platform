import PrismLogo from './PrismLogo';

export default function TypingIntro({ batteryType, nTasks, onStart }) {
  const cardCount = nTasks || (batteryType === 'GOP' ? 12 : 10);
  const statementsPerCard = batteryType === 'GOP' ? 4 : 5;

  return (
    <div className="survey-card typing-intro">
      <div className="typing-intro-logo">
        <PrismLogo size="lg" />
      </div>

      <div className="typing-intro-card">
        <p>
          In this section we'll ask about a mix of political and social issues.
          Some questions may feel personal&hellip; Always just go with your first,
          honest reaction.
        </p>
        <p>
          You'll see a series of cards, each with <strong>{statementsPerCard} statements</strong>.
          On each card, choose the one that sounds <strong>most</strong> like you
          and the one that sounds <strong>least</strong> like you.
        </p>
        <p>
          Some statements may show up again&mdash;that's intentional.
          There are no right or wrong answers.
          Go with the statement that feels most true&mdash;and most familiar&mdash;to you.
        </p>
      </div>

      <button className="btn-cta-pill btn-enjoy" onClick={onStart}>
        ENJOY!
      </button>
    </div>
  );
}
