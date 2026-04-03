import { useState, useEffect, useCallback } from 'react';
import { useSurvey } from './hooks/useSurvey';
import Screener from './components/Screener';
import TypingIntro from './components/TypingIntro';
import TypingMaxDiff from './components/TypingMaxDiff';
import DemAttitudeVectors from './components/DemAttitudeVectors';
import SurveyPage from './components/SurveyPage';
import PrismLogo from './components/PrismLogo';
import SurveyFooter from './components/SurveyFooter';

function App() {
  const {
    phase, respId, battery, studyCode, segmentId,
    pageId, pageContent, loading, error, progress, pageCount,
    enter, submitScreener, startTyping, submitMaxDiff, submitVectors, submitPage,
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

  const hasPsidInUrl = new URLSearchParams(window.location.search).get('psid');

  const handleReadySetGo = useCallback(() => {
    // Generate a session psid and enter the survey
    const psid = 'web_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    enter(psid, 'web');
  }, [enter]);

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

      {/* ENTRY phase — intro screen */}
      {phase === 'entry' && !loading && (
        <div className="entry-screen">
          <PrismLogo size="lg" />

          <div className="entry-card">
            <p className="entry-intro-text">
              Thanks for taking part. This survey helps us understand how people
              think about health care and public policy today. There are no right
              or wrong answers &mdash; we&rsquo;re interested in your point of view.
              Let&rsquo;s begin.
            </p>
          </div>

          {!hasPsidInUrl && (
            <button
              className="btn-cta-pill"
              onClick={handleReadySetGo}
            >
              READY, SET, GO!
            </button>
          )}

          {hasPsidInUrl && (
            <p style={{
              color: 'var(--text-secondary)',
              fontSize: 15,
              fontFamily: 'var(--font-secondary)',
            }}>
              Connecting...
            </p>
          )}
        </div>
      )}

      {/* SCREENER phase */}
      {phase === 'screener' && !loading && (
        <Screener onSubmit={submitScreener} />
      )}

      {/* TYPING INTRO phase */}
      {phase === 'typing_intro' && !loading && (
        <TypingIntro
          batteryType={battery?.battery}
          nTasks={battery?.n_tasks}
          onStart={startTyping}
        />
      )}

      {/* TYPING phase — MaxDiff cards */}
      {phase === 'typing' && !loading && (
        <TypingMaxDiff battery={battery} onSubmit={submitMaxDiff} />
      )}

      {/* TYPING VECTORS phase — DEM/BOTH attitude vectors */}
      {phase === 'typing_vectors' && !loading && (
        <DemAttitudeVectors onSubmit={submitVectors} />
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
