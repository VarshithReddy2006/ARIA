import React, { useEffect, useState } from 'react';
import { useInView, useReducedMotion } from './hooks';
import { MEMORY_ANSWER, MEMORY_CONTEXT, MEMORY_QUESTION, MEMORY_SYMBOLS } from './data';

/* ─────────────────────────────────────────────────────────────────────────────
 * GroundedRetrieval — chapter 06.
 *
 * Deliberately not a chatbot. The sequence is the argument, and it is drawn
 * explicitly as a reasoning path rather than left implicit in a status line:
 *
 *   QUESTION → RETRIEVE → GRAPH CONTEXT → EVIDENCE → ANSWER
 *
 * The grounding — the symbols retrieved and the topology walked — carries more
 * visual weight than the prose, because retrieval is the claim being made. The
 * path runs once and then rests: there is no thinking spinner, and no state here
 * implies a model is working while the visitor reads.
 * ────────────────────────────────────────────────────────────────────────── */

type Phase = 'idle' | 'typing' | 'retrieving' | 'context' | 'answering' | 'done';

const PHASE_ORDER: Phase[] = ['idle', 'typing', 'retrieving', 'context', 'answering', 'done'];

const reached = (current: Phase, target: Phase) =>
  PHASE_ORDER.indexOf(current) >= PHASE_ORDER.indexOf(target);

const STATUS: Record<Phase, string> = {
  idle: 'STANDBY',
  typing: 'QUESTION',
  retrieving: 'RETRIEVE',
  context: 'GRAPH CONTEXT',
  answering: 'EVIDENCE',
  done: `GROUNDED · ${MEMORY_SYMBOLS.length} SOURCES CITED`,
};

/**
 * The reasoning path, drawn as a compact rail above the exchange. Each step is a
 * stage of the retrieval ARIA actually performs; the phase machine below lights
 * them in order, once.
 */
const REASONING_PATH: { label: string; at: Phase }[] = [
  { label: 'QUESTION', at: 'typing' },
  { label: 'RETRIEVE', at: 'retrieving' },
  { label: 'GRAPH CONTEXT', at: 'context' },
  { label: 'EVIDENCE', at: 'answering' },
  { label: 'ANSWER', at: 'done' },
];

