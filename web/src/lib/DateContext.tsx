import { createContext, useContext, useState } from "react";

interface DateCtx {
  asOf: string | null;
  setAsOf: (d: string | null) => void;
}

const Ctx = createContext<DateCtx>({ asOf: null, setAsOf: () => {} });

export function DateProvider({ children }: { children: React.ReactNode }) {
  const [asOf, setAsOf] = useState<string | null>(null);
  return <Ctx.Provider value={{ asOf, setAsOf }}>{children}</Ctx.Provider>;
}

export function useDate() {
  return useContext(Ctx);
}
