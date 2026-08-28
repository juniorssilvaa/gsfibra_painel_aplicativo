import { useState, useEffect } from 'react';

function readIsDarkTheme() {
  const stored = localStorage.getItem('theme');
  if (stored === 'light') return false;
  if (stored === 'dark') return true;
  return document.documentElement.classList.contains('dark');
}

export const useTheme = () => {
  const [isDarkTheme, setIsDarkTheme] = useState(readIsDarkTheme);

  useEffect(() => {
    const checkTheme = () => {
      setIsDarkTheme(readIsDarkTheme());
    };

    checkTheme();

    const observer = new MutationObserver(checkTheme);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    window.addEventListener('storage', checkTheme);
    window.addEventListener('niohub-theme-change', checkTheme);

    return () => {
      observer.disconnect();
      window.removeEventListener('storage', checkTheme);
      window.removeEventListener('niohub-theme-change', checkTheme);
    };
  }, []);

  return isDarkTheme;
};
