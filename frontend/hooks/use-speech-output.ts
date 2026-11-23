"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, ApiError, prepareSpeech } from "@/lib/api";

export type SpeakState = "idle" | "loading" | "playing";

// Desktop Chrome on Linux (and many Windows PCs) ships no Bangla voice; Android Chrome usually has one.
const NO_VOICE = "এই ব্রাউজারে বাংলা ভয়েস নেই (Android ফোনের Chrome-এ থাকে)।";
// Why the online (ElevenLabs) voice was not used — shown with NO_VOICE so the cause is visible.
const WHY_OLD_BACKEND = "সার্ভারের পুরনো সংস্করণ চলছে, ব্যাকএন্ড রিস্টার্ট করুন।";
const WHY_NO_TOKEN = "এই উত্তরের জন্য অনলাইন ভয়েস চালু নেই।";
const WHY_AUDIO_FAILED = "অনলাইন ভয়েস চালানো যায়নি।";

// Only one answer speaks at a time across the page.
let stopActive: (() => void) | null = null;

/** Same idea as the backend's clean_for_speech: no citation markers, links or markdown. */
function speakableText(text: string): string {
  return text
    .replace(/https?:\/\/\S+|www\.\S+/g, "")
    .replace(/\[\s*[CWU]?[0-9০-৯]+\s*\]/g, "")
    .replace(/^\s*[-•*]\s+/gm, "")
    .replace(/[*_`#>]+/g, "")
    .replace(/[ \t]+([।,.?!:;])/g, "$1")
    .trim();
}

function banglaVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  return voices.find((v) => v.lang === "bn-BD") ?? voices.find((v) => v.lang.toLowerCase().startsWith("bn")) ?? null;
}

/**
 * Reads an answer aloud: ElevenLabs (streamed from our backend) when the answer has a speech token,
 * otherwise — or if that fails — the browser's own Bangla voice, which never leaves the device.
 */
export function useSpeechOutput() {
  const [state, setState] = useState<SpeakState>("idle");
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const runRef = useRef(0); // bumps on every start/stop so stale callbacks are ignored

  const stop = useCallback(() => {
    runRef.current += 1;
    audioRef.current?.pause();
    audioRef.current = null;
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    setState("idle");
  }, []);

  useEffect(() => {
    // Chrome loads its voice list lazily; ask once so the fallback can find a Bangla voice later.
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.getVoices();
    return () => {
      if (stopActive === stop) stopActive = null;
      stop();
    };
  }, [stop]);

  const speakWithBrowser = useCallback((text: string, run: number, why?: string) => {
    const voice = banglaVoice();
    if (!voice) {
      setError(why ? `${why} ${NO_VOICE}` : NO_VOICE);
      setState("idle");
      return;
    }
    const utterance = new SpeechSynthesisUtterance(speakableText(text));
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.95;
    utterance.onstart = () => run === runRef.current && setState("playing");
    utterance.onend = () => run === runRef.current && setState("idle");
    utterance.onerror = () => run === runRef.current && setState("idle");
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  }, []);

  const speak = useCallback(
    /** token: string = online voice allowed; null = server said browser voice only; undefined = old backend. */
    async (text: string, token: string | null | undefined) => {
      stopActive?.();
      stopActive = stop;
      const run = ++runRef.current;
      setError(null);
      setState("loading");

      if (token) {
        let fellBack = false;
        const fallBack = (why: string, detail?: unknown) => {
          if (fellBack || run !== runRef.current) return;
          fellBack = true;
          audioRef.current = null;
          console.warn("[tts] online voice failed, using the browser voice:", detail ?? why);
          speakWithBrowser(text, run, why);
        };
        try {
          const { audio_url } = await prepareSpeech(text, token);
          if (run !== runRef.current) return;
          const audio = new Audio(`${API_URL}${audio_url}`);
          audioRef.current = audio;
          audio.onplaying = () => run === runRef.current && setState("playing");
          audio.onended = () => run === runRef.current && setState("idle");
          audio.onerror = () => fallBack(WHY_AUDIO_FAILED, audio.error);
          await audio.play();
        } catch (err) {
          fallBack(err instanceof ApiError ? err.message : WHY_AUDIO_FAILED, err);
        }
        return;
      }
      speakWithBrowser(text, run, token === undefined ? WHY_OLD_BACKEND : WHY_NO_TOKEN);
    },
    [speakWithBrowser, stop],
  );

  return { state, error, speak, stop };
}
