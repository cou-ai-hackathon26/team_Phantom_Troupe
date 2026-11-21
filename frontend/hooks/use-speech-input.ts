"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, transcribeAudio, type VoiceLang } from "@/lib/api";

// Minimal Web Speech API types (not in TypeScript's DOM lib everywhere).
interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionErrorEventLike {
  error: string;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

export type MicMode = "speech" | "recorder" | "none";
export type MicState = "idle" | "listening" | "recording" | "transcribing";

const MAX_RECORD_MS = 30_000;
// Keep listening through the natural pauses of a spoken question; stop after this much silence.
const SILENCE_STOP_MS = 2_500;
const LANG_KEY = "adhikarai.voiceLang";
// Browser recognizers write everything in the chosen language's script, so English speech under bn-BD
// comes out as Bangla-script phonetics: the user picks the language they will speak.
const BROWSER_LANG: Record<VoiceLang, string> = { bn: "bn-BD", en: "en-US" };

const SPEECH_ERRORS: Record<string, string> = {
  "not-allowed": "মাইক্রোফোন ব্যবহারের অনুমতি দেওয়া হয়নি। ব্রাউজারের ঠিকানা-বারের পাশে অনুমতি দিন, অথবা প্রশ্নটি লিখুন।",
  "service-not-allowed": "এই ব্রাউজারে ভয়েস সেবা চালু নেই। প্রশ্নটি লিখুন।",
  "no-speech": "কোনো কথা শোনা যায়নি। মাইকে চাপ দিয়ে আবার বলুন।",
  "audio-capture": "মাইক্রোফোন পাওয়া যায়নি। মাইক্রোফোন যুক্ত আছে কি না দেখুন।",
  network: "ভয়েস চিনতে ইন্টারনেট লাগে। সংযোগ দেখে আবার চেষ্টা করুন, অথবা প্রশ্নটি লিখুন।",
};
const UNSUPPORTED = "এই ব্রাউজারে ভয়েস ইনপুট নেই। Chrome ব্যবহার করুন, অথবা প্রশ্নটি লিখুন।";

function getSpeechCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// Brave (and some other Chromium builds) expose the Web Speech API but have no access to Google's
// speech service: every attempt ends in a "network" error. Use the Whisper recorder there from the start.
function browserSpeechUnusable(): boolean {
  if (typeof navigator === "undefined") return false;
  return "brave" in navigator;
}

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find((t) =>
    MediaRecorder.isTypeSupported(t),
  );
}

/**
 * Voice input: browser speech recognition first (bn-BD or en-US, as chosen); MediaRecorder + backend
 * Whisper (same language) as fallback.
 * The final text is handed to `onFinal` — the caller puts it in the input box. Nothing auto-sends.
 */
