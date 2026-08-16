import React, { useRef, useEffect, useCallback } from 'react';

/* ─────────────────────────────────────────────────────────────────────────────
 * HeroGraph — Cinematic Software Topology Canvas (Auric / Linear inspired)
 *
 * Deterministic seeded clusters representing repository intelligence:
 *   Core AST → Dependency Network → Call Hierarchy → RAG Index → Verification
 *
 * Multi-layer depth, sparse celestial graph topology, data pulses,
 * subtle mouse reactivity and delicate code symbol indicators.
 * ────────────────────────────────────────────────────────────────────────── */

interface Node {
  x: number;
  y: number;
  baseX: number;
  baseY: number;
  /** Where the node begins the assembly: scattered, unresolved. */
  spawnX: number;
  spawnY: number;
  /** Fraction of the assembly elapsed before this node starts arriving. */
  arriveAt: number;
  vx: number;
  vy: number;
  radius: number;
  opacity: number;
  layer: number;       // 0=ast, 1=symbol, 2=module, 3=caller, 4=endpoint
  depth: number;       // 0=distant, 1=main, 2=highlighted
  cluster: number;     // 0–4
  label?: string;
}

/**
 * Opening assembly.
 *
 * The repository does not fade in — it resolves. Points arrive out of a scatter
 * into their clusters, relationships draw themselves between them, and only then
 * do the module labels settle. One-shot: once `ASSEMBLE_MS` has elapsed the
 * physics takes over and this code never runs again, so the hero costs nothing
 * for the rest of the visit.
 */
const ASSEMBLE_MS = 2600;

/** Fast, no overshoot — arriving, not bouncing. */
const easeOutQuint = (t: number): number => 1 - Math.pow(1 - t, 5);

interface Edge {
  from: number;
  to: number;
  opacity: number;
  pulsePhase: number;
  isFlow: boolean;     // animated data-flow edge
}

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

const CLUSTER_CENTERS = [
  { label: 'core/ast_parser.py',             xRatio: 0.62, yRatio: 0.28 },
  { label: 'services/analysis_orch.py',       xRatio: 0.80, yRatio: 0.48 },
  { label: 'core/dependency_graph.py',        xRatio: 0.54, yRatio: 0.62 },
  { label: 'backend/routers/repositories.py', xRatio: 0.84, yRatio: 0.24 },
  { label: 'mcp/tools/search_tools.py',       xRatio: 0.72, yRatio: 0.76 },
];

function createNodes(count: number, w: number, h: number, rng: () => number): Node[] {
  const nodes: Node[] = [];
  const nodesPerCluster = Math.floor(count * 0.72);
  const scattered = count - nodesPerCluster;

  // Clustered nodes
  for (let i = 0; i < nodesPerCluster; i++) {
    const ci = i % CLUSTER_CENTERS.length;
    const c = CLUSTER_CENTERS[ci];
    const spreadX = w * 0.14;
    const spreadY = h * 0.14;
    const isKeyModule = i < CLUSTER_CENTERS.length;
    const depth = isKeyModule ? 2 : (rng() < 0.3 ? 0 : 1);

    nodes.push({
      x: c.xRatio * w + (rng() - 0.5) * spreadX * 2,
      y: c.yRatio * h + (rng() - 0.5) * spreadY * 2,
      baseX: 0, baseY: 0,
      spawnX: 0, spawnY: 0,
      /*
        Structural centres resolve first, then their surrounding symbols. So the
        composition reads as architecture appearing and detail filling in behind
        it, rather than as everything arriving at once.
      */
      arriveAt: isKeyModule ? rng() * 0.12 : 0.18 + rng() * 0.5,
      vx: (rng() - 0.5) * 0.06,
      vy: (rng() - 0.5) * 0.05,
      radius: isKeyModule ? 3.0 : depth === 0 ? 0.8 + rng() * 0.8 : 1.2 + rng() * 1.6,
      opacity: depth === 0 ? 0.08 + rng() * 0.08 : depth === 2 ? 0.45 + rng() * 0.2 : 0.18 + rng() * 0.16,
      layer: isKeyModule ? 2 : Math.floor(rng() * 5),
      depth,
      cluster: ci,
      label: isKeyModule ? c.label : undefined,
    });
  }

  // Scattered background points
  for (let i = 0; i < scattered; i++) {
    const margin = 20;
    nodes.push({
      x: margin + rng() * (w - margin * 2),
      y: margin + rng() * (h - margin * 2),
      baseX: 0, baseY: 0,
      spawnX: 0, spawnY: 0,
      // Distant field arrives last: it is depth, not subject.
      arriveAt: 0.45 + rng() * 0.5,
      vx: (rng() - 0.5) * 0.03,
      vy: (rng() - 0.5) * 0.02,
      radius: 0.6 + rng() * 0.6,
      opacity: 0.04 + rng() * 0.06,
      layer: Math.floor(rng() * 5),
      depth: 0,
      cluster: -1,
    });
  }

  /*
    Each node's origin is its resting place pushed outward from the composition's
    centre of gravity, with a deterministic angular jitter. Radial rather than
    random, so the assembly reads as a structure converging instead of dust
    settling — and seeded, so it is identical on every load.
  */
  const cx = w * 0.68;
  const cy = h * 0.5;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    n.baseX = n.x;
    n.baseY = n.y;

    const dx = n.x - cx;
    const dy = n.y - cy;
    const dist = Math.hypot(dx, dy) || 1;
    const push = 0.55 + (i % 7) * 0.045;
    const swirl = 0.22 * Math.sin(i * 1.31);

    n.spawnX = cx + (dx * (1 + push) - dy * swirl);
    n.spawnY = cy + (dy * (1 + push) + dx * swirl);
  }
  return nodes;
}

