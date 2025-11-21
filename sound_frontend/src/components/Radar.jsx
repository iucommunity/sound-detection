import React, { useRef, useEffect } from 'react';
import { polarToCartesian } from '../data/radarPoints';

const Radar = ({ points = [] }) => {
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const sweepProgressRef = useRef(0);
  const containerRef = useRef(null);

  // Initialize and resize canvas
  const initializeCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return false;

    const container = canvas.parentElement || containerRef.current;
    if (container) {
      const containerWidth = container.clientWidth || 600;
      const containerHeight = container.clientHeight || 600;
      const size = Math.max(400, Math.min(containerWidth, containerHeight) - 40);
      canvas.width = size;
      canvas.height = size;
      return true;
    }
    return false;
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Initialize canvas size
    if (!initializeCanvas()) {
      // Fallback if container not ready
      canvas.width = 600;
      canvas.height = 600;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Ensure canvas has valid dimensions
    if (canvas.width <= 0 || canvas.height <= 0) {
      console.warn('Canvas has invalid dimensions');
      return;
    }

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const maxRadius = Math.max(50, Math.min(centerX, centerY) - 40);

    const draw = () => {
      // Clear canvas
      ctx.fillStyle = 'rgba(10, 22, 40, 0.3)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw concentric circles
      ctx.strokeStyle = '#1a3a52';
      ctx.lineWidth = 1;
      for (let i = 1; i <= 5; i++) {
        ctx.beginPath();
        ctx.arc(centerX, centerY, (maxRadius / 5) * i, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Draw grid lines (every 30 degrees)
      ctx.strokeStyle = '#1a3a52';
      ctx.lineWidth = 1;
      for (let angle = 0; angle < 360; angle += 30) {
        const rad = (angle * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + maxRadius * Math.cos(rad),
          centerY + maxRadius * Math.sin(rad)
        );
        ctx.stroke();
      }

      // Draw cardinal directions
      ctx.fillStyle = '#4a6b7f';
      ctx.font = '14px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      
      const directions = [
        { angle: 0, label: 'N' },
        { angle: 90, label: 'E' },
        { angle: 180, label: 'S' },
        { angle: 270, label: 'W' },
      ];

      directions.forEach(({ angle, label }) => {
        const rad = (angle * Math.PI) / 180;
        const x = centerX + (maxRadius + 20) * Math.cos(rad);
        const y = centerY + (maxRadius + 20) * Math.sin(rad);
        ctx.fillText(label, x, y);
      });

      // Draw expanding radar sweep circle
      const sweepRadius = sweepProgressRef.current * maxRadius;
      if (sweepRadius > 0 && sweepRadius < maxRadius) {
        const innerRadius = Math.max(0, sweepRadius - 20);
        const gradient = ctx.createRadialGradient(
          centerX,
          centerY,
          innerRadius,
          centerX,
          centerY,
          sweepRadius
        );
        gradient.addColorStop(0, 'rgba(0, 255, 136, 0.3)');
        gradient.addColorStop(0.5, 'rgba(0, 212, 255, 0.2)');
        gradient.addColorStop(1, 'rgba(0, 255, 136, 0)');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(centerX, centerY, sweepRadius, 0, Math.PI * 2);
        ctx.fill();

        // Outer edge glow
        ctx.strokeStyle = 'rgba(0, 255, 136, 0.6)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, sweepRadius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Draw radar points
      points.forEach((point) => {
        const { x, y } = polarToCartesian(point.direction, point.distance, maxRadius);
        const screenX = centerX + x;
        const screenY = centerY - y; // Flip Y axis for screen coordinates

        // Draw point with intensity-based size and color
        const size = 4 + point.intensity * 8;
        const alpha = 0.6 + point.intensity * 0.4;

        // Outer glow
        const pointGradient = ctx.createRadialGradient(
          screenX,
          screenY,
          0,
          screenX,
          screenY,
          size * 2
        );
        pointGradient.addColorStop(0, `rgba(0, 255, 136, ${alpha})`);
        pointGradient.addColorStop(0.5, `rgba(0, 212, 255, ${alpha * 0.5})`);
        pointGradient.addColorStop(1, 'rgba(0, 255, 136, 0)');

        ctx.fillStyle = pointGradient;
        ctx.beginPath();
        ctx.arc(screenX, screenY, size * 2, 0, Math.PI * 2);
        ctx.fill();

        // Inner point
        ctx.fillStyle = `rgba(0, 255, 136, ${alpha})`;
        ctx.beginPath();
        ctx.arc(screenX, screenY, size / 2, 0, Math.PI * 2);
        ctx.fill();

        // Pulse animation
        const pulseSize = size + Math.sin(Date.now() / 200) * 2;
        ctx.strokeStyle = `rgba(0, 255, 136, ${alpha * 0.3})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(screenX, screenY, pulseSize, 0, Math.PI * 2);
        ctx.stroke();
      });

      // Draw center point
      ctx.fillStyle = '#00ff88';
      ctx.beginPath();
      ctx.arc(centerX, centerY, 3, 0, Math.PI * 2);
      ctx.fill();

      // Update sweep progress
      sweepProgressRef.current += 0.02;
      if (sweepProgressRef.current > 1) {
        sweepProgressRef.current = 0;
      }

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    // Start the animation loop
    draw();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, [points]);

  // Handle canvas resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resizeCanvas = () => {
      initializeCanvas();
    };

    // Initial resize with a small delay to ensure DOM is ready
    const timeoutId = setTimeout(resizeCanvas, 100);
    
    // Use ResizeObserver for better resize handling
    let resizeObserver;
    try {
      resizeObserver = new ResizeObserver(() => {
        resizeCanvas();
      });
      
      const container = canvas.parentElement;
      if (container) {
        resizeObserver.observe(container);
      }
    } catch (e) {
      // Fallback if ResizeObserver not available
      console.warn('ResizeObserver not available, using window resize');
    }
    
    window.addEventListener('resize', resizeCanvas);
    
    return () => {
      clearTimeout(timeoutId);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener('resize', resizeCanvas);
    };
  }, []);

  return (
    <div ref={containerRef} className="relative flex items-center justify-center w-full h-full min-h-[600px]">
      <canvas
        ref={canvasRef}
        className="rounded-lg shadow-2xl"
        width={600}
        height={600}
        style={{
          background: 'radial-gradient(circle, rgba(15, 30, 53, 0.8) 0%, rgba(10, 22, 40, 0.95) 100%)',
          border: '1px solid rgba(26, 58, 82, 0.5)',
          maxWidth: '100%',
          maxHeight: '100%',
          display: 'block',
        }}
      />
      {/* Overlay info */}
      <div className="absolute bottom-4 left-4 text-xs text-gray-400 font-mono">
        <div>Points: {points.length}</div>
        <div>Range: 0-1.0</div>
      </div>
    </div>
  );
};

export default Radar;

