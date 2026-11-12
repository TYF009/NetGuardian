"use client";
import {useEffect, useState} from "react";

export default function ThemeControl() {
  const [theme, setTheme] = useState("system");
  useEffect(() => setTheme(document.documentElement.dataset.theme ?? 'system'), []);
  return <label className="ops-theme">Theme
    <select value={theme} onChange={event => {
      const next = event.target.value;
      setTheme(next);
      document.documentElement.dataset.theme = next;
    }}>
      <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
    </select>
  </label>;
}
