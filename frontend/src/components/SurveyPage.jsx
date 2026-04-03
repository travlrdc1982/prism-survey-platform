import RadioVertical from './RadioVertical';
import MatrixGrid from './MatrixGrid';
import CardShuffle from './CardShuffle';
import ButtonHorizontal from './ButtonHorizontal';
import RankSort from './RankSort';
import MaxDiffMessage from './MaxDiffMessage';
import OpenText from './OpenText';
import DropdownGrid from './DropdownGrid';
import InvestmentStimulus from './InvestmentStimulus';
import Checklist from './Checklist';
import Demographics from './Demographics';
import OptIn from './OptIn';
import Screener from './Screener';
import TypingIntro from './TypingIntro';
import TypingMaxDiff from './TypingMaxDiff';
import DemAttitudeVectors from './DemAttitudeVectors';
import Influence360 from './Influence360';

const COMPONENT_MAP = {
  'STYLE.MATRIX': MatrixGrid,
  'STYLE.RADIO.VERTICAL': RadioVertical,
  'STYLE.BUTTON.HORIZONTAL': ButtonHorizontal,
  'STYLE.BUTTON.CARD.SHUFFLE': CardShuffle,
  'STYLE.RANKSORT': RankSort,
  'STYLE.CHECKLIST': Checklist,
  'STYLE.OPEN.TEXT': OpenText,
  'STYLE.DROPDOWN': DropdownGrid,
  'MAXDIFF.MESSAGE': MaxDiffMessage,
  'MAXDIFF.TYPING': MaxDiffMessage,
  'CUSTOM.BALLOT': RadioVertical,
  'CUSTOM.PARTYID': RadioVertical,
  'CUSTOM.STIMULUS': InvestmentStimulus,
  'CUSTOM.INVESTMENT': InvestmentStimulus,
  'CUSTOM.DEMOGRAPHICS': Demographics,
  'CUSTOM.OPTIN': OptIn,
  'TYPINGTOOL.SCREENER': Screener,
  'TYPINGTOOL.INTRO': TypingIntro,
  'TYPINGTOOL.MAXDIFF.GOP': TypingMaxDiff,
  'TYPINGTOOL.MAXDIFF.DEM': TypingMaxDiff,
  'TYPINGTOOL.VECTORS.DEM': DemAttitudeVectors,
  'INFLUENCE360': Influence360,
};

export default function SurveyPage({ content, onSubmit }) {
  if (!content) {
    return (
      <div className="survey-card">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  const componentType = content.component || '';
  const Component = COMPONENT_MAP[componentType];

  if (Component) {
    return <Component content={content} onSubmit={onSubmit} />;
  }

  // Fallback: render raw JSON for unknown component types
  return (
    <div className="survey-card">
      <div className="question-text">
        {content.question_text || `Unknown component: ${componentType}`}
      </div>
      {content.comments_text && <div className="comments-text">{content.comments_text}</div>}
      <details style={{ marginTop: 16, fontSize: 13, color: 'var(--text-secondary)' }}>
        <summary>Debug: Raw content</summary>
        <pre style={{
          marginTop: 8,
          padding: 12,
          background: 'var(--bg-page)',
          borderRadius: 8,
          overflow: 'auto',
          fontSize: 12,
          lineHeight: 1.4,
        }}>
          {JSON.stringify(content, null, 2)}
        </pre>
      </details>
      <button className="btn-next" onClick={() => onSubmit({})}>
        Skip / Next
      </button>
    </div>
  );
}
