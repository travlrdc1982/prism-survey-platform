import { useState, useCallback } from 'react';
import { apiGet, apiPost } from './useApi';

/**
 * Survey state machine.
 *
 * Phases: entry → screener → typing_intro → typing → [typing_vectors] → study → complete/terminate/overquota
 *
 * DEM/BOTH batteries require an extra typing_vectors phase to collect
 * attitude vectors before submitting to /survey/typing.
 */
export function useSurvey() {
  const [phase, setPhase] = useState('entry');
  const [respId, setRespId] = useState(null);
  const [battery, setBattery] = useState(null);
  const [typingResponses, setTypingResponses] = useState(null); // MaxDiff B-W scores held until vectors collected
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
      // Fetch typing battery BIBD tasks before showing typing intro
      const batteryData = await apiGet('/survey/typing/battery', { battery: data.battery });
      setBattery(batteryData);
      setPhase('typing_intro');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId]);

  const startTyping = useCallback(() => {
    setPhase('typing');
  }, []);

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

  // Helper: POST combined responses to /survey/typing and advance to study
  const postTypingAndAdvance = useCallback(async (allResponses) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost('/survey/typing', {
        resp_id: respId,
        battery: battery?.battery || battery,
        raw_responses: allResponses,
      });
      if (data.status === 'overquota') {
        setPhase('overquota');
        return;
      }
      setStudyCode(data.study_code);
      setSegmentId(data.segment_id);
      await fetchPage('pre_test.SECTORFAV');
      setPhase('study');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [respId, battery, fetchPage]);

  // After MaxDiff cards: either show vectors (DEM/BOTH) or submit immediately (GOP)
  const submitMaxDiff = useCallback(async (bwScores) => {
    const bat = battery?.battery || '';
    const needsVectors = bat === 'DEM' || bat === 'BOTH';
    if (needsVectors) {
      setTypingResponses(bwScores);
      setPhase('typing_vectors');
    } else {
      await postTypingAndAdvance(bwScores);
    }
  }, [battery, postTypingAndAdvance]);

  // After attitude vectors: merge with MaxDiff and submit
  const submitVectors = useCallback(async (vectorResponses) => {
    const merged = { ...typingResponses, ...vectorResponses };
    await postTypingAndAdvance(merged);
  }, [typingResponses, postTypingAndAdvance]);

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
    enter, submitScreener, startTyping, submitMaxDiff, submitVectors, submitPage,
    setError,
  };
}
