import React, { useRef, useEffect } from 'react';
import { polarToCartesian } from '../data/radarPoints';

const Radar = ({ points = [] }) => {
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const sweepProgressRef = useRef(0);
  const containerRef = useRef(null);
  const sweepHistoryRef = useRef([]);
  const ripplesRef = useRef([]);
  const lastDropTimeRef = useRef(0);

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
      // Clear canvas with subtle fade effect
      ctx.fillStyle = 'rgba(10, 22, 40, 0.95)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw background radial gradient
      const bgGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, maxRadius
      );
      bgGradient.addColorStop(0, 'rgba(15, 30, 53, 0.3)');
      bgGradient.addColorStop(0.5, 'rgba(10, 22, 40, 0.5)');
      bgGradient.addColorStop(1, 'rgba(5, 15, 30, 0.8)');
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw concentric circles with gradient
      for (let i = 1; i <= 5; i++) {
        const radius = (maxRadius / 5) * i;
        const alpha = 0.3 - (i * 0.05);
        
        // Outer glow
        ctx.strokeStyle = `rgba(26, 58, 82, ${alpha})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Main circle
        ctx.strokeStyle = `rgba(74, 107, 127, ${alpha + 0.2})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Draw grid lines with varying opacity
      for (let angle = 0; angle < 360; angle += 30) {
        const rad = (angle * Math.PI) / 180;
        const isCardinal = angle % 90 === 0;
        
        ctx.strokeStyle = isCardinal 
          ? 'rgba(0, 255, 136, 0.3)' 
          : 'rgba(26, 58, 82, 0.4)';
        ctx.lineWidth = isCardinal ? 1.5 : 1;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + maxRadius * Math.cos(rad),
          centerY + maxRadius * Math.sin(rad)
        );
        ctx.stroke();
      }
      
      // Draw minor grid lines (every 15 degrees)
      ctx.strokeStyle = 'rgba(26, 58, 82, 0.2)';
      ctx.lineWidth = 0.5;
      for (let angle = 0; angle < 360; angle += 15) {
        if (angle % 30 === 0) continue; // Skip major lines
        const rad = (angle * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + maxRadius * Math.cos(rad),
          centerY + maxRadius * Math.sin(rad)
        );
        ctx.stroke();
      }

      // Draw cardinal directions with glow
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      
      const directions = [
        { angle: 0, label: 'N', full: 'NORTH' },
        { angle: 90, label: 'E', full: 'EAST' },
        { angle: 180, label: 'S', full: 'SOUTH' },
        { angle: 270, label: 'W', full: 'WEST' },
      ];

      directions.forEach(({ angle, label, full }) => {
        const rad = (angle * Math.PI) / 180;
        const x = centerX + (maxRadius + 25) * Math.cos(rad);
        const y = centerY + (maxRadius + 25) * Math.sin(rad);
        
        // Glow effect
        ctx.shadowBlur = 10;
        ctx.shadowColor = 'rgba(0, 255, 136, 0.5)';
        ctx.fillStyle = '#00ff88';
        ctx.font = 'bold 16px monospace';
        ctx.fillText(label, x, y);
        
        // Full label
        ctx.shadowBlur = 5;
        ctx.fillStyle = 'rgba(0, 255, 136, 0.6)';
        ctx.font = '10px monospace';
        const labelX = centerX + (maxRadius + 40) * Math.cos(rad);
        const labelY = centerY + (maxRadius + 40) * Math.sin(rad);
        ctx.fillText(full, labelX, labelY);
        
        ctx.shadowBlur = 0;
      });

      // Water drop effect - create new ripple periodically
      const now = Date.now();
      const timeSinceLastDrop = now - lastDropTimeRef.current;
      if (timeSinceLastDrop > 2000) { // Create new drop every 2 seconds
        ripplesRef.current.push({
          radius: 0,
          opacity: 1,
          time: now,
          maxRadius: maxRadius,
          dropTime: now // Track when drop was created
        });
        lastDropTimeRef.current = now;
      }

      // Update water ripples
      ripplesRef.current = ripplesRef.current
        .map(ripple => {
          const age = (now - ripple.time) / 1000; // age in seconds
          const speed = 100; // pixels per second - slower for more visible effect
          const newRadius = age * speed;
          const progress = newRadius / ripple.maxRadius;
          
          return {
            ...ripple,
            radius: newRadius,
            opacity: Math.max(0, (1 - progress) * 0.7) // Fade out as it expands
          };
        })
        .filter(ripple => ripple.opacity > 0 && ripple.radius < ripple.maxRadius * 1.2);

      // Draw water drop at center when it first appears (before ripples)
      const recentDrops = ripplesRef.current.filter(r => r.dropTime && (now - r.dropTime) < 300);
      recentDrops.forEach((ripple) => {
        const dropAge = (now - ripple.dropTime) / 300; // 0 to 1 over 300ms
        const dropSize = 4 + Math.sin(dropAge * Math.PI) * 3;
        const dropAlpha = Math.max(0, 1 - dropAge * 1.5);
        
        if (dropAlpha > 0) {
          // Drop shadow/ripple at center
          const dropGradient = ctx.createRadialGradient(
            centerX, centerY, 0,
            centerX, centerY, dropSize * 4
          );
          dropGradient.addColorStop(0, `rgba(0, 212, 255, ${dropAlpha * 0.8})`);
          dropGradient.addColorStop(0.4, `rgba(0, 255, 136, ${dropAlpha * 0.5})`);
          dropGradient.addColorStop(1, 'rgba(0, 212, 255, 0)');
          
          ctx.fillStyle = dropGradient;
          ctx.beginPath();
          ctx.arc(centerX, centerY, dropSize * 4, 0, Math.PI * 2);
          ctx.fill();
          
          // Drop itself
          ctx.fillStyle = `rgba(0, 255, 136, ${dropAlpha})`;
          ctx.beginPath();
          ctx.arc(centerX, centerY, dropSize, 0, Math.PI * 2);
          ctx.fill();
          
          // Drop highlight
          ctx.fillStyle = `rgba(255, 255, 255, ${dropAlpha * 0.5})`;
          ctx.beginPath();
          ctx.arc(centerX - dropSize * 0.3, centerY - dropSize * 0.3, dropSize * 0.3, 0, Math.PI * 2);
          ctx.fill();
        }
      });

      // Draw water ripples (like water drop on water) - expanding circles
      ripplesRef.current.forEach((ripple) => {
        if (ripple.radius <= 5) return; // Don't draw until ripple starts expanding
        
        // Draw multiple concentric rings for each ripple to create wave effect
        for (let ring = 0; ring < 4; ring++) {
          const ringOffset = ring * 20;
          const ringRadius = Math.max(0, ripple.radius - ringOffset);
          if (ringRadius < 5) continue;
          
          const ringOpacity = ripple.opacity * (1 - ring * 0.25) * (1 - ringRadius / ripple.maxRadius * 0.5);
          const ringWidth = 1.5 + ring * 1.5;
          
          // Create gradient for each ring
          const ringGradient = ctx.createRadialGradient(
            centerX, centerY, ringRadius - ringWidth,
            centerX, centerY, ringRadius + ringWidth
          );
          ringGradient.addColorStop(0, `rgba(0, 255, 136, ${ringOpacity * 0.3})`);
          ringGradient.addColorStop(0.5, `rgba(0, 212, 255, ${ringOpacity * 0.6})`);
          ringGradient.addColorStop(1, `rgba(0, 255, 136, ${ringOpacity * 0.2})`);
          
          // Outer ring with gradient
          ctx.strokeStyle = ringGradient;
          ctx.lineWidth = ringWidth;
          ctx.beginPath();
          ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
          ctx.stroke();
          
          // Bright inner edge
          if (ring === 0) {
            ctx.strokeStyle = `rgba(0, 255, 136, ${ringOpacity * 0.9})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      });

      // Update sweep history for trail effect (slower)
      const currentSweep = sweepProgressRef.current * maxRadius;
      if (sweepHistoryRef.current.length === 0 || 
          currentSweep - sweepHistoryRef.current[sweepHistoryRef.current.length - 1].radius > 15) {
        sweepHistoryRef.current.push({
          radius: currentSweep,
          opacity: 1,
          time: now
        });
      }
      
      // Remove old sweeps and update opacity
      sweepHistoryRef.current = sweepHistoryRef.current
        .map(sweep => ({
          ...sweep,
          opacity: Math.max(0, sweep.opacity - 0.015) // Slower fade
        }))
        .filter(sweep => sweep.opacity > 0 && sweep.radius < maxRadius * 1.1);

      // Draw multiple expanding circles (trail effect)
      sweepHistoryRef.current.forEach((sweep, index) => {
        if (sweep.radius <= 0 || sweep.radius > maxRadius) return;
        
        const ringWidth = 30;
        const innerRadius = Math.max(0, sweep.radius - ringWidth);
        const outerRadius = sweep.radius;
        
        // Create gradient for each ring
        const gradient = ctx.createRadialGradient(
          centerX,
          centerY,
          innerRadius,
          centerX,
          centerY,
          outerRadius
        );
        
        // Vary colors based on position
        const progress = sweep.radius / maxRadius;
        const primaryColor = progress < 0.5 
          ? 'rgba(0, 255, 136, ' 
          : 'rgba(0, 212, 255, ';
        const secondaryColor = progress < 0.5
          ? 'rgba(0, 212, 255, '
          : 'rgba(138, 43, 226, ';
        
        gradient.addColorStop(0, primaryColor + (sweep.opacity * 0.4) + ')');
        gradient.addColorStop(0.5, secondaryColor + (sweep.opacity * 0.3) + ')');
        gradient.addColorStop(1, primaryColor + '0)');

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(centerX, centerY, outerRadius, 0, Math.PI * 2);
        ctx.fill();

        // Outer edge with varying intensity
        const edgeAlpha = sweep.opacity * (0.8 - progress * 0.3);
        ctx.strokeStyle = `rgba(0, 255, 136, ${edgeAlpha})`;
        ctx.lineWidth = 2 + (1 - progress) * 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, outerRadius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Inner edge glow
        if (innerRadius > 0) {
          ctx.strokeStyle = `rgba(0, 212, 255, ${sweep.opacity * 0.2})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(centerX, centerY, innerRadius, 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      // Draw radar points with enhanced visuals
      points.forEach((point) => {
        const { x, y } = polarToCartesian(point.direction, point.distance, maxRadius);
        const screenX = centerX + x;
        const screenY = centerY - y; // Flip Y axis for screen coordinates

        // Draw point with intensity-based size and color
        const baseSize = 5 + point.intensity * 10;
        const alpha = 0.7 + point.intensity * 0.3;
        const time = Date.now() / 1000;
        
        // Multiple pulse rings
        for (let i = 0; i < 3; i++) {
          const pulseOffset = (time * 2 + i * 0.5) % 2;
          const pulseSize = baseSize + pulseOffset * 15;
          const pulseAlpha = (1 - pulseOffset) * alpha * 0.2;
          
          if (pulseAlpha > 0) {
            ctx.strokeStyle = `rgba(0, 255, 136, ${pulseAlpha})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(screenX, screenY, pulseSize, 0, Math.PI * 2);
            ctx.stroke();
          }
        }

        // Outer glow with multiple layers
        const glowLayers = [
          { radius: baseSize * 3, alpha: alpha * 0.3 },
          { radius: baseSize * 2, alpha: alpha * 0.5 },
          { radius: baseSize * 1.5, alpha: alpha * 0.7 }
        ];
        
        glowLayers.forEach(({ radius, alpha: layerAlpha }) => {
          const pointGradient = ctx.createRadialGradient(
            screenX, screenY, 0,
            screenX, screenY, radius
          );
          pointGradient.addColorStop(0, `rgba(0, 255, 136, ${layerAlpha})`);
          pointGradient.addColorStop(0.5, `rgba(0, 212, 255, ${layerAlpha * 0.6})`);
          pointGradient.addColorStop(1, 'rgba(0, 255, 136, 0)');

          ctx.fillStyle = pointGradient;
          ctx.beginPath();
          ctx.arc(screenX, screenY, radius, 0, Math.PI * 2);
          ctx.fill();
        });

        // Main point core
        const coreGradient = ctx.createRadialGradient(
          screenX, screenY, 0,
          screenX, screenY, baseSize
        );
        coreGradient.addColorStop(0, `rgba(255, 255, 255, ${alpha})`);
        coreGradient.addColorStop(0.3, `rgba(0, 255, 136, ${alpha})`);
        coreGradient.addColorStop(1, `rgba(0, 212, 255, ${alpha * 0.5})`);
        
        ctx.fillStyle = coreGradient;
        ctx.beginPath();
        ctx.arc(screenX, screenY, baseSize, 0, Math.PI * 2);
        ctx.fill();
        
        // Bright center dot
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        ctx.beginPath();
        ctx.arc(screenX, screenY, baseSize * 0.3, 0, Math.PI * 2);
        ctx.fill();
        
        // Direction line to center
        ctx.strokeStyle = `rgba(0, 255, 136, ${alpha * 0.2})`;
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(screenX, screenY);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Draw center point with pulsing effect
      const centerPulse = 3 + Math.sin(Date.now() / 300) * 2;
      const centerGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, centerPulse * 2
      );
      centerGradient.addColorStop(0, 'rgba(0, 255, 136, 1)');
      centerGradient.addColorStop(0.5, 'rgba(0, 212, 255, 0.6)');
      centerGradient.addColorStop(1, 'rgba(0, 255, 136, 0)');
      
      ctx.fillStyle = centerGradient;
      ctx.beginPath();
      ctx.arc(centerX, centerY, centerPulse * 2, 0, Math.PI * 2);
      ctx.fill();
      
      ctx.fillStyle = '#00ff88';
      ctx.beginPath();
      ctx.arc(centerX, centerY, centerPulse, 0, Math.PI * 2);
      ctx.fill();
      
      // Center crosshair
      ctx.strokeStyle = 'rgba(0, 255, 136, 0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(centerX - 8, centerY);
      ctx.lineTo(centerX + 8, centerY);
      ctx.moveTo(centerX, centerY - 8);
      ctx.lineTo(centerX, centerY + 8);
      ctx.stroke();

      // Update sweep progress (slower speed)
      sweepProgressRef.current += 0.008; // Reduced from 0.015 to make it slower
      if (sweepProgressRef.current > 1) {
        sweepProgressRef.current = 0;
        // Keep last few sweeps for smooth transition
        sweepHistoryRef.current = sweepHistoryRef.current.slice(-3);
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
      {/* Outer glow effect */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-full h-full max-w-[90vh] max-h-[90vh] rounded-full bg-radar-primary/5 blur-3xl animate-pulse-slow"></div>
      </div>
      
      <canvas
        ref={canvasRef}
        className="rounded-2xl shadow-2xl relative z-10"
        width={600}
        height={600}
        style={{
          background: 'radial-gradient(circle at center, rgba(15, 30, 53, 0.9) 0%, rgba(10, 22, 40, 0.98) 50%, rgba(5, 15, 30, 1) 100%)',
          border: '2px solid rgba(26, 58, 82, 0.6)',
          boxShadow: '0 0 60px rgba(0, 255, 136, 0.1), inset 0 0 60px rgba(0, 212, 255, 0.05)',
          maxWidth: '100%',
          maxHeight: '100%',
          display: 'block',
        }}
      />
      {/* Overlay info with better styling */}
      <div className="absolute bottom-6 left-6 bg-radar-surface/80 backdrop-blur-md rounded-lg p-3 border border-radar-grid/50 shadow-xl">
        <div className="text-xs font-mono space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-radar-primary animate-pulse"></div>
            <span className="text-radar-primary font-semibold">ACTIVE</span>
          </div>
          <div className="text-gray-300">
            <span className="text-gray-500">Points:</span> <span className="text-radar-secondary font-bold">{points.length}</span>
          </div>
          <div className="text-gray-300">
            <span className="text-gray-500">Range:</span> <span className="text-radar-secondary">0-1.0</span>
          </div>
        </div>
      </div>
      
      {/* Scale indicator */}
      <div className="absolute top-6 right-6 bg-radar-surface/80 backdrop-blur-md rounded-lg p-3 border border-radar-grid/50 shadow-xl">
        <div className="text-xs font-mono space-y-2">
          <div className="text-gray-400 mb-2">SCALE</div>
          {[1, 0.75, 0.5, 0.25].map((scale) => (
            <div key={scale} className="flex items-center gap-2 text-gray-300">
              <div className="w-8 h-px bg-radar-grid"></div>
              <span className="text-radar-secondary">{scale.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Radar;

