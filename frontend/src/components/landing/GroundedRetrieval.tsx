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
          Drawn once, left to right, so the grounding is visible as a route
          rather than being asserted by a status label.
      --------------------------------------------------------------------- */}
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-7 sm:mb-9" aria-hidden="true">
        {REASONING_PATH.map((node, i) => {
          const lit = reached(phase, node.at);
          return (
            <li key={node.label} className="flex items-center gap-3">
              {i > 0 && (
                <span
                  className="h-px w-5 sm:w-9 origin-left"
                  style={{
                    backgroundColor: lit ? 'var(--primary)' : 'rgba(255,255,255,0.09)',
                    transform: `scaleX(${lit ? 1 : 0.35})`,
                    transition:
                      'background-color 500ms ease, transform 620ms cubic-bezier(0.16,1,0.3,1)',
                  }}
                />
              )}
              <span
                className="mono-label whitespace-nowrap"
                style={{
                  color: lit ? 'var(--text)' : 'var(--text-subtle)',
                  opacity: lit ? 1 : 0.45,
                  transition: 'color 500ms ease, opacity 500ms ease',
                }}
              >
                {node.label}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">
        {/* ── Conversation ────────────────────────────────────────────────── */}
        <div className="lg:col-span-7 spec-panel">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-5 sm:px-7 py-4 hair-b">
            {/*
              The dot marks which step of the illustrative sequence is showing; it
              does not breathe. A pulsing indicator beside "RETRIEVE" reads as a
              model working, and nothing is working while the visitor reads.
            */}
            <div className="flex items-center gap-2.5 min-w-0">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${phase === 'done' ? 'bg-success' : 'bg-primary'
                  }`}
                aria-hidden="true"
              />
              <span className="mono-label truncate">{STATUS[phase]}</span>
            </div>
            {/* Never hidden at any width: the exchange is illustrative. */}
            <span className="mono-label shrink-0">ILLUSTRATIVE EXCHANGE</span>
          </div>

          <div className="px-5 sm:px-7 py-7 sm:py-9 space-y-8" aria-live="polite">
            {/* Question */}
            <div>
              <span className="mono-label block mb-3">USER</span>
              <div className="flex gap-3">
                <span
                  className="font-mono text-sm text-primary shrink-0 select-none"
                  aria-hidden="true"
                >
                  &gt;
                </span>
                <p className="font-mono text-[13px] sm:text-[15px] text-text leading-relaxed">
                  {typed}
                  {phase === 'typing' && (
                    <span className="caret-blink text-primary" aria-hidden="true">
                      ▌
                    </span>
                  )}
                </p>
              </div>
            </div>

            {/* Retrieved symbols — the grounding, weighted above the prose */}
            {reached(phase, 'retrieving') && (
              <div className="hair-t pt-7">
                <div className="flex items-baseline justify-between mb-4">
                  <span className="mono-label mono-label-accent">EVIDENCE · RETRIEVED SYMBOLS</span>
                  <span className="mono-detail" style={{ fontSize: 10 }}>
                    {symbolCount} / {MEMORY_SYMBOLS.length}
                  </span>
                </div>
                {/*
                  Each source is a compact reference — symbol, file, line span.
                  Citable, not decorative: this is what "grounded" has to mean.
                */}
                <ul>
                  {MEMORY_SYMBOLS.slice(0, symbolCount).map((s, i) => (
                    <li key={s.symbol} className="fade-up flex items-baseline gap-4 py-3 hair-t">
                      <span
                        className="mono-label mono-label-accent shrink-0 tabular-nums"
                        style={{ letterSpacing: '0.14em' }}
                      >
                        [{String(i + 1).padStart(2, '0')}]
                      </span>
                      <div className="min-w-0">
                        <p className="font-mono text-[13px] text-text break-all">{s.symbol}</p>
                        <p className="mono-detail mt-1 break-all" style={{ fontSize: 10 }}>
                          {s.path}:{s.lines.replace(/^L/, '').replace('–L', '–')}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Response */}
            {reached(phase, 'answering') && (
              <div className="hair-t pt-7 relative">
                {/*
                  The grounding line. Evidence physically connects to the answer,
                  so "grounded" is something the reader sees rather than a word in
                  a label. Draws once, when the answer begins.
                */}
                <span
                  className={`absolute -top-7 left-0 h-7 w-px grounding-line ${reached(phase, 'answering') ? 'is-grounded' : ''
                    }`}
                  style={{ background: 'linear-gradient(180deg, var(--primary), rgba(94,106,210,0.15))' }}
                  aria-hidden="true"
                />
                <span className="mono-label block mb-4">GROUNDED RESPONSE</span>
                <div className="space-y-4">
                  {MEMORY_ANSWER.slice(0, answerCount).map((paragraph, i) => (
                    <p
                      key={i}
                      className={`text-[13px] sm:text-sm leading-relaxed fade-up ${i === 0 ? 'text-text' : 'text-text-muted'
                        }`}
                    >
                      {paragraph}
                      {phase === 'answering' && i === answerCount - 1 && (
                        <span className="caret-blink text-primary ml-1" aria-hidden="true">
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
          <span className="mono-label mono-label-accent block mb-6">GRAPH CONTEXT</span>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-7">
            {MEMORY_CONTEXT.map((row, i) => (
              <div
                key={row.label}
                style={{
                  opacity: reached(phase, 'context') ? 1 : 0.18,
                  transform: reached(phase, 'context') || reduced ? 'none' : 'translateY(8px)',
                  transition: reduced
                    ? undefined
                    : `opacity 700ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms, transform 700ms cubic-bezier(0.16,1,0.3,1) ${i * 110}ms`,
                }}
              >
                <dt className="mono-label mb-2.5">{row.label}</dt>
                <dd className="font-mono text-xl sm:text-2xl text-text tabular-nums leading-none">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>

          <p className="mt-10 pt-6 hair-t text-[13px] text-text-muted leading-relaxed max-w-sm">
            ARIA does not retrieve text that resembles the question. It walks the symbol graph,
            collects the modules that actually participate, and answers from those.
          </p>
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