export function useSpeechInput(onFinal: (text: string) => void) {
  const [mode, setMode] = useState<MicMode>("none");
  const [state, setState] = useState<MicState>("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [lang, setLangState] = useState<VoiceLang>("bn");
  const langRef = useRef<VoiceLang>("bn");

  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timers = useRef<{
    stop?: ReturnType<typeof setTimeout>;
    max?: ReturnType<typeof setTimeout>;
    tick?: ReturnType<typeof setInterval>;
  }>({});
  const finalText = useRef("");
  const networkFailed = useRef(false);
  const startRecorderRef = useRef<() => Promise<void>>(async () => undefined);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(LANG_KEY);
      if (saved === "bn" || saved === "en") {
        langRef.current = saved;
        setLangState(saved);
      }
    } catch {
      /* storage blocked: default to Bangla */
    }
  }, []);

  const setLang = useCallback((next: VoiceLang) => {
    langRef.current = next;
    setLangState(next);
    try {
      window.localStorage.setItem(LANG_KEY, next);
    } catch {
      /* storage blocked: choice lasts for this visit */
    }
  }, []);

  useEffect(() => {
    if (getSpeechCtor() && !browserSpeechUnusable()) setMode("speech");
    else if (typeof MediaRecorder !== "undefined" && "mediaDevices" in navigator) setMode("recorder");
    else setMode("none");
  }, []);

  const clearTimers = () => {
    if (timers.current.stop) clearTimeout(timers.current.stop);
    if (timers.current.max) clearTimeout(timers.current.max);
    if (timers.current.tick) clearInterval(timers.current.tick);
    timers.current = {};
  };

  const startSpeech = useCallback(() => {
    const Ctor = getSpeechCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = BROWSER_LANG[langRef.current];
    rec.interimResults = true;
    // continuous: with `false`, Chrome ends at the first short pause and cuts the question off
    rec.continuous = true;
    rec.maxAlternatives = 1;
    finalText.current = "";
    const armSilenceStop = () => {
      if (timers.current.stop) clearTimeout(timers.current.stop);
      timers.current.stop = setTimeout(() => rec.stop(), SILENCE_STOP_MS);
    };
    rec.onresult = (e) => {
      let interimText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const piece = r[0].transcript.trim();
        if (r.isFinal) finalText.current = [finalText.current, piece].filter(Boolean).join(" ");
        else interimText += ` ${piece}`;
      }
      setInterim((finalText.current + interimText).trim());
      armSilenceStop(); // speech is still coming: push the auto-stop back
    };
    rec.onerror = (e) => {
      if (e.error === "aborted") return;
      if (e.error === "network" && typeof MediaRecorder !== "undefined") {
        // the browser's speech service is unreachable (often a browser without Google's service):
        // switch to our Whisper recorder and start recording right away — no second tap needed
        networkFailed.current = true;
        return;
      }
      setError(SPEECH_ERRORS[e.error] ?? "ভয়েস চিনতে সমস্যা হয়েছে। আবার বলুন অথবা প্রশ্নটি লিখুন।");
    };
    rec.onend = () => {
      clearTimers();
      setState("idle");
      setInterim("");
      if (networkFailed.current) {
        networkFailed.current = false;
        setMode("recorder");
        void startRecorderRef.current();
        return;
      }
      const text = finalText.current.trim();
      if (text) onFinalRef.current(text);
    };
    recognition.current = rec;
    setError(null);
    setState("listening");
    rec.start();
    timers.current.max = setTimeout(() => rec.stop(), MAX_RECORD_MS); // hard cap, like the recorder path
  }, []);

  const startRecorder = useCallback(async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(SPEECH_ERRORS["not-allowed"]);
      return;
    }
    const mimeType = pickMimeType();
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    rec.onstop = async () => {
      clearTimers();
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      if (blob.size === 0) {
        setState("idle");
        return;
      }
      setState("transcribing");
      try {
        const { transcript } = await transcribeAudio(blob, langRef.current);
        onFinalRef.current(transcript);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "কথা বোঝা যায়নি। আবার বলুন অথবা প্রশ্নটি লিখুন।");
      } finally {
        setState("idle");
      }
    };
    recorder.current = rec;
    rec.start();
    setState("recording");
    setElapsed(0);
    const started = Date.now();
    timers.current.tick = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250);
    timers.current.stop = setTimeout(() => rec.state !== "inactive" && rec.stop(), MAX_RECORD_MS);
  }, []);

  startRecorderRef.current = startRecorder;

  const start = useCallback(() => {
    if (mode === "speech") startSpeech();
    else if (mode === "recorder") void startRecorder();
    else setError(UNSUPPORTED);
  }, [mode, startSpeech, startRecorder]);

  const stop = useCallback(() => {
    if (state === "listening") recognition.current?.stop();
    if (state === "recording" && recorder.current?.state !== "inactive") recorder.current?.stop();
  }, [state]);

  useEffect(
    () => () => {
      clearTimers();
      recognition.current?.abort();
      if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    },
    [],
  );

  return {
    mode,
    state,
    interim,
    error,
    elapsed,
    maxSeconds: MAX_RECORD_MS / 1000,
    lang,
    setLang,
    start,
    stop,
    clearError: () => setError(null),
  };
}
