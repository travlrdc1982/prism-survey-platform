import { useState, useEffect } from 'react';
import { useSurvey } from './hooks/useSurvey';
import Screener from './components/Screener';
import TypingMaxDiff from './components/TypingMaxDiff';
import SurveyPage from './components/SurveyPage';
import PrismLogo from './components/PrismLogo';
import SurveyFooter from './components/SurveyFooter';

function App() {
  const {
    phase, respId, battery, studyCode, segmentId,
    pageId, pageContent, loading, error, progress, pageCount,
    enter, submitScreener, submitTyping, submitPage,
    setError,
  } = useSurvey();

  const [testPsid, setTestPsid] = useState('');

  // Auto-enter if psid is in URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const psid = params.get('psid');
    const source = params.get('source') || 'web';
    if (psid) {
      enter(psid, source);
    }
  }, [enter]);

  const handleTestEntry = () => {
    if (testPsid.trim()) {
      enter(testPsid.trim(), 'test');
    }
  };

  return (
    <div className="survey-container">
      {/* Progress bar for study phase */}
      {phase === 'study' && (
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="error-banner">
          {error}
          <span
            style={{ float: 'right', cursor: 'pointer', fontWeight: 600 }}
            onClick={() => setError(null)}
          >
            x
          </span>
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div className="loading">Loading...</div>
      )}

      {/* ENTRY phase */}
      {phase === 'entry' && !loading && (
        <div style={{ textAlign: 'center', paddingTop: 60 }}>
          <PrismLogo size="lg" />
          <h1 style={{
            fontFamily: 'var(--font-primary)',
            fontSize: 28,
            fontWeight: 600,
            marginTop: 24,
            marginBottom: 8,
          }}>
            PRISM Survey
          </h1>
          <p style={{
            color: 'var(--text-secondary)',
            fontSize: 15,
            marginBottom: 32,
          }}>
            {new URLSearchParams(window.location.search).get('psid')
              ? 'Connecting...'
              : 'Enter your participant ID to begin.'}
          </p>

          {!new URLSearchParams(window.location.search).get('psid') && (
            <div className="survey-card" style={{ textAlign: 'left' }}>
              <div className="question-text" style={{ fontSize: 17 }}>Test Entry</div>
              <div className="comments-text">Enter a PSID to start the survey.</div>
              <input
                type="text"
                value={testPsid}
                onChange={(e) => setTestPsid(e.target.value)}
                placeholder="PSID"
                onKeyDown={(e) => { if (e.key === 'Enter') handleTestEntry(); }}
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  border: '1.5px solid var(--border-light)',
                  borderRadius: 8,
                  fontFamily: 'var(--font-secondary)',
                  fontSize: 15,
                  marginBottom: 8,
                }}
              />
              <button className="btn-next" disabled={!testPsid.trim()} onClick={handleTestEntry}>
                Begin Survey
              </button>
            </div>
          )}
        </div>
      )}

      {/* SCREENER phase */}
      {phase === 'screener' && !loading && (
        <Screener onSubmit={submitScreener} />
      )}

      {/* TYPING phase */}
      {phase === 'typing' && !loading && (
        <TypingMaxDiff battery={battery} onSubmit={submitTyping} />
      )}

      {/* STUDY phase */}
      {phase === 'study' && !loading && (
        <SurveyPage
          key={pageId}
          content={pageContent}
          onSubmit={submitPage}
        />
      )}

      {/* COMPLETE */}
      {phase === 'complete' && (
        <div style={{ textAlign: 'center', paddingTop: 60 }}>
          <PrismLogo size="lg" />
          <h1 style={{
            fontFamily: 'var(--font-primary)',
            fontSize: 26,
            fontWeight: 600,
            marginTop: 24,
            marginBottom: 12,
          }}>
            Thank You!
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 15, lineHeight: 1.6 }}>
            Your responses have been recorded. You may now close this window.
          </p>
        </div>
      )}

      {/* TERMINATE */}
      {phase === 'terminate' && (
        <div style={{ textAlign: 'center', paddingTop: 60 }}>
          <PrismLogo size="lg" />
          <h1 style={{
            fontFamily: 'var(--font-primary)',
            fontSize: 26,
            fontWeight: 600,
            marginTop: 24,
            marginBottom: 12,
          }}>
            Thank You
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 15, lineHeight: 1.6 }}>
            Unfortunately, you do not qualify for this survey at this time.
            Thank you for your interest.
          </p>
        </div>
      )}

      {/* OVERQUOTA */}
      {phase === 'overquota' && (
        <div style={{ textAlign: 'center', paddingTop: 60 }}>
          <PrismLogo size="lg" />
          <h1 style={{
            fontFamily: 'var(--font-primary)',
            fontSize: 26,
            fontWeight: 600,
            marginTop: 24,
            marginBottom: 12,
          }}>
            Survey Full
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 15, lineHeight: 1.6 }}>
            We have reached our target number of responses for your group.
            Thank you for your time.
          </p>
        </div>
      )}

      <SurveyFooter />
    </div>
  );
}

export default App;
