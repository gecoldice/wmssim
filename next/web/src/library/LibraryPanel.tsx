import { copy } from "../copy";
import { catalog, groupLabels, type CatalogGroup } from "./catalog";

type Props = {
  pending: string | null;
  query: string;
  filter: "all" | CatalogGroup;
  onQuery: (value: string) => void;
  onFilter: (value: "all" | CatalogGroup) => void;
  onPick: (id: string, placeable: boolean) => void;
};

export function LibraryPanel({ pending, query, filter, onQuery, onFilter, onPick }: Props) {
  const q = query.trim().toLowerCase();
  return (
    <aside className="sidebar" id="libraryPanel">
      <div className="sidebar-head">
        <div className="section-title">元素库</div>
        <div className="section-sub">综合仓 · 常用设施</div>
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
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`catalog-item${pending === item.id ? " active" : ""}`}
                  onClick={() => onPick(item.id, item.placeable)}
                  title={item.placeable ? item.id : copy.unsupportedType}
                >
                  <span className={`catalog-icon${group === "station" ? " orange" : group === "dock" ? " blue" : ""}`}>
                    {item.placeable ? "▣" : "·"}
                  </span>
                  <span className="catalog-copy">
                    <span className="catalog-name">{item.name}</span>
                    <span className="catalog-id">
                      {item.id}
                      {item.placeable ? "" : " · 未启用"}
                    </span>
                  </span>
                  <span className="catalog-add">{item.placeable ? "+" : ""}</span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
      <div className="library-foot">点击元素，再点击画布放置</div>
    </aside>
  );
}
