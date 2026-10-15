"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";

export default function NewRepositoryPage() {
  const router = useRouter();
  const [sourceType, setSourceType] = useState<"git_url" | "upload" | "local">("git_url");
  const [name, setName] = useState("");
  const [gitUrl, setGitUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (sourceType === "git_url") {
        await api.createRepository({ name, git_url: gitUrl });
      } else if (sourceType === "local") {
        await api.createRepository({ name, local_path: localPath });
      } else if (sourceType === "upload" && file) {
        const formData = new FormData();
        formData.append("name", name);
        formData.append("file", file);
        const res = await fetch("/api/v1/repositories/upload", {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Upload failed" }));
          throw new Error(err.detail || "Upload failed");
        }
      }
      setSuccess(true);
      setTimeout(() => router.push("/repositories"), 800);
    } catch (e: any) {
      setError(e.message || "Failed to create repository");
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="panel p-8 text-center">
        <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center mx-auto mb-4 text-3xl">✓</div>
        <h2 className="text-xl font-semibold">Repository created</h2>
        <p className="text-slate-400 mt-2">Redirecting...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Add repository</h1>
      <form onSubmit={handleSubmit} className="panel p-6 space-y-6">
        <div>
          <label className="block text-sm font-medium mb-2">Source type</label>
          <div className="flex gap-4">
            {["git_url", "upload", "local"].map(t => (
              <label key={t} className={`flex items-center gap-2 px-4 py-2 rounded-md border-2 cursor-pointer transition-colors ${
                sourceType === t
                  ? "border-emerald-500 bg-emerald-500/10 text-emerald-400"
                  : "border-[#1e2633] text-slate-300 hover:border-slate-500"
              }`}>
                <input type="radio" name="sourceType" value={t} checked={sourceType === t} onChange={() => setSourceType(t as any)} className="sr-only" />
                <span className="font-medium capitalize">{t.replace("_", " ")}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Repository name <span className="text-rose-400">*</span></label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="my-awesome-project"
            className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
            required
          />
        </div>

        {sourceType === "git_url" && (
          <div>
            <label className="block text-sm font-medium mb-2">GitHub HTTPS URL <span className="text-rose-400">*</span></label>
            <input
              type="url"
              value={gitUrl}
              onChange={e => setGitUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              required
            />
            <p className="text-xs text-slate-500 mt-1">Only HTTPS GitHub URLs are supported. No credentials, no private IPs.</p>
          </div>
        )}

        {sourceType === "local" && (
          <div>
            <label className="block text-sm font-medium mb-2">Local path <span className="text-rose-400">*</span></label>
            <input
              type="text"
              value={localPath}
              onChange={e => setLocalPath(e.target.value)}
              placeholder="/home/user/projects/my-repo"
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              required
            />
            <p className="text-xs text-slate-500 mt-1">Must be a local git repository with .git directory. Requires server config: allow_local_repos=true.</p>
          </div>
        )}

        {sourceType === "upload" && (
          <div>
            <label className="block text-sm font-medium mb-2">ZIP archive <span className="text-rose-400">*</span></label>
            <input
              type="file"
              accept=".zip"
              onChange={e => setFile(e.target.files?.[0] || null)}
              className="w-full px-4 py-2 rounded-md bg-[#0b0e14] border border-[#1e2633] text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              required
            />
            <p className="text-xs text-slate-500 mt-1">Upload a ZIP of the repository root. Max size: 50MB. Nested zips not supported.</p>
          </div>
        )}

        {error && (
          <div className="p-3 rounded-md bg-rose-500/15 border border-rose-500/30 text-rose-300 text-sm">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-4">
          <button type="button" onClick={() => router.back()} className="px-4 py-2 rounded-md border border-[#1e2633] text-slate-300 hover:bg-[#161b26]">Cancel</button>
          <button type="submit" disabled={loading} className="px-4 py-2 rounded-md bg-emerald-500 hover:bg-emerald-400 text-[#0b0e14] font-semibold disabled:opacity-50">
            {loading ? "Creating..." : "Create repository"}
          </button>
        </div>
      </form>
    </div>
  );
}