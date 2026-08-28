import React, { useEffect, useState } from 'react';

const LoadingBar = () => {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setProgress((prevProgress) => {
        if (prevProgress >= 90) {
          clearInterval(timer);
          return 90;
        }
        return prevProgress + 10;
      });
    }, 100);

    return () => {
      clearInterval(timer);
      setProgress(100);
    };
  }, []);

  return (
    <div className="fixed top-0 left-0 w-full h-1 z-[9999]">
      <div 
        className="h-full bg-gradient-to-r from-blue-500 to-indigo-600 transition-all duration-300 ease-out shadow-[0_0_10px_rgba(59,130,246,0.5)]"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
};

export default LoadingBar;
