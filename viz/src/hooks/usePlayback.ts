import { useState, useRef, useCallback, useEffect } from 'react';
import type { TraceEvent } from '../types/trace';

export interface PlaybackState {
  currentTime: number;
  playing: boolean;
  speed: number;
  eventIndex: number;
  makespan: number;
}

const SPEEDS = [0.25, 0.5, 1, 2, 5, 10];

export function usePlayback(trace: TraceEvent[] | null, makespan: number) {
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState(1);
  const [eventIndex, setEventIndex] = useState(0);
  const [playbackSource, setPlaybackSource] = useState({ trace, makespan });

  if (playbackSource.trace !== trace || playbackSource.makespan !== makespan) {
    setPlaybackSource({ trace, makespan });
    setCurrentTime(0);
    setEventIndex(0);
    setPlaying(false);
  }

  // Refs for the rAF loop — avoids stale closures
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const currentTimeRef = useRef(0);
  const makespanRef = useRef(makespan);
  const traceRef = useRef(trace);
  const animRef = useRef<number>(0);
  const lastFrameRef = useRef(0);

  // Keep refs in sync
  useEffect(() => { speedRef.current = speed; }, [speed]);
  useEffect(() => { makespanRef.current = makespan; }, [makespan]);
  useEffect(() => { traceRef.current = trace; }, [trace]);

  // Stop the previous animation loop when the playback source changes.
  useEffect(() => {
    playingRef.current = false;
    currentTimeRef.current = 0;
    cancelAnimationFrame(animRef.current);
  }, [trace, makespan]);

  const findEventIndex = useCallback(
    (time: number): number => {
      const t = traceRef.current;
      if (!t) return 0;
      let idx = 0;
      for (let i = 0; i < t.length; i++) {
        if (t[i].sim_time <= time) idx = i;
        else break;
      }
      return idx;
    },
    [] // uses ref, no deps needed
  );

  // The animation loop — completely independent of React render cycle
  const startLoop = useCallback(() => {
    lastFrameRef.current = 0;

    const loop = (timestamp: number) => {
      if (!playingRef.current) return; // stopped — exit loop

      const dt = lastFrameRef.current
        ? (timestamp - lastFrameRef.current) / 1000
        : 0;
      lastFrameRef.current = timestamp;

      const ms = makespanRef.current;
      const newTime = Math.min(
        currentTimeRef.current + dt * speedRef.current,
        ms
      );
      currentTimeRef.current = newTime;

      const newIndex = findEventIndex(newTime);
      setCurrentTime(newTime);
      setEventIndex(newIndex);

      if (newTime >= ms) {
        // Reached end
        playingRef.current = false;
        setPlaying(false);
        return;
      }

      animRef.current = requestAnimationFrame(loop);
    };

    animRef.current = requestAnimationFrame(loop);
  }, [findEventIndex]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelAnimationFrame(animRef.current);
      playingRef.current = false;
    };
  }, []);

  const play = useCallback(() => {
    if (playingRef.current) return;
    // If at end, restart
    if (currentTimeRef.current >= makespanRef.current) {
      currentTimeRef.current = 0;
      setCurrentTime(0);
      setEventIndex(0);
    }
    playingRef.current = true;
    setPlaying(true);
    startLoop();
  }, [startLoop]);

  const pause = useCallback(() => {
    playingRef.current = false;
    setPlaying(false);
    cancelAnimationFrame(animRef.current);
  }, []);

  const togglePlay = useCallback(() => {
    if (playingRef.current) {
      pause();
    } else {
      play();
    }
  }, [play, pause]);

  const seek = useCallback(
    (time: number) => {
      const clamped = Math.max(0, Math.min(time, makespanRef.current));
      currentTimeRef.current = clamped;
      setCurrentTime(clamped);
      setEventIndex(findEventIndex(clamped));
    },
    [findEventIndex]
  );

  const stepForward = useCallback(() => {
    const t = traceRef.current;
    if (!t) return;
    pause();
    const next = Math.min(eventIndex + 1, t.length - 1);
    currentTimeRef.current = t[next].sim_time;
    setCurrentTime(t[next].sim_time);
    setEventIndex(next);
  }, [eventIndex, pause]);

  const stepBackward = useCallback(() => {
    const t = traceRef.current;
    if (!t) return;
    pause();
    const prev = Math.max(eventIndex - 1, 0);
    currentTimeRef.current = t[prev].sim_time;
    setCurrentTime(t[prev].sim_time);
    setEventIndex(prev);
  }, [eventIndex, pause]);

  const speedUp = useCallback(() => {
    setSpeedState((s) => {
      const idx = SPEEDS.indexOf(s);
      const next = idx < SPEEDS.length - 1 ? SPEEDS[idx + 1] : s;
      speedRef.current = next;
      return next;
    });
  }, []);

  const speedDown = useCallback(() => {
    setSpeedState((s) => {
      const idx = SPEEDS.indexOf(s);
      const prev = idx > 0 ? SPEEDS[idx - 1] : s;
      speedRef.current = prev;
      return prev;
    });
  }, []);

  const setSpeed = useCallback((sp: number) => {
    speedRef.current = sp;
    setSpeedState(sp);
  }, []);

  return {
    currentTime,
    playing,
    speed,
    eventIndex,
    makespan,
    play,
    pause,
    togglePlay,
    seek,
    stepForward,
    stepBackward,
    speedUp,
    speedDown,
    setSpeed,
  };
}
