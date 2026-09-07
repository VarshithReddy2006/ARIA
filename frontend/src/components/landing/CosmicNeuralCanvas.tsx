import React, { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  baseAlpha: number;
  pulseSpeed: number;
  pulsePhase: number;
}

const COLORS = [
  'rgba(129, 140, 248, ',  // Indigo
  'rgba(56, 189, 248, ',   // Sky
  'rgba(52, 211, 153, ',   // Emerald
  'rgba(167, 139, 250, ',  // Purple
];

export const CosmicNeuralCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const mouse = {
      x: -1000,
      y: -1000,
      radius: 180,
      active: false,
    };

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      initParticles();
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
      mouse.active = true;
    };

    const handleMouseLeave = () => {
      mouse.active = false;
      mouse.x = -1000;
      mouse.y = -1000;
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);

    const particleCount = Math.min(65, Math.floor((width * height) / 22000));
    let particles: Particle[] = [];

    const initParticles = () => {
      particles = [];
      for (let i = 0; i < particleCount; i++) {
        const color = COLORS[Math.floor(Math.random() * COLORS.length)];
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.45,
          vy: (Math.random() - 0.5) * 0.45,
          radius: Math.random() * 2 + 1,
          color,
          baseAlpha: Math.random() * 0.4 + 0.25,
          pulseSpeed: Math.random() * 0.02 + 0.008,
          pulsePhase: Math.random() * Math.PI * 2,
        });
      }
    };

    initParticles();

    const render = (time: number) => {
      ctx.clearRect(0, 0, width, height);

      // Render cosmic background radial gradient focused on mouse if active
      if (mouse.active) {
        const radialGradient = ctx.createRadialGradient(
          mouse.x,
          mouse.y,
          0,
          mouse.x,
          mouse.y,
          mouse.radius * 1.6
        );
        radialGradient.addColorStop(0, 'rgba(99, 102, 241, 0.055)');
        radialGradient.addColorStop(0.5, 'rgba(56, 189, 248, 0.02)');
        radialGradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = radialGradient;
        ctx.fillRect(0, 0, width, height);
      }

      // Update and draw particles
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        // Move
        p.x += p.vx;
        p.y += p.vy;

        // Wrap edges
        if (p.x < 0) p.x = width;
        else if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        else if (p.y > height) p.y = 0;

        // Mouse attraction physics
        if (mouse.active) {
          const dx = mouse.x - p.x;
          const dy = mouse.y - p.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < mouse.radius) {
            const force = (1 - dist / mouse.radius) * 0.4;
            p.x += (dx / dist) * force;
            p.y += (dy / dist) * force;

            // Draw line to mouse
            const lineAlpha = (1 - dist / mouse.radius) * 0.35;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.strokeStyle = `rgba(129, 140, 248, ${lineAlpha.toFixed(3)})`;
            ctx.lineWidth = 0.75;
            ctx.stroke();
          }
        }

        // Pulse alpha
        p.pulsePhase += p.pulseSpeed;
        const currentAlpha = p.baseAlpha + Math.sin(p.pulsePhase) * 0.15;

        // Draw particle node
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}${Math.max(0.05, currentAlpha).toFixed(3)})`;
        ctx.fill();

        // Node aura glow
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius * 2.8, 0, Math.PI * 2);
        ctx.fillStyle = `${p.color}${(currentAlpha * 0.18).toFixed(3)})`;
        ctx.fill();

        // Connect nearby particles (Constellation mesh)
        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dx = p.x - p2.x;
          const dy = p.y - p2.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          const maxDist = 135;
          if (dist < maxDist) {
            const alpha = (1 - dist / maxDist) * 0.22;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(129, 140, 248, ${alpha.toFixed(3)})`;
            ctx.lineWidth = 0.65;
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-[1] opacity-75"
      aria-hidden="true"
    />
  );
};

export default CosmicNeuralCanvas;
