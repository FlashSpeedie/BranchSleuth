export default function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center justify-center px-8 py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400/20 to-cyan-500/20 border border-emerald-500/20 flex items-center justify-center mb-4 text-xl">
        🔍
      </div>
      <h3 className="text-slate-200 font-semibold mb-1.5">{title}</h3>
      <p className="text-sm text-slate-400 max-w-md mb-5">{body}</p>
      {action}
    </div>
  );
}
