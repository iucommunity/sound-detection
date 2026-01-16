import React, { useEffect, useState, useRef } from 'react';

const Notification = ({ message, type = 'info', onClose, duration = 2000 }) => {
  const [isVisible, setIsVisible] = useState(true);
  const [isExiting, setIsExiting] = useState(false);
  const onCloseRef = useRef(onClose);

  // Update ref when onClose changes
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (duration > 0) {
      // Start fade-out animation slightly before closing
      const fadeOutTimer = setTimeout(() => {
        setIsExiting(true);
      }, duration - 300); // Start fade 300ms before close

      // Actually close after duration
      const closeTimer = setTimeout(() => {
        setIsVisible(false);
        if (onCloseRef.current) {
          onCloseRef.current();
        }
      }, duration);

      return () => {
        clearTimeout(fadeOutTimer);
        clearTimeout(closeTimer);
      };
    }
  }, [duration]); // Remove onClose from dependencies

  const handleClose = () => {
    setIsExiting(true);
    setTimeout(() => {
      setIsVisible(false);
      if (onCloseRef.current) {
        onCloseRef.current();
      }
    }, 300);
  };

  const getTypeStyles = () => {
    switch (type) {
      case 'success':
        return {
          bg: 'bg-radar-surface/95',
          border: 'border-radar-primary/50',
          accent: 'from-radar-primary/20 to-emerald-500/20',
          iconColor: 'text-radar-primary',
          icon: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ),
        };
      case 'error':
        return {
          bg: 'bg-radar-surface/95',
          border: 'border-red-500/50',
          accent: 'from-red-500/20 to-rose-500/20',
          iconColor: 'text-red-400',
          icon: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ),
        };
      case 'warning':
        return {
          bg: 'bg-radar-surface/95',
          border: 'border-radar-warning/50',
          accent: 'from-radar-warning/20 to-amber-500/20',
          iconColor: 'text-radar-warning',
          icon: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ),
        };
      default:
        return {
          bg: 'bg-radar-surface/95',
          border: 'border-radar-primary/50',
          accent: 'from-radar-primary/20 to-radar-secondary/20',
          iconColor: 'text-radar-primary',
          icon: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ),
        };
    }
  };

  if (!isVisible) return null;

  const styles = getTypeStyles();

  return (
    <div
      className={`${styles.bg} ${styles.border} border backdrop-blur-md rounded-xl shadow-2xl p-4 min-w-[320px] max-w-[400px] flex items-start gap-3 transition-all duration-300 ease-in-out ${
        isExiting ? 'opacity-0 translate-x-full scale-95' : 'opacity-100 translate-x-0 scale-100'
      }`}
      style={{
        animation: !isExiting ? 'slideInRight 0.3s ease-out' : undefined,
      }}
    >
      {/* Accent gradient background */}
      <div className={`absolute inset-0 bg-gradient-to-r ${styles.accent} rounded-xl opacity-30 -z-10`}></div>
      
      {/* Icon */}
      <div className={`flex-shrink-0 ${styles.iconColor} mt-0.5`}>
        {styles.icon}
      </div>
      
      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="text-white font-semibold text-sm mb-1">
          {type === 'success' ? 'Success' : type === 'error' ? 'Failed' : type === 'warning' ? 'Warning' : 'Info'}
        </div>
        <div className="text-gray-300 text-sm leading-relaxed">
          {message}
        </div>
      </div>
      
      {/* Close button */}
      <button
        onClick={handleClose}
        className="flex-shrink-0 text-gray-400 hover:text-white transition-colors p-1 hover:bg-radar-grid/30 rounded-lg"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      
      <style>{`
        @keyframes slideInRight {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
};

export default Notification;

