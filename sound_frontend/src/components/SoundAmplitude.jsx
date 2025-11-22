import React, { useRef, useEffect } from 'react';

const SoundAmplitude = ({ points = [], audioData = null }) => {
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const phaseRef = useRef(0); // For smooth waveform animation
  const lastSplRef = useRef(0); // For smooth transitions
  const pointsRef = useRef(points); // Store points in ref to avoid animation restarts
  const audioDataRef = useRef(audioData); // Store audio data in ref
  const audioSamplesRef = useRef([]); // Store processed audio samples
  const audioBufferRef = useRef([]); // Buffer to accumulate audio samples (10 seconds)
  const waveformDataRef = useRef([]); // Store waveform data for time-domain display
  const maxWaveformPoints = 2000; // Number of waveform points to display (for smooth 10-second visualization)
  const audioSampleRate = 16000; // 16kHz sample rate
  const bufferDurationSeconds = 10.0; // Buffer duration in seconds (10 seconds for smooth scrolling)
  const maxBufferSamples = audioSampleRate * bufferDurationSeconds; // 160,000 samples for 10 seconds

  // Update refs when props change
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);

  useEffect(() => {
    audioDataRef.current = audioData;
    
    // Process audio data when received - accumulate in buffer (1-2 seconds)
    if (audioData && Array.isArray(audioData) && audioData.length > 0) {
      // Audio is 1 channel, 16kHz, normalized float array (-1.0 to 1.0)
      // Each chunk is about 0.25 seconds (4,000 samples at 16kHz)
      
      // Append new audio data to buffer
      audioBufferRef.current = [...audioBufferRef.current, ...audioData];
      
      // Keep only the most recent 1.5 seconds of data (FIFO)
      if (audioBufferRef.current.length > maxBufferSamples) {
        const excess = audioBufferRef.current.length - maxBufferSamples;
        audioBufferRef.current = audioBufferRef.current.slice(excess);
      }
      
      // Downsample the buffered data for display
      const downsampleFactor = Math.max(1, Math.floor(audioBufferRef.current.length / maxWaveformPoints));
      const downsampled = [];
      
      for (let i = 0; i < audioBufferRef.current.length; i += downsampleFactor) {
        downsampled.push(audioBufferRef.current[i]);
      }
      
      audioSamplesRef.current = downsampled;
      
      const bufferDuration = (audioBufferRef.current.length / audioSampleRate).toFixed(3);
      console.log('[SoundAmplitude] Audio buffer updated:', audioData.length, 'new samples,', audioBufferRef.current.length, 'total samples (', bufferDuration, 's),', downsampled.length, 'display points');
    } else {
      // Clear buffer if no audio data
      audioBufferRef.current = [];
      audioSamplesRef.current = [];
    }
  }, [audioData]);

  // Animation loop (runs once on mount)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      console.log('[SoundAmplitude] Canvas not found');
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      console.log('[SoundAmplitude] Context not found');
      return;
    }

    console.log('[SoundAmplitude] Initializing canvas and animation');

    // Set canvas size
    const resizeCanvas = () => {
      const container = canvas.parentElement;
      if (container) {
        canvas.width = container.clientWidth;
        canvas.height = 120; // Increased height for better visibility
        console.log('[SoundAmplitude] Canvas resized:', canvas.width, 'x', canvas.height);
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    let frameCount = 0;
    const draw = () => {
      if (!canvas || !ctx) return;

      frameCount++;

      // Check if we have audio data in buffer (preferred) or points with SPL
      const hasAudioData = audioBufferRef.current && audioBufferRef.current.length > 0;
      const currentPoints = pointsRef.current || [];
      
      let avgSpl = 0;
      let hasRealData = false;
      let amplitude = 0;
      
      if (hasAudioData) {
        // Use audio data to calculate amplitude
        const audioSamples = audioSamplesRef.current || [];
        if (audioSamples.length > 0) {
          // Calculate average RMS across all samples for overall amplitude
          const avgRMS = audioSamples.reduce((a, b) => a + b, 0) / audioSamples.length;
          const maxRMS = Math.max(...audioSamples);
          
          // RMS is already the amplitude (0 to 1 for normalized audio)
          // Use max RMS for peak amplitude, average RMS for average amplitude
          const peakAmplitude = maxRMS;
          const avgAmplitude = avgRMS;
          
          // Convert RMS amplitude to visual height
          // RMS of 1.0 = maximum amplitude, scale to 40% of canvas height
          amplitude = peakAmplitude * (canvas.height * 0.4);
          
          // Calculate SPL from RMS amplitude
          // RMS represents the sound pressure level
          // Convert normalized RMS (0-1) to actual pressure
          // For normalized audio, RMS of 1.0 = full scale
          // We need to map this to a realistic SPL range
          const P_ref = 20e-6; // Reference pressure (20 μPa)
          
          // Map RMS to pressure range
          // RMS of 0.0 -> 30 dB (quiet), RMS of 1.0 -> 120 dB (very loud)
          // This is a linear mapping for visualization
          // In reality, you'd need calibration, but for display we use this approximation
          const minSpl = 30;
          const maxSpl = 120;
          const splRange = maxSpl - minSpl;
          
          // Map RMS (0-1) directly to SPL range (30-120 dB)
          avgSpl = minSpl + (avgAmplitude * splRange);
          avgSpl = Math.max(minSpl, Math.min(maxSpl, avgSpl)); // Clamp to range
          
          hasRealData = true;
          
          if (frameCount % 60 === 0) {
            console.log('[SoundAmplitude] Using audio data - RMS:', avgAmplitude.toFixed(4), 'Peak:', peakAmplitude.toFixed(4), 'Amplitude:', amplitude.toFixed(2), 'px, SPL:', avgSpl.toFixed(1), 'dB');
          }
        }
      } else if (currentPoints.length > 0) {
        // Fallback to SPL from points
        const splValues = currentPoints.map(p => p.spl_db || 0).filter(v => v > 0);
        if (splValues.length > 0) {
          avgSpl = splValues.reduce((a, b) => a + b, 0) / splValues.length;
          hasRealData = true;
          if (frameCount % 60 === 0) {
            console.log('[SoundAmplitude] Using points SPL - Points:', currentPoints.length, 'SPL values:', splValues, 'Average SPL:', avgSpl.toFixed(2));
          }
        }
      }
      
      // Smooth transition between values
      const smoothingFactor = 0.15;
      const targetSpl = avgSpl;
      lastSplRef.current = lastSplRef.current * (1 - smoothingFactor) + targetSpl * smoothingFactor;

      // Ensure canvas has valid dimensions
      if (canvas.width <= 0 || canvas.height <= 0) {
        console.warn('[SoundAmplitude] Invalid canvas dimensions:', canvas.width, canvas.height);
        animationFrameRef.current = requestAnimationFrame(draw);
        return;
      }

      // Graph dimensions with padding for axes
      const paddingLeft = 40;
      const paddingRight = 10;
      const paddingTop = 20;
      const paddingBottom = 25;
      const graphWidth = canvas.width - paddingLeft - paddingRight;
      const graphHeight = canvas.height - paddingTop - paddingBottom;
      const graphX = paddingLeft;
      const graphY = paddingTop;
      
      // Clear canvas with clean background
      ctx.fillStyle = 'rgba(5, 10, 20, 1)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw graph background
      ctx.fillStyle = 'rgba(10, 20, 40, 0.5)';
      ctx.fillRect(graphX, graphY, graphWidth, graphHeight);
      
      // Draw grid lines (horizontal - amplitude levels)
      ctx.strokeStyle = 'rgba(0, 217, 255, 0.08)';
      ctx.lineWidth = 0.5;
      const gridLines = 5;
      for (let i = 0; i <= gridLines; i++) {
        const y = graphY + (graphHeight / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(graphX, y);
        ctx.lineTo(graphX + graphWidth, y);
        ctx.stroke();
      }
      
      // Calculate time window based on buffered audio data
      // Audio is 16kHz, so each sample is 1/16000 seconds
      let timeWindowMs = 0;
      if (hasAudioData && audioBufferRef.current.length > 0) {
        const numSamples = audioBufferRef.current.length;
        timeWindowMs = (numSamples / audioSampleRate) * 1000; // Convert to milliseconds
      }
      
      // Draw vertical grid lines (time markers) with time labels
      const timeMarkers = 10; // More markers for finer time resolution
      for (let i = 0; i <= timeMarkers; i++) {
        const x = graphX + (graphWidth / timeMarkers) * i;
        ctx.beginPath();
        ctx.moveTo(x, graphY);
        ctx.lineTo(x, graphY + graphHeight);
        ctx.stroke();
        
        // Add time labels on x-axis (show every other marker to avoid crowding)
        if (timeWindowMs > 0 && i % 2 === 0) {
          const timeMs = (timeWindowMs / timeMarkers) * i;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillStyle = 'rgba(156, 163, 175, 0.6)';
          ctx.font = '8px monospace';
          ctx.fillText(`${timeMs.toFixed(1)}ms`, x, graphY + graphHeight + 2);
        }
      }
      
      // Draw axes
      ctx.strokeStyle = 'rgba(0, 217, 255, 0.3)';
      ctx.lineWidth = 1;
      
      // X-axis (bottom)
      ctx.beginPath();
      ctx.moveTo(graphX, graphY + graphHeight);
      ctx.lineTo(graphX + graphWidth, graphY + graphHeight);
      ctx.stroke();
      
      // Y-axis (left)
      ctx.beginPath();
      ctx.moveTo(graphX, graphY);
      ctx.lineTo(graphX, graphY + graphHeight);
      ctx.stroke();
      
      // Draw axis labels
      ctx.font = '9px monospace';
      ctx.fillStyle = 'rgba(156, 163, 175, 0.6)';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      
      // Use a much larger range so weak noises appear very small and strong sounds appear appropriately sized
      // Normalized audio samples are typically -1.0 to +1.0, but we use a much larger range
      // This ensures noise (typically 0.01-0.05) appears tiny, while real sounds (0.3-1.0) appear large
      const minAmplitude = -1.1;
      const maxAmplitude = 1.1;
      const amplitudeRange = maxAmplitude - minAmplitude;
      
      // Y-axis labels (amplitude) - dynamic range
      for (let i = 0; i <= gridLines; i++) {
        const value = maxAmplitude - (amplitudeRange / gridLines) * i;
        const y = graphY + (graphHeight / gridLines) * i;
        ctx.fillText(`${value.toFixed(2)}`, graphX - 8, y);
      }
      
      // X-axis label (only if no time labels shown)
      if (timeWindowMs === 0) {
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText('Time', graphX + graphWidth / 2, graphY + graphHeight + 8);
      }
      
      // Y-axis label
      ctx.save();
      ctx.translate(15, graphY + graphHeight / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillText('Amplitude', 0, 0);
      ctx.restore();
      
      // If using points SPL (not audio data), calculate amplitude from SPL
      if (!hasAudioData && hasRealData && lastSplRef.current > 0) {
        // Reference pressure: 20 micropascals (threshold of human hearing at 1 kHz)
        const P_ref = 20e-6; // 20 μPa
        
        // Calculate actual sound pressure from SPL
        const soundPressure = P_ref * Math.pow(10, lastSplRef.current / 20);
        
        // Convert sound pressure to visual amplitude
        // Scale it logarithmically for better visualization
        // Typical range: 30 dB (0.0006 Pa) to 120 dB (20 Pa)
        const minPressure = P_ref * Math.pow(10, 30 / 20); // 0.000632 Pa
        const maxPressure = P_ref * Math.pow(10, 120 / 20); // 20 Pa
        
        // Normalize to 0-1 range using logarithmic scale
        const normalizedAmplitude = Math.log10(soundPressure / minPressure) / Math.log10(maxPressure / minPressure);
        
        // Convert to pixel height (use 40% of canvas height as maximum)
        amplitude = Math.max(0, Math.min(1, normalizedAmplitude)) * (canvas.height * 0.4);
        
        if (frameCount % 60 === 0) {
          console.log('[SoundAmplitude] SPL:', lastSplRef.current.toFixed(1), 'dB, Pressure:', soundPressure.toFixed(6), 'Pa, Amplitude:', amplitude.toFixed(2), 'px');
        }
      }
      
      // Draw waveform if we have audio data
      if (hasAudioData && audioSamplesRef.current.length > 0) {
        const audioSamples = audioSamplesRef.current;
        
        // Use the same amplitude range calculated earlier for labels
        // This ensures the waveform matches the Y-axis labels
        const amplitudeRange = maxAmplitude - minAmplitude;
        const centerAmplitude = 0.0; // Center line at 0
        
        // Determine line color based on peak amplitude (strength of sound)
        const peakAmplitude = Math.max(...audioSamples.map(Math.abs));
        const avgAmplitude = audioSamples.reduce((a, b) => a + Math.abs(b), 0) / audioSamples.length;
        
        // Color based on peak amplitude relative to range
        const normalizedPeak = peakAmplitude / Math.max(1.0, maxAmplitude);
        let lineColor = 'rgba(0, 217, 255, 1)';
        if (normalizedPeak > 0.7) {
          lineColor = 'rgba(239, 68, 68, 1)'; // Strong sound - red
        } else if (normalizedPeak > 0.4) {
          lineColor = 'rgba(168, 85, 247, 1)'; // Medium sound - purple
        } else if (normalizedPeak > 0.1) {
          lineColor = 'rgba(0, 217, 255, 1)'; // Weak sound - cyan
        } else {
          lineColor = 'rgba(156, 163, 175, 0.6)'; // Very weak/noise - gray
        }
        
        // Draw waveform line
        ctx.beginPath();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = lineColor;
        
        for (let i = 0; i < audioSamples.length; i++) {
          const sample = audioSamples[i];
          // Clamp sample to valid range
          const clampedSample = Math.max(minAmplitude, Math.min(maxAmplitude, sample));
          
          // Calculate X position (time axis - left to right)
          const x = graphX + (graphWidth / audioSamples.length) * i;
          
          // Calculate Y position (amplitude axis)
          // Center (0.0) is at middle of graph
          // Positive values go up, negative values go down
          const normalizedValue = (clampedSample - minAmplitude) / amplitudeRange;
          const y = graphY + graphHeight - (normalizedValue * graphHeight);
          
          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        
        ctx.stroke();
        
        // Fill area under curve (above center line)
        ctx.beginPath();
        for (let i = 0; i < audioSamples.length; i++) {
          const sample = audioSamples[i];
          const clampedSample = Math.max(minAmplitude, Math.min(maxAmplitude, sample));
          const normalizedValue = (clampedSample - minAmplitude) / amplitudeRange;
          const x = graphX + (graphWidth / audioSamples.length) * i;
          const y = graphY + graphHeight - (normalizedValue * graphHeight);
          const centerY = graphY + graphHeight / 2;
          
          if (i === 0) {
            ctx.moveTo(x, centerY);
          }
          ctx.lineTo(x, y);
        }
        
        // Close the path
        const lastX = graphX + (graphWidth / audioSamples.length) * (audioSamples.length - 1);
        const centerY = graphY + graphHeight / 2;
        ctx.lineTo(lastX, centerY);
        ctx.closePath();
        
        // Fill with gradient
        const fillGradient = ctx.createLinearGradient(0, graphY, 0, graphY + graphHeight / 2);
        fillGradient.addColorStop(0, lineColor.replace('1)', '0.2)'));
        fillGradient.addColorStop(1, lineColor.replace('1)', '0.05)'));
        ctx.fillStyle = fillGradient;
        ctx.fill();
        
        // Draw center line (0 amplitude reference)
        ctx.strokeStyle = 'rgba(0, 217, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(graphX, graphY + graphHeight / 2);
        ctx.lineTo(graphX + graphWidth, graphY + graphHeight / 2);
        ctx.stroke();
      } else if (hasRealData && lastSplRef.current > 0) {
        // Fallback: show flat line if no audio data but have SPL
        const centerY = graphY + graphHeight / 2;
        ctx.strokeStyle = 'rgba(0, 217, 255, 0.5)';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(graphX, centerY);
        ctx.lineTo(graphX + graphWidth, centerY);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw current amplitude display (top-right, above graph)
      if (hasAudioData && audioSamplesRef.current.length > 0) {
        const audioSamples = audioSamplesRef.current;
        const maxAmplitude = Math.max(...audioSamples.map(Math.abs));
        const avgAmplitude = audioSamples.reduce((a, b) => a + Math.abs(b), 0) / audioSamples.length;
        
        // Determine color based on amplitude
        let accentColor = 'rgba(0, 217, 255, 1)';
        if (maxAmplitude > 0.7) {
          accentColor = 'rgba(239, 68, 68, 1)';
        } else if (maxAmplitude > 0.4) {
          accentColor = 'rgba(168, 85, 247, 1)';
        }
        
        // Current amplitude display
        ctx.font = 'bold 14px monospace';
        ctx.textAlign = 'right';
        ctx.fillStyle = accentColor;
        ctx.fillText(`Peak: ${maxAmplitude.toFixed(3)}`, canvas.width - 10, 12);
        
        ctx.font = '11px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.7)';
        ctx.fillText(`Avg: ${avgAmplitude.toFixed(3)}`, canvas.width - 10, 26);
      } else {
        // No signal indicator
        ctx.font = '11px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.4)';
        ctx.textAlign = 'center';
        ctx.fillText('NO SIGNAL', graphX + graphWidth / 2, graphY + graphHeight / 2);
      }

      animationFrameRef.current = requestAnimationFrame(draw);
    };

    console.log('[SoundAmplitude] Starting animation loop');
    draw();

    return () => {
      console.log('[SoundAmplitude] Cleaning up animation');
      window.removeEventListener('resize', resizeCanvas);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []); // Empty dependency - animation runs continuously

  return (
    <div className="w-full flex flex-col">
      {/* Compact Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-gradient-to-br from-radar-primary/20 to-radar-secondary/20 border border-radar-primary/30 flex items-center justify-center">
            <svg className="w-3 h-3 text-radar-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-200">
              Audio Waveform
            </h3>
            <p className="text-[10px] text-gray-500 font-mono">16kHz</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-1 bg-radar-surface/40 rounded border border-radar-grid/20">
          <div className="w-1 h-1 rounded-full bg-radar-primary animate-pulse"></div>
          <span className="text-[10px] text-gray-400 font-mono">LIVE</span>
        </div>
      </div>
      
      {/* Canvas Container */}
      <div className="relative rounded overflow-hidden border border-radar-grid/30 bg-gradient-to-b from-radar-surface/20 to-radar-surface/10">
        <canvas
          ref={canvasRef}
          className="w-full block"
          style={{
            height: '120px',
            display: 'block',
          }}
        />
      </div>
    </div>
  );
};

export default SoundAmplitude;