export const GroundedRetrieval: React.FC = () => {
  const [ref, inView] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const reduced = useReducedMotion();

  const [phase, setPhase] = useState<Phase>('idle');
  const [typed, setTyped] = useState('');
  const [symbolCount, setSymbolCount] = useState(0);
  const [answerCount, setAnswerCount] = useState(0);

  // Reduced motion: present the finished exchange immediately, no choreography.
  useEffect(() => {
    if (!inView || phase !== 'idle') return;
    if (reduced) {
      setTyped(MEMORY_QUESTION);
      setSymbolCount(MEMORY_SYMBOLS.length);
      setAnswerCount(MEMORY_ANSWER.length);
      setPhase('done');
      return;
    }
    setPhase('typing');
  }, [inView, phase, reduced]);

  useEffect(() => {
    if (phase !== 'typing') return;
    let i = 0;
    let timeoutId: number | null = null;
    const intervalId = window.setInterval(() => {
      i += 1;
      setTyped(MEMORY_QUESTION.slice(0, i));
      if (i >= MEMORY_QUESTION.length) {
        window.clearInterval(intervalId);
        timeoutId = window.setTimeout(() => setPhase('retrieving'), 420);
      }
    }, 26);
    return () => {
      window.clearInterval(intervalId);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== 'retrieving') return;
    let i = 0;
    let timeoutId: number | null = null;
    const intervalId = window.setInterval(() => {
      i += 1;
      setSymbolCount(i);
      if (i >= MEMORY_SYMBOLS.length) {
        window.clearInterval(intervalId);
        timeoutId = window.setTimeout(() => setPhase('context'), 460);
      }
    }, 340);
    return () => {
      window.clearInterval(intervalId);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [phase]);

  useEffect(() => {
    if (phase !== 'context') return;
    const id = window.setTimeout(() => setPhase('answering'), 900);
    return () => window.clearTimeout(id);
  }, [phase]);

  useEffect(() => {
    if (phase !== 'answering') return;
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setAnswerCount(i);
      if (i >= MEMORY_ANSWER.length) {
        window.clearInterval(id);
        setPhase('done');
      }
    }, 760);
    return () => window.clearInterval(id);
  }, [phase]);

  return (
    <div ref={ref}>
      {/* ── The reasoning path ───────────────────────────────────────────────
          Drawn once, left to right, with glowing laser connectors
      --------------------------------------------------------------------- */}
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-8 sm:mb-10 p-3.5 rounded-xl bg-[#080B12]/80 border border-white/[0.06] backdrop-blur-xl" aria-hidden="true">
        {REASONING_PATH.map((node, i) => {
          const lit = reached(phase, node.at);
          return (
            <li key={node.label} className="flex items-center gap-3">
              {i > 0 && (
                <span
                  className="h-px w-5 sm:w-8 origin-left rounded-full"
                  style={{
                    background: lit ? 'linear-gradient(90deg, #6366F1, #38BDF8)' : 'rgba(255,255,255,0.08)',
                    boxShadow: lit ? '0 0 8px rgba(99,102,241,0.5)' : 'none',
                    transform: `scaleX(${lit ? 1 : 0.35})`,
                    transition:
                      'background 500ms ease, transform 620ms cubic-bezier(0.16,1,0.3,1)',
                  }}
                />
              )}
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                    lit ? 'bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)]' : 'bg-white/20'
                  }`}
                />
                <span
                  className="mono-label text-[10px] whitespace-nowrap tracking-wider font-semibold"
                  style={{
                    color: lit ? '#F8FAFC' : '#64748B',
                    transition: 'color 500ms ease',
                  }}
                >
                  {node.label}
                </span>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">
        {/* ── Conversation Console ────────────────────────────────────────── */}
        <div className="lg:col-span-7 rounded-2xl bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 border border-white/[0.08] shadow-[0_20px_50px_rgba(0,0,0,0.7)] backdrop-blur-2xl overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-5 sm:px-7 py-3.5 border-b border-white/[0.08] bg-[#050608]/40">
            <div className="flex items-center gap-2.5 min-w-0">
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  phase === 'done'
                    ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]'
                    : 'bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.8)] animate-pulse'
                }`}
                aria-hidden="true"
              />
              <span className="mono-label text-indigo-300 font-semibold truncate text-[11px]">{STATUS[phase]}</span>
            </div>
            <span className="mono-label text-[9px] text-[#64748B] shrink-0 tracking-widest">GROUNDED REASONING ENGINE</span>
          </div>

          <div className="px-5 sm:px-7 py-6 sm:py-8 space-y-7" aria-live="polite">
            {/* Question */}
            <div className="p-4 rounded-xl bg-[#050608]/60 border border-white/[0.05]">
              <span className="mono-label text-[10px] text-indigo-400 block mb-2 font-semibold">QUERY</span>
              <div className="flex gap-3">
                <span
                  className="font-mono text-sm text-indigo-400 shrink-0 select-none font-bold"
                  aria-hidden="true"
                >
                  &gt;
                </span>
                <p className="font-mono text-[13px] sm:text-[14px] text-[#F8FAFC] leading-relaxed font-medium">
                  {typed}
                  {phase === 'typing' && (
                    <span className="caret-blink text-indigo-400 font-bold" aria-hidden="true">
                      ▌
                    </span>
                  )}
                </p>
              </div>
            </div>

            {/* Retrieved symbols — the grounding */}
            {reached(phase, 'retrieving') && (
              <div className="border-t border-white/[0.06] pt-6">
                <div className="flex items-baseline justify-between mb-3.5">
                  <span className="mono-label text-indigo-400 font-semibold text-[10px] tracking-wider">EVIDENCE · RETRIEVED SYMBOLS</span>
                  <span className="font-mono text-[11px] text-indigo-300 font-semibold">
                    {symbolCount} / {MEMORY_SYMBOLS.length}
                  </span>
                </div>

                <ul className="space-y-2">
                  {MEMORY_SYMBOLS.slice(0, symbolCount).map((s, i) => (
                    <li key={s.symbol} className="fade-up flex items-center justify-between gap-4 p-2.5 rounded-lg bg-[#050608]/50 border border-white/[0.04] hover:border-indigo-500/30 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className="font-mono text-[10px] text-indigo-400 font-bold shrink-0"
                        >
                          [{String(i + 1).padStart(2, '0')}]
                        </span>
                        <div className="min-w-0">
                          <p className="font-mono text-[12px] text-[#F8FAFC] font-semibold truncate">{s.symbol}</p>
                          <p className="font-mono text-[10px] text-[#64748B] mt-0.5 truncate">
                            {s.path}:{s.lines.replace(/^L/, '').replace('–L', '–')}
                          </p>
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[9px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 shrink-0">
                        RESOLVED
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Response */}
            {reached(phase, 'answering') && (
              <div className="border-t border-white/[0.06] pt-6 relative">
                <span
                  className="absolute -top-6 left-0 h-6 w-px bg-gradient-to-b from-indigo-500 to-indigo-500/20"
                  aria-hidden="true"
                />
                <span className="mono-label text-emerald-400 block mb-3 font-semibold text-[10px] tracking-wider">GROUNDED RESPONSE</span>
                <div className="space-y-3.5 p-4 rounded-xl bg-[#050608]/70 border border-emerald-500/20 shadow-[0_0_20px_rgba(52,211,153,0.05)]">
                  {MEMORY_ANSWER.slice(0, answerCount).map((paragraph, i) => (
                    <p
                      key={i}
                      className={`text-[13px] sm:text-[14px] leading-relaxed fade-up ${
                        i === 0 ? 'text-[#F8FAFC] font-medium' : 'text-[#CBD5E1]'
                      }`}
                    >
                      {paragraph}
                      {phase === 'answering' && i === answerCount - 1 && (
                        <span className="caret-blink text-emerald-400 font-bold ml-1" aria-hidden="true">
                          ▌
                        </span>
                      )}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Graph context ───────────────────────────────────────────────── */}
        <div className="lg:col-span-5 lg:pt-2">
          <div className="p-6 rounded-2xl bg-gradient-to-b from-[#0D1220]/80 to-[#070A12]/90 border border-white/[0.08] shadow-[0_16px_36px_rgba(0,0,0,0.6)] backdrop-blur-2xl">
            <div className="flex items-center gap-2 mb-6">
              <span className="w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.6)] animate-pulse" />
              <span className="mono-label text-sky-400 font-bold text-[10px] tracking-[0.2em] uppercase">GRAPH TOPOLOGY CONTEXT</span>
            </div>

            <dl className="grid grid-cols-2 gap-4">
              {MEMORY_CONTEXT.map((row, i) => (
                <div
                  key={row.label}
                  className="p-3.5 rounded-xl bg-[#050608]/60 border border-white/[0.04]"
                  style={{
                    opacity: reached(phase, 'context') ? 1 : 0.78,
                    transform: reached(phase, 'context') || reduced ? 'none' : 'translateY(4px)',
                    transition: reduced
                      ? undefined
                      : `opacity 700ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms, transform 700ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms`,
                  }}
                >
                  <dt className="mono-label text-[10px] text-[#64748B] mb-2">{row.label}</dt>
                  <dd className="font-mono text-xl sm:text-2xl text-[#F8FAFC] font-bold tabular-nums leading-none">
                    {row.value}
                  </dd>
                </div>
              ))}
            </dl>

            <p className="mt-6 pt-5 border-t border-white/[0.07] text-[13px] text-[#94A3B8] leading-relaxed">
              ARIA does not retrieve text that resembles the question. It walks the symbol graph,
              collects the modules that actually participate, and answers from those.
            </p>
          </div>
        </div>
      </div>

      {/* The point of the section */}
      <p className="display-3 text-text mt-14 sm:mt-16">
        ARIA answers from repository structure,
        <br className="hidden sm:block" />
        <span className="display-dim"> not just text similarity.</span>
      </p>
    </div>
  );
};

export default GroundedRetrieval;
