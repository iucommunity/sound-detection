import React, { useRef, useEffect } from 'react';

const SoundAmplitude = ({ points = [], audioData = null }) => {
  const canvasRef = useRef(null);
  const animationFrameRef = useRef(null);
  const phaseRef = useRef(0); // For smooth waveform animation
  const lastSplRef = useRef(0); // For smooth transitions
  const pointsRef = useRef(points); // Store points in ref to avoid animation restarts
  const audioDataRef = useRef(audioData); // Store audio data in ref
  const audioSamplesRef = useRef([]); // Store processed audio samples

  // Update refs when props change
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);

  useEffect(() => {
    audioDataRef.current = audioData;
    
    // Process audio data when received
    if (audioData && Array.isArray(audioData) && audioData.length > 0) {
      // Audio is 1 channel, 16kHz, normalized float array (-1.0 to 1.0)
      // Calculate RMS (Root Mean Square) amplitude for each sample window
      const sampleRate = 16000; // 16kHz
      const windowSize = 160; // Process in windows of 160 samples (10ms at 16kHz)
      const samples = [];
      
      for (let i = 0; i < audioData.length; i += windowSize) {
        const window = audioData.slice(i, i + windowSize);
        if (window.length === 0) break;
        
        // Calculate RMS (Root Mean Square) - this gives us the amplitude
        const sumSquares = window.reduce((sum, val) => sum + val * val, 0);
        const rms = Math.sqrt(sumSquares / window.length);
        samples.push(rms);
      }
      
      audioSamplesRef.current = samples;
      console.log('[SoundAmplitude] Audio data processed:', audioData.length, 'samples ->', samples.length, 'windows');
      console.log('[SoundAmplitude] RMS range:', Math.min(...samples).toFixed(4), 'to', Math.max(...samples).toFixed(4));
    } else {
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
        canvas.height = 100;
        console.log('[SoundAmplitude] Canvas resized:', canvas.width, 'x', canvas.height);
      }
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    let frameCount = 0;
    const draw = () => {
      if (!canvas || !ctx) return;

      frameCount++;

      // Check if we have audio data (preferred) or points with SPL
      const hasAudioData = audioDataRef.current && audioDataRef.current.length > 0;
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
          // Assuming max RMS of 1.0 corresponds to 1 Pascal (94 dB SPL)
          const P_ref = 20e-6; // Reference pressure (20 μPa)
          const maxPressure = 1.0; // Maximum pressure for normalized audio (1 Pa = 94 dB)
          
          // Convert RMS to pressure
          const pressure = avgAmplitude * maxPressure;
          
          // Calculate SPL: SPL = 20 * log10(P / P_ref)
          if (pressure > 0) {
            avgSpl = 20 * Math.log10(pressure / P_ref);
            avgSpl = Math.max(0, Math.min(120, avgSpl)); // Clamp to reasonable range
          } else {
            avgSpl = 0;
          }
          
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

      // Clear canvas with fade effect for smooth animation
      ctx.fillStyle = 'rgba(10, 22, 40, 0.4)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Draw background gradient
      const bgGradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
      bgGradient.addColorStop(0, 'rgba(10, 20, 40, 0.95)');
      bgGradient.addColorStop(0.5, 'rgba(8, 15, 35, 0.98)');
      bgGradient.addColorStop(1, 'rgba(5, 10, 25, 0.99)');
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const centerY = canvas.height / 2;
      
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
      
      // Increment phase for smooth animation
      phaseRef.current += 0.15;
      
      // Calculate normalized SPL for color coding
      const minSpl = 30;
      const maxSpl = 120;
      const normalizedSpl = hasRealData && lastSplRef.current > 0 
        ? Math.max(0, Math.min(1, (lastSplRef.current - minSpl) / (maxSpl - minSpl)))
        : 0;
      
      // ALWAYS draw waveform if we have real data (audio or SPL)
      if (hasRealData && (lastSplRef.current > 0 || hasAudioData)) {
        // Ensure minimum visible amplitude (at least 5 pixels)
        const minVisibleAmplitude = 5;
        let displayAmplitude = Math.max(minVisibleAmplitude, amplitude);
        
        // Draw waveform from audio data if available, otherwise use calculated amplitude
        if (hasAudioData && audioSamplesRef.current.length > 0) {
          // Draw waveform directly from processed RMS audio samples
          const audioSamples = audioSamplesRef.current;
          const maxSample = Math.max(...audioSamples, 0.001);
          const avgSample = audioSamples.reduce((a, b) => a + b, 0) / audioSamples.length;
          
          const layers = [
            { alpha: 0.8, thickness: 2.5 },
            { alpha: 0.5, thickness: 2.0 },
            { alpha: 0.3, thickness: 1.5 },
          ];
          
          layers.forEach((layer, layerIndex) => {
            ctx.beginPath();
            ctx.lineWidth = layer.thickness;
            
            // Determine color based on average amplitude
            const normalizedAvg = avgSample / maxSample;
            let primaryColor, secondaryColor;
            
            if (normalizedAvg > 0.7) {
              primaryColor = { r: 239, g: 68, b: 68 };
              secondaryColor = { r: 249, g: 115, b: 22 };
            } else if (normalizedAvg > 0.4) {
              primaryColor = { r: 147, g: 51, b: 234 };
              secondaryColor = { r: 168, g: 85, b: 247 };
            } else {
              primaryColor = { r: 0, g: 217, b: 255 };
              secondaryColor = { r: 56, g: 189, b: 248 };
            }
            
            const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
            gradient.addColorStop(0, `rgba(${primaryColor.r}, ${primaryColor.g}, ${primaryColor.b}, ${layer.alpha})`);
            gradient.addColorStop(0.5, `rgba(${secondaryColor.r}, ${secondaryColor.g}, ${secondaryColor.b}, ${layer.alpha})`);
            gradient.addColorStop(1, `rgba(${primaryColor.r}, ${primaryColor.g}, ${primaryColor.b}, ${layer.alpha})`);
            ctx.strokeStyle = gradient;
            
            // Draw waveform from actual RMS audio samples
            // Each sample represents RMS amplitude in a time window
            for (let x = 0; x < canvas.width; x += 1) {
              const sampleIndex = Math.floor((x / canvas.width) * audioSamples.length);
              const actualIndex = Math.min(sampleIndex, audioSamples.length - 1);
              
              const rmsSample = audioSamples[actualIndex] || 0;
              const normalizedSample = rmsSample / maxSample;
              
              // Convert RMS to visual amplitude
              // RMS already represents amplitude, so use it directly
              const sampleAmplitude = normalizedSample * (canvas.height * 0.4) * (1 - layerIndex * 0.3);
              
              // Draw both positive and negative (mirror) for symmetric waveform
              const y = centerY - sampleAmplitude;
              
              if (x === 0) {
                ctx.moveTo(x, y);
              } else {
                ctx.lineTo(x, y);
              }
            }
            
            // Draw mirrored bottom half
            for (let x = canvas.width - 1; x >= 0; x -= 1) {
              const sampleIndex = Math.floor((x / canvas.width) * audioSamples.length);
              const actualIndex = Math.min(sampleIndex, audioSamples.length - 1);
              
              const rmsSample = audioSamples[actualIndex] || 0;
              const normalizedSample = rmsSample / maxSample;
              const sampleAmplitude = normalizedSample * (canvas.height * 0.4) * (1 - layerIndex * 0.3);
              
              const y = centerY + sampleAmplitude;
              ctx.lineTo(x, y);
            }
            
            ctx.closePath();
            ctx.stroke();
            ctx.shadowBlur = 0;
          });
        } else {
          // Draw synthetic waveform from calculated amplitude (fallback)
          const layers = [
            { frequency: 1.0, alpha: 0.8, thickness: 2.5 },
            { frequency: 1.5, alpha: 0.5, thickness: 2.0 },
            { frequency: 2.0, alpha: 0.3, thickness: 1.5 },
          ];
          
          layers.forEach(layer => {
            ctx.beginPath();
            ctx.lineWidth = layer.thickness;
            
            let primaryColor, secondaryColor;
            if (normalizedSpl > 0.7) {
              primaryColor = { r: 239, g: 68, b: 68 };
              secondaryColor = { r: 249, g: 115, b: 22 };
            } else if (normalizedSpl > 0.4) {
              primaryColor = { r: 147, g: 51, b: 234 };
              secondaryColor = { r: 168, g: 85, b: 247 };
            } else {
              primaryColor = { r: 0, g: 217, b: 255 };
              secondaryColor = { r: 56, g: 189, b: 248 };
            }
            
            const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
            gradient.addColorStop(0, `rgba(${primaryColor.r}, ${primaryColor.g}, ${primaryColor.b}, ${layer.alpha})`);
            gradient.addColorStop(0.5, `rgba(${secondaryColor.r}, ${secondaryColor.g}, ${secondaryColor.b}, ${layer.alpha})`);
            gradient.addColorStop(1, `rgba(${primaryColor.r}, ${primaryColor.g}, ${primaryColor.b}, ${layer.alpha})`);
            ctx.strokeStyle = gradient;
            
            for (let x = 0; x < canvas.width; x += 2) {
              const progress = x / canvas.width;
              const wave1 = Math.sin((progress * 10 + phaseRef.current * 0.1) * layer.frequency) * displayAmplitude;
              const wave2 = Math.sin((progress * 20 + phaseRef.current * 0.2) * layer.frequency) * displayAmplitude * 0.3;
              const wave3 = Math.sin((progress * 30 + phaseRef.current * 0.15) * layer.frequency) * displayAmplitude * 0.15;
              const noise = (Math.random() - 0.5) * displayAmplitude * 0.1;
              const y = centerY + wave1 + wave2 + wave3 + noise;
              
              if (x === 0) {
                ctx.moveTo(x, y);
              } else {
                ctx.lineTo(x, y);
              }
            }
            
            ctx.stroke();
            ctx.shadowBlur = 0;
          });
        }
        
        // Debug: Log that we're drawing
        if (frameCount % 60 === 0) {
          console.log('[SoundAmplitude] DRAWING waveform - Audio:', hasAudioData, 'SPL:', lastSplRef.current.toFixed(1), 'dB, Amplitude:', displayAmplitude.toFixed(2), 'px');
        }
        
      } else {
        // Draw flat line when no data
        ctx.strokeStyle = 'rgba(0, 217, 255, 0.3)';
        ctx.lineWidth = 2;
        ctx.setLineDash([10, 5]);
        ctx.beginPath();
        ctx.moveTo(0, centerY);
        ctx.lineTo(canvas.width, centerY);
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Add "No Signal" text
        ctx.font = '12px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.5)';
        ctx.textAlign = 'center';
        ctx.fillText('NO SIGNAL', canvas.width / 2, centerY - 15);
        
        ctx.font = '10px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.4)';
        ctx.fillText('Waiting for SPL data...', canvas.width / 2, centerY + 5);
      }
      
      // Draw center reference line
      ctx.strokeStyle = 'rgba(0, 217, 255, 0.15)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, centerY);
      ctx.lineTo(canvas.width, centerY);
      ctx.stroke();

      // Draw current SPL value and amplitude
      if (hasRealData && lastSplRef.current > 0) {
        ctx.font = 'bold 20px monospace';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'top';
        
        // Determine color based on SPL level
        let textColor = 'rgba(0, 217, 255, 1)';
        if (lastSplRef.current > 90) {
          textColor = 'rgba(239, 68, 68, 1)';
        } else if (lastSplRef.current > 70) {
          textColor = 'rgba(168, 85, 247, 1)';
        }
        
        ctx.fillStyle = textColor;
        ctx.shadowBlur = 15;
        ctx.shadowColor = textColor;
        ctx.fillText(`${lastSplRef.current.toFixed(1)} dB`, canvas.width - 15, 10);
        ctx.shadowBlur = 0;

        // Draw SPL label
        ctx.font = '9px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.8)';
        ctx.fillText('SPL', canvas.width - 15, 35);
        
        // Calculate and display sound pressure
        const P_ref = 20e-6;
        const soundPressure = P_ref * Math.pow(10, lastSplRef.current / 20);
        
        // Draw sound pressure value
        ctx.font = 'bold 14px monospace';
        ctx.fillStyle = textColor;
        ctx.textAlign = 'left';
        
        let pressureText = '';
        if (soundPressure < 0.001) {
          pressureText = `${(soundPressure * 1e6).toFixed(1)} µPa`;
        } else if (soundPressure < 1) {
          pressureText = `${(soundPressure * 1000).toFixed(2)} mPa`;
        } else {
          pressureText = `${soundPressure.toFixed(3)} Pa`;
        }
        
        ctx.fillText(pressureText, 15, 10);
        ctx.font = '8px monospace';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.8)';
        ctx.fillText('PRESSURE', 15, 30);
      }

      // Draw reference markers (only when data is present)
      if (hasRealData) {
        ctx.font = '8px monospace';
        ctx.textAlign = 'left';
        ctx.fillStyle = 'rgba(156, 163, 175, 0.4)';
        
        // Top marker
        ctx.fillText('+', 8, 15);
        // Bottom marker  
        ctx.fillText('-', 8, canvas.height - 8);
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
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-radar-primary/20 to-radar-secondary/20 border border-radar-primary/30 flex items-center justify-center">
            <svg className="w-5 h-5 text-radar-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold text-transparent bg-clip-text bg-gradient-to-r from-radar-primary to-radar-secondary">
              Sound Amplitude
            </h3>
            <p className="text-xs text-gray-500">Real-time SPL Monitor</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-radar-surface/50 rounded-lg border border-radar-grid/30">
          <div className="w-2 h-2 rounded-full bg-radar-primary animate-pulse"></div>
          <span className="text-xs text-gray-400 font-mono">LIVE</span>
        </div>
      </div>
      
      <canvas
        ref={canvasRef}
        className="rounded-xl shadow-lg w-full"
        style={{
          background: 'radial-gradient(circle at center, rgba(10, 20, 40, 0.95) 0%, rgba(8, 15, 35, 0.98) 40%, rgba(5, 10, 25, 0.99) 70%, rgba(3, 5, 15, 1) 100%)',
          border: '2px solid rgba(0, 217, 255, 0.3)',
          boxShadow: '0 0 40px rgba(0, 217, 255, 0.08), inset 0 0 40px rgba(124, 58, 237, 0.05)',
          height: '100px',
          display: 'block',
        }}
      />
    </div>
  );
};

export default SoundAmplitude;

