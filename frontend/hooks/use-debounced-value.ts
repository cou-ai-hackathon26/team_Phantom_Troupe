"use client";

import { useEffect, useState } from "react";

/** The value, updated only after it stops changing for `ms` (search boxes: one request per pause, not per key). */
export function useDebouncedValue<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
