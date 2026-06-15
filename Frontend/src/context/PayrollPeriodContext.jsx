import { createContext, useCallback, useContext, useState } from 'react';

const STORAGE_KEY = 'hrms.payroll.period';

const EMPTY = { selectedMonth: null, selectedYear: null, selectedRunId: null };

function readStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

function writeStorage(value) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(value)); } catch {}
}

const PayrollPeriodContext = createContext(null);

export function PayrollPeriodProvider({ children }) {
  const [period, setPeriodState] = useState(readStorage);

  const setPeriod = useCallback((update) => {
    setPeriodState(prev => {
      const next = { ...prev, ...update };
      writeStorage(next);
      return next;
    });
  }, []);

  const clearPeriod = useCallback(() => {
    setPeriodState(EMPTY);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  }, []);

  return (
    <PayrollPeriodContext.Provider value={{ ...period, setPeriod, clearPeriod }}>
      {children}
    </PayrollPeriodContext.Provider>
  );
}

export function usePayrollPeriod() {
  const ctx = useContext(PayrollPeriodContext);
  if (!ctx) throw new Error('usePayrollPeriod must be used inside PayrollPeriodProvider');
  return ctx;
}
