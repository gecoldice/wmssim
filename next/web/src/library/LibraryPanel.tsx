import { copy } from "../copy";
import { catalog, groupLabels, type CatalogGroup } from "./catalog";

type Props = {
  dragging: string | null;
  query: string;
  filter: "all" | CatalogGroup;
  onQuery: (value: string) => void;
  onFilter: (value: "all" | CatalogGroup) => void;
  onLocked: (id: string) => void;
  onDragStart: (id: string, clientX: number, clientY: number) => void;
  onDragMove: (id: string, clientX: number, clientY: number) => void;
  onDragEnd: (id: string, clientX: number, clientY: number) => void;
};

export function LibraryPanel({ dragging, query, filter, onQuery, onFilter, onLocked, onDragStart, onDragMove, onDragEnd }: Props) {
  const q = query.trim().toLowerCase();
  return (
    <aside className="sidebar" id="libraryPanel">
      <div className="sidebar-head">
        <div className="section-title">元素库</div>
        <div className="section-sub">综合仓 · 米制占地</div>
      </div>
      <div className="search-wrap">
        <input
          aria-label="搜索设备"
          placeholder="搜索设备或 ID"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
        />
      </div>
      <div className="tabs">
        {(["all", "storage", "dock", "station", "structure"] as const).map((key) => (
          <button key={key} className={filter === key ? "active" : ""} type="button" onClick={() => onFilter(key)}>
            {key === "all" ? "全部" : groupLabels.find((row) => row[0] === key)?.[1].slice(0, 2)}
          </button>
        ))}
      </div>
      <div className="catalog">
        {groupLabels.map(([group, label]) => {
          const items = catalog.filter((item) => {
            if (item.group !== group) return false;
            if (filter !== "all" && filter !== group) return false;
            if (!q) return true;
            return `${item.name} ${item.id}`.toLowerCase().includes(q);
          });
          if (!items.length) return null;
          return (
            <div className="catalog-group" key={group}>
              <div className="catalog-label">{label}</div>
              {items.map((item) => {
                const preview = 26 / Math.max(item.lengthM, item.widthM);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`catalog-item${dragging === item.id ? " active" : ""}${item.placeable ? "" : " locked"}`}
                    title={item.placeable ? `${item.lengthM} × ${item.widthM} m` : copy.unsupportedType}
                    onPointerDown={(event) => {
                      if (!item.placeable) {
                        onLocked(item.id);
                        return;
                      }
                      event.currentTarget.setPointerCapture(event.pointerId);
                      onDragStart(item.id, event.clientX, event.clientY);
                    }}
                    onPointerMove={(event) => {
                      if (!item.placeable) return;
                      onDragMove(item.id, event.clientX, event.clientY);
                    }}
                    onPointerUp={(event) => {
                      if (!item.placeable) return;
                      onDragEnd(item.id, event.clientX, event.clientY);
                    }}
                  >
                    <span className={`catalog-icon${group === "station" ? " orange" : group === "dock" ? " blue" : ""}`}>
                      <i
                        className="foot-preview"
                        style={{ width: Math.max(6, item.lengthM * preview), height: Math.max(4, item.widthM * preview) }}
                      />
                    </span>
                    <span className="catalog-copy">
                      <span className="catalog-name">{item.name}</span>
                      <span className="catalog-id">
                        {item.id}
                        {item.placeable ? ` · ${item.lengthM}×${item.widthM} m` : " · 未启用"}
                      </span>
                    </span>
                    <span className="catalog-add">{item.placeable ? "拖" : ""}</span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="library-foot">{copy.libraryHint}</div>
    </aside>
  );
}
