import { useState, useCallback } from 'react';
import { apiGet, apiPost } from './useApi';

/**
 * Survey state machine.
 *
 * Phases: entry → screener → typing → study → complete/terminate/overquota
 *
 * The study phase loops: fetch page → render → collect response → submit → next page.
 */
export function useSurvey() {
  const [phase, setPhase] = useState('entry');
  const [respId, setRespId] = useState(null);
  const [battery, setBattery] = useState(null);
  const [studyCode, setStudyCode] = useState(null);
  const [segmentId, setSegmentId] = useState(null);
  const [pageId, setPageId] = useState(null);
  const [pageContent, setPageContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(0);
  const [pageCount, setPageCount] = useState(0);

  const enter = useCallback(async (psid, source) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet('/survey/entry', { psid, source });
      setRespId(data.resp_id);
      setPhase('screener');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const submitScreener = useCallback(async (screenerData) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost('/survey/screener', { resp_id: respId, ...screenerData });
      if (data.status === 'terminate') {
        setPhase('terminate');
        return;
      }
      setBattery(data.battery);
      setPhase('typing');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId]);

  const submitTyping = useCallback(async (rawResponses) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost('/survey/typing', {
        resp_id: respId,
        battery,
        raw_responses: rawResponses,
      });
      if (data.status === 'overquota') {
        setPhase('overquota');
        return;
      }
      setStudyCode(data.study_code);
      setSegmentId(data.segment_id);
      // Fetch the first study page
      await fetchPage('pre_test.SECTORFAV');
      setPhase('study');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId, battery]);

  const fetchPage = useCallback(async (pid) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet(`/survey/study/${pid}`, { resp_id: respId });
      setPageId(pid);
      setPageContent(data.content);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId]);

  const submitPage = useCallback(async (responses) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost(`/survey/study/${pageId}`, {
        resp_id: respId,
        page_id: pageId,
        responses,
      });
      setPageCount(c => c + 1);
      setProgress(p => Math.min(p + 3.5, 98));

      if (data.next === 'complete' || data.status === 'complete') {
        // Fire completion
        await apiPost('/survey/complete', { resp_id: respId });
        setPhase('complete');
      } else {
        await fetchPage(data.next);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId, pageId, fetchPage]);

  return {
    phase, respId, battery, studyCode, segmentId,
    pageId, pageContent, loading, error, progress, pageCount,
    enter, submitScreener, submitTyping, submitPage,
    setError,
  };
}
