import { useState } from "react";
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

const FILTERS = ["all", ...groupLabels.map((row) => row[0])] as const;

export function LibraryPanel({ dragging, query, filter, onQuery, onFilter, onLocked, onDragStart, onDragMove, onDragEnd }: Props) {
  const [openGroups, setOpenGroups] = useState<Record<CatalogGroup, boolean>>({
    IN: true,
    ST: true,
    PK: true,
    CV: true,
    MH: true,
    OUT: true,
    AUX: true,
  });
  const q = query.trim().toLowerCase();
  const groups = groupLabels.map(([group, label]) => ({
    group,
    label,
    items: catalog.filter((item) => {
      if (item.group !== group) return false;
      if (filter !== "all" && filter !== group) return false;
      if (!q) return true;
      return `${item.name} ${item.id}`.toLowerCase().includes(q);
    }),
  }));
  const visible = groups.filter((group) => group.items.length > 0);

  return (
    <aside className="sidebar" id="libraryPanel">
      <div className="sidebar-head">
        <div className="section-title">元素库</div>
        <div className="section-sub">综合仓 · 78 个正式类型</div>
      </div>
      <div className="search-wrap">
        <input
          aria-label="搜索设备"
          placeholder="搜索设备或 ID"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
        />
      </div>
      <div className="tabs" aria-label="元素库分类">
        {FILTERS.map((key) => {
          const label = key === "all" ? "全部" : groupLabels.find((row) => row[0] === key)?.[1];
          return (
            <button
              key={key}
              className={filter === key ? "active" : ""}
              type="button"
              data-catalog-filter={key}
              data-catalog-label={label}
              aria-pressed={filter === key}
              onClick={() => onFilter(key)}
            >
              {label}
            </button>
          );
        })}
      </div>
      <div className="catalog" id="catalogList">
        {visible.length ? (
          visible.map(({ group, label, items }) => (
            <details
              className="catalog-group"
              key={group}
              data-catalog-group={group}
              data-catalog-label={label}
              open={openGroups[group]}
              onToggle={(event) => {
                const open = event.currentTarget.open;
                setOpenGroups((current) => (current[group] === open ? current : { ...current, [group]: open }));
              }}
            >
              <summary className="catalog-label">
                <span>{label}</span>
                <span className="catalog-count">{items.length}</span>
              </summary>
              {items.map((item) => {
                const preview = 26 / Math.max(item.lengthM, item.widthM);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`catalog-item${dragging === item.id ? " active" : ""}${item.placeable ? "" : " locked"}`}
                    data-element-id={item.id}
                    data-placeable={item.placeable ? "true" : "false"}
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
                    <span className={`catalog-icon${group === "PK" || group === "OUT" ? " orange" : group === "IN" ? " blue" : ""}`}>
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
            </details>
          ))
        ) : (
          <p className="catalog-empty" role="status">
            {copy.noCatalogMatch}
          </p>
        )}
      </div>
      <div className="library-foot">{copy.libraryHint}</div>
    </aside>
  );
}