function createEdges(nodes: Node[], maxEdges: number, rng: () => number): Edge[] {
  const edges: Edge[] = [];

  // Intra-cluster edges
  for (let i = 0; i < nodes.length && edges.length < maxEdges * 0.75; i++) {
    for (let j = i + 1; j < nodes.length && edges.length < maxEdges * 0.75; j++) {
      if (nodes[i].cluster < 0 || nodes[j].cluster < 0) continue;
      if (nodes[i].cluster !== nodes[j].cluster) continue;
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 140 && rng() < 0.45) {
        edges.push({
          from: i, to: j,
          opacity: 0.05 + rng() * 0.08,
          pulsePhase: rng() * Math.PI * 2,
          isFlow: rng() < 0.25,
        });
      }
    }
  }

  // Inter-cluster flow highways
  for (let ci = 0; ci < CLUSTER_CENTERS.length - 1 && edges.length < maxEdges; ci++) {
    const cj = ci + 1;
    const nodesA = nodes.filter((_, idx) => nodes[idx].cluster === ci && nodes[idx].depth >= 1);
    const nodesB = nodes.filter((_, idx) => nodes[idx].cluster === cj && nodes[idx].depth >= 1);
    const crossCount = Math.min(3, nodesA.length, nodesB.length);
    for (let k = 0; k < crossCount; k++) {
      const a = nodes.indexOf(nodesA[Math.floor(rng() * nodesA.length)]);
      const b = nodes.indexOf(nodesB[Math.floor(rng() * nodesB.length)]);
      if (a >= 0 && b >= 0) {
        edges.push({
          from: a, to: b,
          opacity: 0.08 + rng() * 0.06,
          pulsePhase: rng() * Math.PI * 2,
          isFlow: true,
        });
      }
    }
  }

  return edges;
}

