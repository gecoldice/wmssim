type Props = {
  busy: boolean;
  canDelete: boolean;
  runLabel: string;
  onPrepare: () => void;
  onDelete: () => void;
  onRun: () => void;
};

export function PreparePanel({ busy, canDelete, runLabel, onPrepare, onDelete, onRun }: Props) {
  return (
    <div className="panel-actions">
      <div className="secondary-actions">
        <button className="ghost-btn" type="button" disabled={busy} onClick={onPrepare}>
          准备
        </button>
        <button className="ghost-btn" type="button" disabled={!canDelete || busy} onClick={onDelete}>
          删除所选
        </button>
      </div>
      <button className="run-btn" type="button" disabled={busy} onClick={onRun}>
        <span>{runLabel}</span>
      </button>
    </div>
  );
}
