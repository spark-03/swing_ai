import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('Dashboard Error Boundary caught:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    window.location.reload();
  };

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '100vh',
            background: '#0f172a',
            color: '#f8fafc',
            fontFamily: 'system-ui, sans-serif',
            padding: '32px',
          }}
        >
          <div
            style={{
              maxWidth: '500px',
              textAlign: 'center',
              background: '#1e293b',
              padding: '40px',
              borderRadius: '16px',
              border: '1px solid #334155',
            }}
          >
            <AlertTriangle size={48} style={{ color: '#f43f5e', marginBottom: '16px' }} />
            <h2 style={{ margin: '0 0 8px 0', color: '#f1f5f9' }}>Something went wrong</h2>
            <p style={{ margin: '0 0 24px 0', color: '#94a3b8', fontSize: '14px' }}>
              The dashboard encountered an unexpected error. This has been logged for investigation.
            </p>

            {this.state.error && (
              <div
                style={{
                  background: '#0f172a',
                  padding: '12px',
                  borderRadius: '8px',
                  marginBottom: '24px',
                  textAlign: 'left',
                  fontSize: '12px',
                  fontFamily: 'monospace',
                  color: '#f43f5e',
                  overflow: 'auto',
                  maxHeight: '120px',
                }}
              >
                {this.state.error.toString()}
              </div>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                onClick={this.handleRetry}
                style={{
                  background: '#1e293b',
                  border: '1px solid #475569',
                  color: '#fff',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '14px',
                }}
              >
                <RefreshCw size={16} /> Try Again
              </button>
              <button
                onClick={this.handleReload}
                style={{
                  background: '#38bdf8',
                  border: 'none',
                  color: '#0f172a',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                }}
              >
                Reload Page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;