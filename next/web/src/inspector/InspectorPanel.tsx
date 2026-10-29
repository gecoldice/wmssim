import { copy } from "../copy";
import type { Draft, PoseEl, ScenarioFields } from "../workbench/draft";
import { parseNum } from "../workbench/draft";

type Check = { status?: string; message?: string; objectIds?: string[]; ruleId?: string };

type Props = {
  draft: Draft;
  onDraft: (patch: Partial<Draft>) => void;
  selected: PoseEl | null;
  onElement: (patch: Partial<PoseEl>) => void;
  fields: ScenarioFields;
  onField: (patch: Partial<ScenarioFields>) => void;
  onTestValues: () => void;
  testValues: boolean;
  checks: Check[];
  prepareReady: boolean | null;
  onRecheck: () => void;
};

export function InspectorPanel({
  draft,
  onDraft,
  selected,
  onElement,
  fields,
  onField,
  onTestValues,
  testValues,
  checks,
  prepareReady,
  onRecheck,
}: Props) {
  const fails = checks.filter((check) => check.status === "fail");
  return (
    <>
      <div className="inspector-head">
        <div className="section-title">参数与校核</div>
        <div className="section-sub">{selected ? `${selected.typeElementId} · ${selected.instanceId}` : "当前未选中设备"}</div>
      </div>
      <div className="inspector-scroll" id="inspectorScroll">
        <section className="panel-section">
          <div className="panel-row">
            <h3>场地</h3>
            <span className="mini-tag">米</span>
          </div>
          <div className="two-fields">
            <NumberField label="场地宽" unit="m" value={draft.widthM} placeholder={copy.missing} onChange={(value) => onDraft({ widthM: value })} />
            <NumberField label="场地高" unit="m" value={draft.heightM} placeholder={copy.missing} onChange={(value) => onDraft({ heightM: value })} />
          </div>
          <div className="two-fields">
            <NumberField label="通道宽" unit="m" value={draft.aisleWidthM} placeholder={copy.missing} onChange={(value) => onDraft({ aisleWidthM: value })} />
            <NumberField label="通道 Y" unit="m" value={draft.aisleY} placeholder={copy.missing} onChange={(value) => onDraft({ aisleY: value })} />
          </div>
          <div className="two-fields">
            <NumberField label="通道起点 X" unit="m" value={draft.aisleFromX} placeholder={copy.missing} onChange={(value) => onDraft({ aisleFromX: value })} />
            <NumberField label="通道终点 X" unit="m" value={draft.aisleToX} placeholder={copy.missing} onChange={(value) => onDraft({ aisleToX: value })} />
          </div>
        </section>
        <section className="panel-section">
          <div className="panel-row">
            <h3>实例参数</h3>
            <span className="mini-tag">{selected?.typeElementId ?? "未选择"}</span>
          </div>
          {selected ? (
            <>
              <div className="field">
                <label>实例 ID</label>
                <div className="input-row">
                  <input value={selected.instanceId} readOnly />
                </div>
              </div>
              <div className="two-fields">
                <NumberField label="东向 X" unit="m" value={String(selected.x)} onChange={(value) => onElement({ x: parseNum(value) ?? selected.x })} />
                <NumberField label="北向 Y" unit="m" value={String(selected.y)} onChange={(value) => onElement({ y: parseNum(value) ?? selected.y })} />
              </div>
              <div className="two-fields">
                <NumberField label="长度" unit="m" value={String(selected.lengthM)} onChange={(value) => onElement({ lengthM: parseNum(value) ?? selected.lengthM })} />
                <NumberField label="宽度" unit="m" value={String(selected.widthM)} onChange={(value) => onElement({ widthM: parseNum(value) ?? selected.widthM })} />
              </div>
              <div className="two-fields">
                <NumberField label="高度" unit="m" value={String(selected.heightM)} onChange={(value) => onElement({ heightM: parseNum(value) ?? selected.heightM })} />
                <NumberField
                  label="朝向"
                  unit="°"
                  value={String(selected.yawDeg)}
                  onChange={(value) => onElement({ yawDeg: parseNum(value) ?? selected.yawDeg })}
                />
              </div>
              {selected.typeElementId === "ST-PAL-01" ? (
                <div className="two-fields">
                  <NumberField
                    label="列数"
                    unit="列"
                    value={String(selected.bays ?? 1)}
                    onChange={(value) => {
                      const bays = parseNum(value);
                      if (bays === null || bays < 1) return;
                      onElement({ bays, lengthM: 2.7 * bays });
                    }}
                  />
                  <NumberField
                    label="层数"
                    unit="层"
                    value={String(selected.levels ?? 1)}
                    onChange={(value) => {
                      const levels = parseNum(value);
                      if (levels === null || levels < 1) return;
                      onElement({ levels, heightM: 1.5 * levels });
                    }}
                  />
                </div>
              ) : null}
              <div className="field">
                <label>接入点</label>
                <div className="input-row">
                  <input value={selected.accessNodeId ?? "未绑定"} readOnly />
                </div>
              </div>
              <button className="text-link" type="button" onClick={() => onElement({ yawDeg: (selected.yawDeg + 90) % 360 })}>
                旋转 90°
              </button>
            </>
          ) : (
            <div className="inspector-empty">拖入或点选设备。占地由长度、宽度和朝向决定，单位是米。</div>
          )}
        </section>
        <section className="panel-section">
          <div className="panel-row">
            <h3>业务工况</h3>
            <span className="mini-tag">场景包</span>
          </div>
          <label className="toggle-line">
            <span>
              <input
                type="checkbox"
                checked={fields.fullPallet}
                onChange={(event) => onField({ fullPallet: event.target.checked })}
              />
              整托作业
            </span>
          </label>
          <label className="toggle-line">
            <span>
              <input
                type="checkbox"
                checked={fields.breakBulk}
                onChange={(event) => onField({ breakBulk: event.target.checked })}
              />
              拆托作业
            </span>
          </label>
          <label className="toggle-line">
            <span>
              <input
                type="checkbox"
                checked={fields.piecePick}
                onChange={(event) => onField({ piecePick: event.target.checked })}
              />
              小件分拣
            </span>
          </label>
          <div className="panel-row" style={{ marginTop: 14 }}>
            <h3>业务参数</h3>
          </div>
          <div className="two-fields">
            <NumberField label="日入量" unit="托/班" value={fields.inbound} placeholder={copy.missing} onChange={(value) => onField({ inbound: value })} />
            <NumberField label="日出量" unit="托/班" value={fields.outbound} placeholder={copy.missing} onChange={(value) => onField({ outbound: value })} />
          </div>
          <div className="two-fields">
            <NumberField label="电商单量" unit="单/班" value="" placeholder="本切片不使用" disabled onChange={() => undefined} />
            <NumberField label="高峰系数" unit="×" value="" placeholder="本切片不使用" disabled onChange={() => undefined} />
          </div>
          <NumberField
            label="班次窗"
            unit="小时"
            value={fields.shiftHours}
            placeholder={copy.missing}
            onChange={(value) => onField({ shiftHours: value })}
          />
          <button className="text-link" type="button" onClick={onTestValues}>
            {testValues ? "已载入测试工况" : "填入测试工况"}
          </button>
          {testValues ? <div className="constraint warn">{copy.testBanner}</div> : null}
          <div className="two-fields" style={{ marginTop: 11 }}>
            <NumberField label="叉车数量" unit="台" value={fields.forklifts} placeholder={copy.missing} onChange={(value) => onField({ forklifts: value })} />
            <NumberField label="拣货人数" unit="人" value={fields.pickers} placeholder={copy.missing} onChange={(value) => onField({ pickers: value })} />
          </div>
          <div className="two-fields">
            <NumberField label="空驶速度" unit="m/s" value={fields.emptySpeed} placeholder={copy.missing} onChange={(value) => onField({ emptySpeed: value })} />
            <NumberField label="载货速度" unit="m/s" value={fields.travel} placeholder={copy.missing} onChange={(value) => onField({ travel: value })} />
          </div>
          <div className="two-fields">
            <NumberField label="取货时间" unit="秒" value={fields.pickSec} placeholder={copy.missing} onChange={(value) => onField({ pickSec: value })} />
            <NumberField label="发运时间" unit="秒" value={fields.shipSec} placeholder={copy.missing} onChange={(value) => onField({ shipSec: value })} />
          </div>
          <NumberField
            label="到达窗口"
            unit="秒"
            value={fields.windowSec}
            placeholder={copy.missing}
            onChange={(value) => onField({ windowSec: value })}
          />
        </section>
        <section className="panel-section">
          <div className="panel-row">
            <h3>约束与规范</h3>
            <span className={`mini-tag${prepareReady === false ? " amber" : ""}`}>
              {prepareReady === null ? "未准备" : prepareReady ? "已通过" : "未通过"}
            </span>
          </div>
          {fails.length === 0 ? (
            <div className="constraint">
              <span>
                <strong>{prepareReady ? "当前准备已通过" : "尚未做权威校验"}</strong>
                碰撞、窄通道和跨墙由准备任务判定。
              </span>
            </div>
          ) : (
            fails.map((check, index) => (
              <div className="constraint error" key={index}>
                <span>
                  <strong>{check.ruleId}</strong>
                  {check.message} {(check.objectIds ?? []).join("、")}
                </span>
              </div>
            ))
          )}
          <button className="text-link" type="button" onClick={onRecheck}>
            重新校核
          </button>
        </section>
      </div>
    </>
  );
}

function NumberField({
  label,
  unit,
  value,
  placeholder,
  disabled,
  onChange,
}: {
  label: string;
  unit: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="field">
      <label>
        {label}
        {value.trim() === "" && !disabled ? <small>{copy.missing}</small> : null}
      </label>
      <div className="input-row">
        <input
          type={disabled ? "text" : "number"}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        <em>{unit}</em>
      </div>
    </div>
  );
}

export function poseText(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "";
  return String(value);
}

export function poseNumber(raw: string): number | null {
  return parseNum(raw);
}
