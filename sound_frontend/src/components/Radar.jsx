import React, { useRef, useEffect, useMemo } from 'react';
import { polarToCartesian } from '../data/radarPoints';
import { CLASS_LIST, getClassColor } from '../data/classColors';

const Radar = ({ points = [], isRunning = true, classColors = {} }) => {
  // REMOVED: classColorMap and legendColorMap - we don't need them anymore
  // All colors come directly from getClassColor() which is the single source of truth

  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const sweepProgressRef = useRef(0);
  const containerRef = useRef(null);
  const sweepHistoryRef = useRef([]);
  const ripplesRef = useRef([]);
  const lastDropTimeRef = useRef(0);
  const pointsRef = useRef(points); // Store points in ref so animation can access them
  const isRunningRef = useRef(isRunning); // Store isRunning in ref for animation loop
  const drawFunctionRef = useRef(null); // Store draw function so it can be restarted
  const staticFrameIntervalRef = useRef(null); // Store interval for static frame redraw when paused

  // Update points ref whenever points change
  useEffect(() => {
    pointsRef.current = points;
    
    // If paused, redraw static frame when points change to keep radar visible
    if (!isRunning && drawFunctionRef.current) {
      drawFunctionRef.current(true);
    }
  }, [points, isRunning]);

  // Update isRunning ref whenever isRunning changes
  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  // Initialize and resize canvas
  const initializeCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return false;

    const container = canvas.parentElement || containerRef.current;
    if (container) {
      const containerWidth = container.clientWidth || 600;
      const containerHeight = container.clientHeight || 600;
      // Reserve more space for labels (60px padding instead of 40px)
      const size = Math.max(400, Math.min(containerWidth, containerHeight) - 60);
      canvas.width = size;
      canvas.height = size;
      return true;
    }
    return false;
  };

  // Separate effect for animation loop - always runs regardless of points or WebSocket connection
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      // Retry if canvas not ready yet
      const retryTimeout = setTimeout(() => {
        const retryCanvas = canvasRef.current;
        if (retryCanvas) {
          // Force re-render by triggering a state update or re-initialization
          retryCanvas.width = retryCanvas.width || 600;
          retryCanvas.height = retryCanvas.height || 600;
        }
      }, 100);
      return () => clearTimeout(retryTimeout);
    }

    // Initialize canvas size - ensure it's always initialized
    const initCanvas = () => {
      // Force canvas to be visible
      canvas.style.display = 'block';
      canvas.style.visibility = 'visible';
      canvas.style.opacity = '1';
      
      if (!initializeCanvas()) {
        // Fallback if container not ready
        const size = 600;
        canvas.width = size;
        canvas.height = size;
      }
      
      // Ensure canvas has valid dimensions
      if (canvas.width <= 0 || canvas.height <= 0) {
        canvas.width = 600;
        canvas.height = 600;
      }
    };
    
    // Initialize immediately
    initCanvas();
    
    // Also initialize after delays to handle DevTools closing and other edge cases
    const initTimeout1 = setTimeout(initCanvas, 100);
    const initTimeout2 = setTimeout(initCanvas, 500);
    const initTimeout3 = setTimeout(initCanvas, 1000);
    
    // Periodic check to ensure canvas stays visible (every 2 seconds)
    const visibilityCheckInterval = setInterval(() => {
      if (canvas) {
        initCanvas();
      }
    }, 2000);

    let ctx = canvas.getContext('2d');
    // Don't return early - start animation even if context needs retry
    // The draw function will handle context reacquisition

    // Re-check canvas dimensions and context periodically
    const checkCanvas = () => {
      if (canvas.width <= 0 || canvas.height <= 0) {
        initCanvas();
        ctx = canvas.getContext('2d');
      }
      // Also check if context is lost (can happen when DevTools closes)
      if (!ctx || ctx.canvas !== canvas) {
        ctx = canvas.getContext('2d');
      }
    };

    const draw = (isStaticFrame = false) => {
      // Store draw function in ref for pause/resume
      drawFunctionRef.current = draw;
      
      try {
        // Always ensure canvas exists and is valid
        if (!canvas || !canvasRef.current) {
          if (isRunningRef.current && !isStaticFrame) {
            animationFrameRef.current = requestAnimationFrame(() => draw(false));
          }
          return;
        }
        
        // Re-check canvas before each draw to handle DevTools closing
        checkCanvas();
        
        if (!ctx) {
          ctx = canvas.getContext('2d');
          if (!ctx) {
            if (isRunningRef.current && !isStaticFrame) {
              animationFrameRef.current = requestAnimationFrame(() => draw(false));
            }
            return;
          }
        }

        // Ensure canvas has valid dimensions before drawing
        if (canvas.width <= 0 || canvas.height <= 0) {
          canvas.width = 600;
          canvas.height = 600;
        }
        
        // Force canvas to be visible on every frame
        canvas.style.display = 'block';
        canvas.style.visibility = 'visible';
        canvas.style.opacity = '1';

        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        // Reserve more space for labels (60px instead of 40px)
        const maxRadius = Math.max(50, Math.min(centerX, centerY) - 60);
        
        // Get current points from ref (always up-to-date, works even when WebSocket disconnected)
        const currentPoints = pointsRef.current || [];
        
        // Clear canvas with subtle fade effect - ALWAYS draw, even with no points or disconnected
      ctx.fillStyle = 'rgba(10, 22, 40, 0.95)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw background radial gradient with cool colors
      const bgGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, maxRadius
      );
      bgGradient.addColorStop(0, 'rgba(10, 20, 40, 0.4)');
      bgGradient.addColorStop(0.3, 'rgba(8, 15, 35, 0.5)');
      bgGradient.addColorStop(0.6, 'rgba(5, 10, 25, 0.7)');
      bgGradient.addColorStop(1, 'rgba(3, 5, 15, 0.9)');
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Distance ranges: 10m, 100m, 1000m, 10000m, 100000m
      const distanceRanges = [10, 100, 1000, 10000, 100000];
      const minDistance = 1; // Minimum distance to display (1m)
      const maxDistance = 100000; // Maximum distance (100km)
      
      // Use logarithmic scale for positioning
      const logMin = Math.log10(minDistance);
      const logMax = Math.log10(maxDistance);
      const logRange = logMax - logMin;
      
      // Draw concentric circles representing distance ranges
      distanceRanges.forEach((distance, i) => {
        // Calculate radius using logarithmic scale
        const logDistance = Math.log10(distance);
        const normalizedPos = (logDistance - logMin) / logRange;
        const radius = normalizedPos * maxRadius;
        const alpha = 0.4 - (i * 0.06);
        
        // Outer glow with cyan tint
        ctx.strokeStyle = `rgba(30, 58, 95, ${alpha})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Main circle with cool cyan color
        ctx.strokeStyle = `rgba(0, 217, 255, ${alpha + 0.15})`;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Draw distance label on the right side of each circle
        if (i < distanceRanges.length - 1) { // Don't label the outermost circle
          const labelX = centerX + radius + 8;
          const labelY = centerY + 10; // Move down by 10px
          ctx.fillStyle = `rgba(0, 217, 255, ${alpha + 0.3})`;
          ctx.font = '10px monospace';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          
          // Format distance label
          let label = '';
          if (distance < 1000) {
            label = `${distance}m`;
          } else if (distance < 1000000) {
            label = `${distance / 1000}km`;
          } else {
            label = `${distance / 1000000}Mm`;
          }
          ctx.fillText(label, labelX, labelY);
        }
      });
      
      // Label the outermost circle separately
      const outermostRadius = maxRadius;
      const labelX = centerX + outermostRadius + 8;
      const labelY = centerY + 10; // Move down by 10px
      ctx.fillStyle = 'rgba(0, 217, 255, 0.5)';
      ctx.font = '10px monospace';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText('100km', labelX, labelY);

      // Draw grid lines with richer colors (0° = North at top)
      for (let angle = 0; angle < 360; angle += 30) {
        // Convert: 0° = North (top), so subtract 90° and flip Y
        const rad = ((angle - 90) * Math.PI) / 180;
        const isCardinal = angle % 90 === 0;
        
        ctx.strokeStyle = isCardinal 
          ? 'rgba(0, 217, 255, 0.5)' 
          : 'rgba(30, 58, 95, 0.35)';
        ctx.lineWidth = isCardinal ? 2 : 1.2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + maxRadius * Math.cos(rad),
          centerY - maxRadius * Math.sin(rad) // Flip Y for canvas
        );
        ctx.stroke();
      }
      
      // Draw minor grid lines (every 15 degrees) with subtle color
      ctx.strokeStyle = 'rgba(30, 58, 95, 0.25)';
      ctx.lineWidth = 0.8;
      for (let angle = 0; angle < 360; angle += 15) {
        if (angle % 30 === 0) continue; // Skip major lines
        // Convert: 0° = North (top), so subtract 90° and flip Y
        const rad = ((angle - 90) * Math.PI) / 180;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(
          centerX + maxRadius * Math.cos(rad),
          centerY - maxRadius * Math.sin(rad) // Flip Y for canvas
        );
        ctx.stroke();
      }

      // Draw cardinal directions with vibrant glow
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      
      const directions = [
        { angle: 0, label: 'S', full: 'SOUTH', labelColor: 'rgba(0, 217, 255, 0.9)', fullColor: 'rgba(124, 58, 237, 0.8)' },
        { angle: 90, label: 'E', full: 'EAST', labelColor: 'rgba(0, 217, 255, 0.9)', fullColor: 'rgba(168, 85, 247, 0.8)' },
        { angle: 180, label: 'N', full: 'NORTH', labelColor: 'rgba(0, 217, 255, 0.9)', fullColor: 'rgba(124, 58, 237, 0.8)' },
        { angle: 270, label: 'W', full: 'WEST', labelColor: 'rgba(0, 217, 255, 0.9)', fullColor: 'rgba(139, 92, 246, 0.8)' },
      ];

      directions.forEach(({ angle, label, full, labelColor, fullColor }) => {
        // Convert angle: 0° = North (top), 90° = East (right), 180° = South (bottom), 270° = West (left)
        // Subtract 90° to align with canvas coordinates and flip Y
        const rad = ((angle - 90) * Math.PI) / 180;
        
        // Position labels closer to edge but within canvas bounds
        const labelOffset = 20;
        // Increase spacing for East and West (horizontal directions)
        const isHorizontal = angle === 90 || angle === 270;
        const fullLabelOffset = isHorizontal ? 45 : 35;
        const x = centerX + (maxRadius + labelOffset) * Math.cos(rad);
        const y = centerY - (maxRadius + labelOffset) * Math.sin(rad); // Flip Y for canvas coordinates
        
        // Enhanced glow effect for main label (single letter)
        ctx.shadowBlur = 15;
        ctx.shadowColor = labelColor.replace('0.9)', '0.6)');
        ctx.fillStyle = labelColor;
        ctx.font = 'bold 16px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, x, y);
        
        // Full label with different color - positioned further out
        ctx.shadowBlur = 8;
        ctx.shadowColor = fullColor.replace('0.8)', '0.5)');
        ctx.fillStyle = fullColor;
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const labelX = centerX + (maxRadius + fullLabelOffset) * Math.cos(rad);
        const labelY = centerY - (maxRadius + fullLabelOffset) * Math.sin(rad); // Flip Y for canvas coordinates
        
        // Ensure labels stay within canvas bounds
        const padding = 5;
        const clampedX = Math.max(padding, Math.min(canvas.width - padding, labelX));
        const clampedY = Math.max(padding, Math.min(canvas.height - padding, labelY));
        
        ctx.fillText(full, clampedX, clampedY);
        
        ctx.shadowBlur = 0;
      });

      // Get current time for all animation calculations
      const now = Date.now();
      
      // Water drop effect - create new ripple periodically (only when running)
      if (!isStaticFrame && isRunningRef.current) {
        const timeSinceLastDrop = now - lastDropTimeRef.current;
        // Safety check: don't create new ripples if too many exist
        if (timeSinceLastDrop > 2000 && ripplesRef.current.length < 3) {
          ripplesRef.current.push({
            radius: 0,
            opacity: 1,
            time: now,
            maxRadius: maxRadius,
            dropTime: now // Track when drop was created
          });
          lastDropTimeRef.current = now;
        }

        // Update water ripples - limit to prevent accumulation
        const MAX_RIPPLES = 3;
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
          .filter(ripple => ripple.opacity > 0.05 && ripple.radius < ripple.maxRadius * 1.1)
          .slice(-MAX_RIPPLES); // Keep only the most recent ripples
      }

      // Water drop effect removed - no blinking at center

      // Draw water ripples (like water drop on water) - expanding circles with vibrant colors
      ripplesRef.current.forEach((ripple) => {
        if (ripple.radius <= 20) return; // Don't draw until ripple is far enough from center to prevent blinking
        
        // Draw multiple concentric rings for each ripple to create wave effect
        for (let ring = 0; ring < 4; ring++) {
          const ringOffset = ring * 20;
          const ringRadius = Math.max(0, ripple.radius - ringOffset);
          if (ringRadius < 5) continue;
          
          const ringOpacity = ripple.opacity * (1 - ring * 0.25) * (1 - ringRadius / ripple.maxRadius * 0.5);
          const ringWidth = 2 + ring * 1.5;
          
          // Ensure inner radius is never negative
          const innerGradientRadius = Math.max(0, ringRadius - ringWidth);
          const outerGradientRadius = Math.max(innerGradientRadius + 1, ringRadius + ringWidth);
          
          // Create gradient for each ring with cool cyan-purple colors
          const ringGradient = ctx.createRadialGradient(
            centerX, centerY, innerGradientRadius,
            centerX, centerY, outerGradientRadius
          );
          ringGradient.addColorStop(0, `rgba(0, 217, 255, ${ringOpacity * 0.4})`);
          ringGradient.addColorStop(0.5, `rgba(124, 58, 237, ${ringOpacity * 0.7})`);
          ringGradient.addColorStop(1, `rgba(0, 240, 255, ${ringOpacity * 0.2})`);
          
          // Outer ring with gradient
          ctx.strokeStyle = ringGradient;
          ctx.lineWidth = ringWidth;
          ctx.shadowBlur = 8;
          ctx.shadowColor = `rgba(0, 217, 255, ${ringOpacity * 0.5})`;
          ctx.beginPath();
          ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
          ctx.stroke();
          ctx.shadowBlur = 0;
          
          // Bright inner edge
          if (ring === 0) {
            ctx.strokeStyle = `rgba(0, 217, 255, ${ringOpacity * 1.0})`;
            ctx.lineWidth = 2.5;
            ctx.shadowBlur = 10;
            ctx.shadowColor = `rgba(0, 217, 255, ${ringOpacity * 0.8})`;
            ctx.beginPath();
            ctx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.shadowBlur = 0;
          }
        }
      });

      // Update sweep history for trail effect - only when running
      if (!isStaticFrame && isRunningRef.current) {
        const MAX_SWEEPS = 1; // Only one sweep at a time to prevent blinking
        const currentSweep = sweepProgressRef.current * maxRadius;
        
        // Always ensure at least one sweep exists for continuous animation
        if (sweepHistoryRef.current.length === 0) {
          // Initialize sweep if none exists
          sweepHistoryRef.current.push({
            radius: currentSweep,
            opacity: 1,
            time: now
          });
        } else if (currentSweep - sweepHistoryRef.current[sweepHistoryRef.current.length - 1].radius > 5) {
          // Add new sweep when it moves far enough
          sweepHistoryRef.current.push({
            radius: currentSweep,
            opacity: 1,
            time: now
          });
        } else {
          // Update existing sweep to current position
          sweepHistoryRef.current[sweepHistoryRef.current.length - 1] = {
            radius: currentSweep,
            opacity: 1,
            time: now
          };
        }
        
        // Remove old sweeps and update opacity - smooth fade as extends
        sweepHistoryRef.current = sweepHistoryRef.current
          .map(sweep => {
            const progress = sweep.radius / maxRadius;
            // Smooth fade: gradual decrease
            const distanceFade = 1 - (progress * 0.3); // Fade to 70% at edge
            // Time-based fade for smooth disappearance
            const age = (now - sweep.time) / 1000; // age in seconds
            const timeFade = Math.max(0, 1 - (age * 0.3)); // Fade out over 3.3 seconds
            return {
              ...sweep,
              opacity: Math.min(distanceFade, timeFade) // Use the smaller value for gradual fade
            };
          })
          .filter(sweep => sweep.opacity > 0.05 && sweep.radius <= maxRadius) // Extend to edge
          .slice(-MAX_SWEEPS); // Only keep one sweep to prevent blinking
        
        // Ensure at least one sweep exists after filtering
        if (sweepHistoryRef.current.length === 0) {
          sweepHistoryRef.current.push({
            radius: currentSweep,
            opacity: 1,
            time: now
          });
        }
      }

      // Draw extending circle - natural radar sweep effect
      sweepHistoryRef.current.forEach((sweep, index) => {
        if (sweep.radius <= 15 || sweep.radius > maxRadius) return; // Don't draw near center to prevent blinking
        
        const progress = sweep.radius / maxRadius;
        
        // Wider trailing fade for more natural look
        const trailWidth = 50;
        const innerRadius = Math.max(0, Math.max(15, sweep.radius - trailWidth)); // Ensure never negative
        const outerRadius = Math.max(innerRadius + 1, sweep.radius); // Ensure outer > inner
        
        // Natural opacity curve - brighter near leading edge, fades behind
        const baseOpacity = sweep.opacity;
        const fadeProgress = (sweep.radius - innerRadius) / trailWidth; // 0 to 1 across trail width
        
        // Create natural radar sweep gradient - bright leading edge, smooth trailing fade
        // Ensure both radii are valid (non-negative and outer > inner)
        const gradient = ctx.createRadialGradient(
          centerX,
          centerY,
          innerRadius,
          centerX,
          centerY,
          outerRadius
        );
        
        // Reduced opacity for subtler effect
        const leadingEdgeOpacity = baseOpacity * 0.15; // Much lower opacity
        const midOpacity = baseOpacity * 0.1;
        const trailingOpacity = baseOpacity * 0.05;
        
        gradient.addColorStop(0, `rgba(0, 217, 255, ${trailingOpacity})`);
        gradient.addColorStop(0.6, `rgba(0, 217, 255, ${midOpacity})`);
        gradient.addColorStop(0.9, `rgba(0, 217, 255, ${leadingEdgeOpacity})`);
        gradient.addColorStop(1, `rgba(0, 217, 255, 0)`);

        // Draw the trailing fade
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(centerX, centerY, outerRadius, 0, Math.PI * 2);
        ctx.fill();

        // Subtle leading edge ring - reduced opacity
        const edgeOpacity = baseOpacity * 0.35; // Much lower opacity
        ctx.strokeStyle = `rgba(0, 217, 255, ${edgeOpacity})`;
        ctx.lineWidth = 2;
        ctx.shadowBlur = 6; // Reduced glow
        ctx.shadowColor = `rgba(0, 217, 255, ${edgeOpacity * 0.5})`;
        ctx.beginPath();
        ctx.arc(centerX, centerY, outerRadius, 0, Math.PI * 2);
        ctx.stroke();
        
        ctx.shadowBlur = 0;
      });

      // Draw radar points with enhanced visuals - use ref to get current points
      currentPoints.forEach((point) => {
        // Convert actual distance (in meters) to screen radius using logarithmic scale
        const actualDistance = Math.max(minDistance, Math.min(maxDistance, point.distance || minDistance));
        const logDistance = Math.log10(actualDistance);
        const normalizedPos = (logDistance - logMin) / logRange;
        const screenRadius = normalizedPos * maxRadius;
        
        // Use normalized radius (0-1) for polarToCartesian, then scale by screenRadius
        const { x, y } = polarToCartesian(point.direction, 1.0, screenRadius);
        const screenX = centerX + x;
        const screenY = centerY - y; // Flip Y axis for screen coordinates

        // Draw point with intensity-based size and color
        // Ensure baseSize is always positive and reasonable
        const baseSize = Math.max(3, Math.min(20, 5 + (point.intensity || 0.5) * 10));
        const alpha = Math.max(0.3, Math.min(1.0, 0.7 + (point.intensity || 0.5) * 0.3));
        const time = Date.now() / 1000;
        
        // Use getClassColor to ensure color matches class list and points history
        // This is the single source of truth for all colors - always use getClassColor, never point.color
        // This ensures colors are always up-to-date even if point.color is stale
        const pointColor = getClassColor(point.classLabel);
        // Convert hex color to RGB
        const hexToRgb = (hex) => {
          const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
          return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
          } : { r: 0, g: 217, b: 255 }; // Default cyan RGB fallback
        };
        const rgb = hexToRgb(pointColor);
        
        // Multiple pulse rings
        for (let i = 0; i < 3; i++) {
          const pulseOffset = (time * 2 + i * 0.5) % 2;
          const pulseSize = baseSize + pulseOffset * 15;
          const pulseAlpha = (1 - pulseOffset) * alpha * 0.2;
          
          if (pulseAlpha > 0) {
            ctx.strokeStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${pulseAlpha})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(screenX, screenY, pulseSize, 0, Math.PI * 2);
            ctx.stroke();
          }
        }

        // Outer glow with multiple layers - use point color
        const glowLayers = [
          { radius: baseSize * 3, alpha: alpha * 0.35 },
          { radius: baseSize * 2, alpha: alpha * 0.6 },
          { radius: baseSize * 1.5, alpha: alpha * 0.8 }
        ];
        
        glowLayers.forEach(({ radius, alpha: layerAlpha }) => {
          const pointGradient = ctx.createRadialGradient(
            screenX, screenY, 0,
            screenX, screenY, radius
          );
          pointGradient.addColorStop(0, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${layerAlpha})`);
          pointGradient.addColorStop(0.4, `rgba(${Math.min(255, rgb.r + 30)}, ${Math.min(255, rgb.g + 30)}, ${Math.min(255, rgb.b + 30)}, ${layerAlpha * 0.7})`);
          pointGradient.addColorStop(0.7, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${layerAlpha * 0.4})`);
          pointGradient.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0)`);

          ctx.fillStyle = pointGradient;
          ctx.shadowBlur = radius * 0.5;
          ctx.shadowColor = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${layerAlpha * 0.6})`;
          ctx.beginPath();
          ctx.arc(screenX, screenY, radius, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
        });

        // Main point core with point color gradient
        const coreGradient = ctx.createRadialGradient(
          screenX, screenY, 0,
          screenX, screenY, baseSize
        );
        coreGradient.addColorStop(0, `rgba(255, 255, 255, ${alpha})`);
        coreGradient.addColorStop(0.3, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`);
        coreGradient.addColorStop(0.7, `rgba(${Math.max(0, rgb.r - 30)}, ${Math.max(0, rgb.g - 30)}, ${Math.max(0, rgb.b - 30)}, ${alpha * 0.8})`);
        coreGradient.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha * 0.4})`);
        
        ctx.fillStyle = coreGradient;
        ctx.beginPath();
        ctx.arc(screenX, screenY, baseSize, 0, Math.PI * 2);
        ctx.fill();
        
        // Bright center dot
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        ctx.beginPath();
        ctx.arc(screenX, screenY, baseSize * 0.35, 0, Math.PI * 2);
        ctx.fill();
        
        // Direction line to center with point color
        ctx.strokeStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha * 0.25})`;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([6, 4]);
        ctx.shadowBlur = 3;
        ctx.shadowColor = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha * 0.3})`;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(screenX, screenY);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.shadowBlur = 0;
      });

      // Draw center point (completely static, no blinking)
      const centerSize = 3;
      ctx.fillStyle = '#00d9ff';
      ctx.beginPath();
      ctx.arc(centerX, centerY, centerSize, 0, Math.PI * 2);
      ctx.fill();
      
      // Center crosshair (static)
      ctx.strokeStyle = 'rgba(0, 217, 255, 0.4)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(centerX - 8, centerY);
      ctx.lineTo(centerX + 8, centerY);
      ctx.moveTo(centerX, centerY - 8);
      ctx.lineTo(centerX, centerY + 8);
      ctx.stroke();

      // Update sweep progress only if animation is running (not paused)
      if (!isStaticFrame && isRunningRef.current) {
        sweepProgressRef.current += 0.003; // Increased speed for faster extending
        if (sweepProgressRef.current > 1) {
          sweepProgressRef.current = 0;
          // Don't clear sweeps - keep one active sweep for continuous animation
          // Only reset if sweep history is empty to ensure it's always visible
          if (sweepHistoryRef.current.length === 0) {
            sweepHistoryRef.current.push({
              radius: 0,
              opacity: 1,
              time: now
            });
          }
          // Also clear old ripples periodically
          if (ripplesRef.current.length > 3) {
            ripplesRef.current = ripplesRef.current.slice(-3);
          }
        }
      }

        // Only continue animation if running and not a static frame
        if (isRunningRef.current && !isStaticFrame) {
          animationFrameRef.current = requestAnimationFrame(() => draw(false));
        }
      } catch (error) {
        // Log error but continue animation loop - don't let errors stop the radar
        console.error('Error in radar draw loop:', error);
        // Continue animation even if there's an error, but only if running and not static
        if (isRunningRef.current && !isStaticFrame) {
          animationFrameRef.current = requestAnimationFrame(() => draw(false));
        }
      }
    };

    // Start the animation loop if running
    if (isRunning) {
      draw();
      console.log('✓ Radar animation loop started');
    }

    return () => {
      clearTimeout(initTimeout1);
      clearTimeout(initTimeout2);
      clearTimeout(initTimeout3);
      clearInterval(visibilityCheckInterval);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      // Don't clear sweep history on unmount - keep it for continuous animation
      // Only clear ripples
      ripplesRef.current = [];
      lastDropTimeRef.current = 0;
    };
  }, []); // Empty dependency array - animation setup runs once

  // Separate effect to handle pause/resume
  useEffect(() => {
    if (!isRunning) {
      // Pause animation - cancel the loop
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      
      // Clear any existing static frame interval
      if (staticFrameIntervalRef.current) {
        clearInterval(staticFrameIntervalRef.current);
        staticFrameIntervalRef.current = null;
      }
      
      // Draw a static frame immediately
      if (drawFunctionRef.current) {
        drawFunctionRef.current(true);
      }
      
      // Set up periodic redraw to keep radar visible when paused
      // Redraw every 100ms to ensure radar stays visible even with WebSocket updates
      staticFrameIntervalRef.current = setInterval(() => {
        if (drawFunctionRef.current && !isRunningRef.current) {
          drawFunctionRef.current(true);
        }
      }, 100);
      
      console.log('⏸ Radar animation paused - radar remains visible with periodic redraw');
    } else {
      // Resume animation
      // Clear static frame interval
      if (staticFrameIntervalRef.current) {
        clearInterval(staticFrameIntervalRef.current);
        staticFrameIntervalRef.current = null;
      }
      
      // Restart the animation loop
      if (!animationFrameRef.current && drawFunctionRef.current) {
        console.log('✓ Radar animation resumed - restarting draw loop');
        drawFunctionRef.current(false);
      }
    }
    
    // Cleanup on unmount or when isRunning changes
    return () => {
      if (staticFrameIntervalRef.current) {
        clearInterval(staticFrameIntervalRef.current);
        staticFrameIntervalRef.current = null;
      }
    };
  }, [isRunning]);

  // Handle canvas resize - ensure canvas is always properly sized
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const resizeCanvas = () => {
      // Ensure canvas is initialized
      if (!initializeCanvas()) {
        canvas.width = 600;
        canvas.height = 600;
      }
      // Ensure valid dimensions
      if (canvas.width <= 0 || canvas.height <= 0) {
        canvas.width = 600;
        canvas.height = 600;
      }
    };

    // Initial resize with a small delay to ensure DOM is ready
    const timeoutId = setTimeout(resizeCanvas, 100);
    
    // Also resize after a longer delay to handle DevTools closing
    const delayedResizeId = setTimeout(resizeCanvas, 500);
    
    // Use ResizeObserver for better resize handling
    let resizeObserver;
    try {
      resizeObserver = new ResizeObserver(() => {
        resizeCanvas();
      });
      
      const container = canvas.parentElement || containerRef.current;
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
      clearTimeout(delayedResizeId);
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener('resize', resizeCanvas);
    };
  }, []);

  return (
    <div ref={containerRef} className="relative flex items-start justify-center w-full h-[750px]">
      {/* Outer glow effect */}
      <div className="absolute inset-0 flex items-start justify-center pointer-events-none">
        <div className="w-[750px] h-[750px] rounded-full bg-radar-primary/5 blur-3xl"></div>
      </div>
      
      <canvas
        ref={canvasRef}
        className="rounded-2xl shadow-2xl relative z-10"
        width={700}
        height={700}
        style={{
          background: 'radial-gradient(circle at center, rgba(10, 20, 40, 0.95) 0%, rgba(8, 15, 35, 0.98) 40%, rgba(5, 10, 25, 0.99) 70%, rgba(3, 5, 15, 1) 100%)',
          border: '2px solid rgba(0, 217, 255, 0.3)',
          boxShadow: '0 0 80px rgba(0, 217, 255, 0.12), inset 0 0 80px rgba(124, 58, 237, 0.05)',
          width: '700px',
          height: '700px',
          display: 'block',
        }}
      />
      
      {/* Distance Scale and Classes - aligned horizontally at same Y position */}
      <div className="absolute top-6 right-6 flex flex-col gap-3">
        {/* Scale indicator */}
        <div className="bg-radar-surface/80 backdrop-blur-md rounded-lg p-3 border border-radar-grid/50 shadow-xl">
          <div className="text-xs font-mono space-y-2">
            <div className="text-gray-400 mb-2">DISTANCE</div>
            {[100000, 10000, 1000, 100, 10].map((distance) => {
              const label = distance >= 1000 ? `${distance / 1000}km` : `${distance}m`;
              return (
                <div key={distance} className="flex items-center gap-2 text-gray-300">
                  <div className="w-8 h-px bg-radar-grid"></div>
                  <span className="text-radar-secondary">{label}</span>
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Class Legend - aligned with distance scale */}
        <div className="bg-radar-surface/80 backdrop-blur-md rounded-lg p-2.5 border border-radar-grid/50 shadow-xl">
          <div className="text-xs font-mono space-y-1">
            <div className="text-gray-400 mb-1.5 text-[10px]">CLASSES</div>
            {CLASS_LIST.map((classItem) => {
              // Use getClassColor as the single source of truth - same function used by radar points and points history
              // This ensures perfect matching across all three locations
              // Use getClassColor() instead of classItem.color to ensure it's always up-to-date
              const actualColor = getClassColor(classItem.name);
              
              return (
                <div key={classItem.name} className="flex items-center gap-2 text-gray-300">
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor: actualColor,
                      boxShadow: `0 0 6px ${actualColor}80`,
                    }}
                  />
                  <span className="text-[10px] text-gray-300 font-medium">{classItem.name}</span>
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Active Status Panel - moved below classes */}
        <div className="bg-radar-surface/80 backdrop-blur-md rounded-lg p-3 border border-radar-grid/50 shadow-xl">
          <div className="text-xs font-mono space-y-1">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-radar-primary"></div>
              <span className="text-radar-primary font-semibold">ACTIVE</span>
            </div>
            <div className="text-gray-300">
              <span className="text-gray-500">Points:</span> <span className="text-radar-secondary font-bold">{points.length}</span>
            </div>
            <div className="text-gray-300">
              <span className="text-gray-500">Range:</span> <span className="text-radar-secondary">1m-100km</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Radar;

