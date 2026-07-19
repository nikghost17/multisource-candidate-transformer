"use client";

import { createContext, useContext, useState, useCallback } from "react";

const DrawerContext = createContext();

export function DrawerProvider({ children }) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeCandidate, setActiveCandidate] = useState(null);

  const openDrawer = useCallback((candidate) => {
    setActiveCandidate(candidate);
    setIsOpen(true);
    document.body.style.overflow = "hidden";
  }, []);

  const closeDrawer = useCallback(() => {
    setIsOpen(false);
    setActiveCandidate(null);
    document.body.style.overflow = "";
  }, []);

  return (
    <DrawerContext.Provider
      value={{ isOpen, activeCandidate, openDrawer, closeDrawer }}
    >
      {children}
    </DrawerContext.Provider>
  );
}

export function useDrawer() {
  const ctx = useContext(DrawerContext);
  if (!ctx) throw new Error("useDrawer must be used within DrawerProvider");
  return ctx;
}
