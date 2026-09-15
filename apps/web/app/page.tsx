'use client';

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {

  const [result, setResult] = useState<string>('loading...');

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then((d) => setResult(JSON.stringify(d, null, 2)))
      .catch((e) => setResult(`error: ${e.message}`));
  }, []);

  return (
    <main className="min-h-screen bg-neutral-950 p-8 font-mono text-neutral-200">
      <h1 className="text-xl font-semibold">Spatial Maintenance Copilot</h1>
      <p className="mt-1 text-sm text-neutral-500">perception service at {API}</p>
      <pre className="mt-6 rounded border border-neutral-800 bg-neutral-900 p-4 text-sm">
        {result}
      </pre>
    </main>
  );
}
