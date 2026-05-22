import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@gravity-ui/uikit';
import '@gravity-ui/uikit/styles/fonts.css';
import '@gravity-ui/uikit/styles/styles.css';
import { ThemeContext, useThemeState } from './hooks/useThemeState';
import App from './App';

function Root({ children }: { children: React.ReactNode }) {
  const themeState = useThemeState();

  return (
    <ThemeContext.Provider value={themeState}>
      <ThemeProvider theme={themeState.resolved}>
        {children}
      </ThemeProvider>
    </ThemeContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Root>
  </React.StrictMode>,
);
