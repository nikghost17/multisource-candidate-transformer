"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCandidates } from "@/contexts/CandidateContext";

export default function Sidebar() {
  const pathname = usePathname();
  const { stats } = useCandidates();

  const navItems = [
    {
      href: "/",
      label: "Dashboard",
      icon: (
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path d="M3 4a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 12a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H4a1 1 0 01-1-1v-4zM11 4a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V4zM11 12a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
        </svg>
      ),
    },
    {
      href: "/upload",
      label: "Upload",
      icon: (
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z"
            clipRule="evenodd"
          />
        </svg>
      ),
    },
    {
      href: "/search",
      label: "Semantic Search",
      icon: (
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
            clipRule="evenodd"
          />
        </svg>
      ),
    },
  ];

  return (
    <aside className="sidebar" id="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">
          <svg viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" fill="url(#lg1)" />
            <path
              d="M10 16l4 4 8-8"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <defs>
              <linearGradient id="lg1" x1="0" y1="0" x2="32" y2="32">
                <stop offset="0%" stopColor="#818cf8" />
                <stop offset="100%" stopColor="#6366f1" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <span className="logo-text">CandidateIQ</span>
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`nav-link ${pathname === item.href ? "active" : ""}`}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>

      <div className="sidebar-stats" id="sidebar-stats">
        <div className="stat-item">
          <span className="stat-label">Total Candidates</span>
          <span className="stat-value">{stats.total || "—"}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">LLM Enriched</span>
          <span className="stat-value">{stats.enriched || "—"}</span>
        </div>
      </div>
    </aside>
  );
}