export const HeroGraph: React.FC<{ className?: string }> = ({ className = '' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const sizeRef = useRef({ w: 0, h: 0 });
  /** First painted frame, so the opening assembly plays exactly once per visit. */
  const assembleStart = useRef(0);
  const mouseRef = useRef<{ x: number; y: number; active: boolean }>({ x: -1000, y: -1000, active: false });
  const reducedMotion = useRef(false);
  const visibleRef = useRef(true);

  const init = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = rect.width;
    const h = rect.height;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    sizeRef.current = { w, h };
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.scale(dpr, dpr);

    const rng = mulberry32(1337);
    const isMobile = w < 640;
    const nodeCount = isMobile ? 36 : w < 1024 ? 60 : 88;
    const maxEdges = isMobile ? 28 : w < 1024 ? 64 : 96;

    nodesRef.current = createNodes(nodeCount, w, h, rng);
    edgesRef.current = createEdges(nodesRef.current, maxEdges, rng);
  }, []);

  const draw = useCallback((time: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const { w, h } = sizeRef.current;
    ctx.clearRect(0, 0, w, h);

    const nodes = nodesRef.current;
    const edges = edgesRef.current;
    const mouse = mouseRef.current;

    /*
      ── Assembly ─────────────────────────────────────────────────────────────
      For the first ASSEMBLE_MS the repository resolves out of a scatter. During
      that window positions are interpolated rather than simulated, so the
      arrival is exact and identical on every load; afterwards `assembling` goes
      false for good and the drift physics takes over.
    */
    if (assembleStart.current === 0) assembleStart.current = time;
    const assembleT = reducedMotion.current
      ? 1
      : Math.min(1, Math.max(0, (time - assembleStart.current) / ASSEMBLE_MS));
    const assembling = assembleT < 1;

    if (assembling) {
      for (const n of nodes) {
        // Remap the global progress onto this node's own arrival window.
        const local = Math.min(1, Math.max(0, (assembleT - n.arriveAt) / (1 - n.arriveAt)));
        const e = easeOutQuint(local);
        n.x = n.spawnX + (n.baseX - n.spawnX) * e;
        n.y = n.spawnY + (n.baseY - n.spawnY) * e;
        // Keep the simulation quiet until it takes over, so there is no lurch.
        n.vx = 0;
        n.vy = 0;
      }
    }

    // Update positions — gentle anchored drift + subtle mouse influence
    if (!reducedMotion.current && !assembling) {
      for (const n of nodes) {
        n.x += n.vx;
        n.y += n.vy;

        // Drift back toward base position
        const driftForce = 0.0004;
        n.vx += (n.baseX - n.x) * driftForce;
        n.vy += (n.baseY - n.y) * driftForce;

        // Subtle mouse repulsion/attraction
        if (mouse.active) {
          const dx = n.x - mouse.x;
          const dy = n.y - mouse.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 180 && dist > 1) {
            const force = (1 - dist / 180) * 0.08;
            n.vx += (dx / dist) * force;
            n.vy += (dy / dist) * force;
          }
        }

        // Damping
        n.vx *= 0.998;
        n.vy *= 0.998;
        n.x = Math.max(8, Math.min(w - 8, n.x));
        n.y = Math.max(8, Math.min(h - 8, n.y));
      }
    }

    // ── Phase 00: Architectural grid & technical registration marks ──────
    const gridSize = Math.max(70, Math.floor(w / 14));
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.014)';
    ctx.lineWidth = 0.5;
    for (let x = gridSize; x < w; x += gridSize) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
    }
    for (let y = gridSize; y < h; y += gridSize) {
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
    }
    ctx.stroke();

    // Technical registration crosses at select intersections
    ctx.strokeStyle = 'rgba(94, 106, 210, 0.12)';
    ctx.lineWidth = 0.75;
    const crossSize = 3;
    for (let x = gridSize * 2; x < w - gridSize; x += gridSize * 3) {
      for (let y = gridSize * 2; y < h - gridSize; y += gridSize * 2) {
        ctx.beginPath();
        ctx.moveTo(x - crossSize, y);
        ctx.lineTo(x + crossSize, y);
        ctx.moveTo(x, y - crossSize);
        ctx.lineTo(x, y + crossSize);
        ctx.stroke();
      }
    }

    // Draw pointer awareness relationship rays
    if (!assembling && mouse.active && !reducedMotion.current) {
      const nearbyNodes = nodes
        .filter(n => Math.hypot(n.x - mouse.x, n.y - mouse.y) < 170)
        .sort((a, b) => Math.hypot(a.x - mouse.x, a.y - mouse.y) - Math.hypot(b.x - mouse.x, b.y - mouse.y))
        .slice(0, 2);

      for (const n of nearbyNodes) {
        const d = Math.hypot(n.x - mouse.x, n.y - mouse.y);
        const rayAlpha = (1 - d / 170) * 0.28;
        ctx.beginPath();
        ctx.moveTo(mouse.x, mouse.y);
        ctx.lineTo(n.x, n.y);
        ctx.strokeStyle = `rgba(129, 140, 248, ${rayAlpha.toFixed(3)})`;
        ctx.lineWidth = 0.5;
        ctx.setLineDash([2, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Draw edges
    for (const edge of edges) {
      const a = nodes[edge.from];
      const b = nodes[edge.to];
      if (!a || !b) continue;

      const pulseMod = reducedMotion.current ? 1 : 0.5 + 0.5 * Math.sin(time * 0.0005 + edge.pulsePhase);

      /*
        Relationships cannot exist before the things they relate. Each edge waits
        until both endpoints have essentially arrived, then draws itself from
        source to target — so the reader sees structure, then connection.
      */
      let reach = 1;
      if (assembling) {
        const ready = Math.min(
          1,
          Math.max(0, (assembleT - Math.max(a.arriveAt, b.arriveAt) - 0.08) / 0.3),
        );
        if (ready <= 0) continue;
        reach = easeOutQuint(ready);
      }

      const edgeOpacity = edge.opacity * pulseMod * (assembling ? reach : 1);

      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(a.x + (b.x - a.x) * reach, a.y + (b.y - a.y) * reach);
      ctx.strokeStyle = `rgba(94, 106, 210, ${edgeOpacity})`;
      ctx.lineWidth = edge.isFlow ? 0.75 : 0.35;
      ctx.stroke();

      // Data-flow packet traveling along flow edges
      if (edge.isFlow && !reducedMotion.current && !assembling) {
        const flowT = ((time * 0.00012 + edge.pulsePhase) % 1);
        const fx = a.x + (b.x - a.x) * flowT;
        const fy = a.y + (b.y - a.y) * flowT;

        // A soft halo ring instead of shadowBlur: same read, far cheaper to
        // rasterise every frame.
        ctx.beginPath();
        ctx.arc(fx, fy, 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(94, 106, 210, ${0.18 * pulseMod})`;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(fx, fy, 1.5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(180, 200, 255, ${0.45 * pulseMod})`;
        ctx.fill();
      }
    }

    // Draw nodes across 3 depth planes (0=distant soft, 1=structural, 2=key modules)
    for (let d = 0; d <= 2; d++) {
      for (const n of nodes) {
        if (n.depth !== d) continue;

        const isAccent = n.layer === 0 || n.layer === 2;
        const isHovered = !assembling && mouse.active && Math.hypot(n.x - mouse.x, n.y - mouse.y) < 65;

        /*
          A node arrives slightly large and settles — the one overshoot in the
          whole composition, and it is what makes the assembly feel physical
          rather than interpolated.
        */
        let arrive = 1;
        if (assembling) {
          const local = Math.min(1, Math.max(0, (assembleT - n.arriveAt) / (1 - n.arriveAt)));
          if (local <= 0) continue;
          arrive = local;
        }
        const settle = assembling ? 1 + Math.sin(Math.PI * arrive) * 0.55 : 1;

        ctx.beginPath();
        ctx.arc(n.x, n.y, (isHovered ? n.radius * 1.4 : n.radius) * settle, 0, Math.PI * 2);

        // One alpha for the node, its halo and its label — they arrive together.
        ctx.globalAlpha = arrive;

        if (n.depth === 2 || isHovered) {
          ctx.fillStyle = isAccent ? 'rgba(120, 140, 245, 0.92)' : 'rgba(230, 235, 250, 0.88)';
        } else if (n.depth === 1) {
          ctx.fillStyle = isAccent ? `rgba(94, 106, 210, ${n.opacity * 1.25})` : `rgba(140, 145, 160, ${n.opacity})`;
        } else {
          ctx.fillStyle = `rgba(80, 85, 100, ${n.opacity * 0.85})`;
        }
        ctx.fill();

        // Subtle ambient halo for dominant module nodes
        if (n.depth === 2) {
          const glowPulse = reducedMotion.current ? 1 : 0.7 + 0.3 * Math.sin(time * 0.0008 + n.baseX);
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.radius + 5, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(94, 106, 210, ${0.08 * glowPulse})`;
          ctx.fill();

          /*
            Module paths settle last. Naming a thing is the final step of
            recognising it, so the labels arrive only once the structure they
            annotate has stopped moving.
          */
          if (n.label && w > 768 && !assembling) {
            ctx.font = '9px "JetBrains Mono", monospace';
            ctx.fillStyle = `rgba(142, 147, 158, ${0.45 * glowPulse})`;
            ctx.fillText(n.label, n.x + 8, n.y + 3);
          }
        }

        ctx.globalAlpha = 1;
      }
    }

    // Reduced motion gets a single composed frame, never a loop.
    if (reducedMotion.current) {
      animRef.current = 0;
      return;
    }
    animRef.current = requestAnimationFrame(draw);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    reducedMotion.current = mql.matches;
    init();

    const start = () => {
      if (animRef.current || reducedMotion.current) return;
      animRef.current = requestAnimationFrame(draw);
    };

    const stop = () => {
      if (!animRef.current) return;
      cancelAnimationFrame(animRef.current);
      animRef.current = 0;
    };

    // Paint once so the canvas is never blank, then loop only while visible.
    draw(performance.now());

    const handleMouseMove = (e: MouseEvent) => {
      if (reducedMotion.current) return;
      const rect = canvas.getBoundingClientRect();
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        active: true,
      };
    };

    const handleMouseLeave = () => {
      mouseRef.current.active = false;
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('mouseleave', handleMouseLeave);

    const ro = new ResizeObserver(() => {
      init();
      if (reducedMotion.current) draw(performance.now());
    });
    ro.observe(canvas);

    // Off-screen means no frames at all, rather than frames that early-return.
    const io = new IntersectionObserver(
      ([entry]) => {
        visibleRef.current = entry.isIntersecting;
        if (entry.isIntersecting) start();
        else stop();
      },
      { threshold: 0.05 }
    );
    io.observe(canvas);

    const onVisibility = () => {
      if (document.hidden) stop();
      else if (visibleRef.current) start();
    };
    document.addEventListener('visibilitychange', onVisibility);

    const handleMotion = (e: MediaQueryListEvent) => {
      reducedMotion.current = e.matches;
      if (e.matches) {
        stop();
        draw(performance.now());
      } else if (visibleRef.current) {
        start();
      }
    };
    mql.addEventListener('change', handleMotion);

    return () => {
      stop();
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
      document.removeEventListener('visibilitychange', onVisibility);
      ro.disconnect();
      io.disconnect();
      mql.removeEventListener('change', handleMotion);
    };
  }, [init, draw]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full ${className}`}
      style={{ display: 'block' }}
      aria-hidden="true"
    />
  );
};

export default HeroGraph;
