import { copy } from "../copy";
import { isLinearConveyor } from "../library/catalog";
import { SPEC_PACKS, type NormFinding, type NormPhase, type SpecPackId } from "../prepare/norms";
import type { Draft, PoseEl, ScenarioFields } from "../workbench/draft";
import { conveyorLinks, linearEndsLinked, parseNum } from "../workbench/draft";

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
  normPhase: NormPhase;
  normSummary: string;
  normNote: string;
  specOn: Record<SpecPackId, boolean>;
  findings: NormFinding[];
  onToggleSpec: (id: SpecPackId, checked: boolean) => void;
  onAudit: () => void;
  onFix: (finding: NormFinding) => void;
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
  normPhase,
  normSummary,
  normNote,
  specOn,
  findings,
  onToggleSpec,
  onAudit,
  onFix,
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
              {selected.typeElementId.startsWith("CV-") ? (
                <ConveyorFields draft={draft} selected={selected} onElement={onElement} />
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
          <details open>
            <summary className="panel-row fold-summary">
              <h3>约束与规范</h3>
              <span className={`mini-tag${normPhase === "fail" ? " red" : normPhase === "stale" || prepareReady === false ? " amber" : ""}`}>
                {normPhase === "fail" ? "硬冲突" : normPhase === "stale" ? "未校核" : prepareReady === null ? "未准备" : prepareReady ? "已通过" : "未通过"}
              </span>
            </summary>
            <p className="norm-summary">{normSummary}</p>
            <p className="norm-note">{normNote}</p>
            {SPEC_PACKS.map((pack) => (
              <label className="toggle-line" key={pack.id}>
                <span>
                  <input
                    type="checkbox"
                    data-pack={pack.id}
                    checked={specOn[pack.id]}
                    onChange={(event) => onToggleSpec(pack.id, event.target.checked)}
                  />
                  {pack.name}
                </span>
                <em className="pack-hint">{pack.hint}</em>
              </label>
            ))}
            <label className="toggle-line">
              <span>
                <input type="checkbox" disabled checked={false} aria-label="空槽" />
                空槽 · 可扩展规范包
              </span>
              <em className="pack-hint">未接入</em>
            </label>
            <button className="norm-btn" id="normAudit" type="button" onClick={onAudit}>
              按规范校核
            </button>
            {normPhase === "stale" ? (
              <div className="constraint warn">
                <span>
                  <strong>已选规范还没校核</strong>
                  不能推演。点「按规范校核」，或取消勾选回到仅几何硬约束。
                </span>
              </div>
            ) : null}
            {normPhase === "off" ? (
              <div className="constraint">
                <span>
                  <strong>未选，仅几何硬约束</strong>
                  碰撞、超区、通道净宽和压柱仍会拒绝放下。
                </span>
              </div>
            ) : null}
            {normPhase === "pass" ? (
              <div className="constraint">
                <span>
                  <strong>校核没有硬冲突</strong>
                  可以进入推演。几何准备仍要单独通过。
                </span>
              </div>
            ) : null}
            {findings.map((finding) => (
              <div className="constraint error" key={finding.id}>
                <span>
                  <strong>{finding.title}</strong>
                  {finding.message}
                  {finding.repair ? (
                    <button className="text-link" type="button" onClick={() => onFix(finding)}>
                      {finding.fixLabel}
                    </button>
                  ) : (
                    <em className="pack-hint">请手动挪开。</em>
                  )}
                </span>
              </div>
            ))}
            {fails.length === 0 ? (
              <div className="constraint">
                <span>
                  <strong>{prepareReady ? "当前准备已通过" : "尚未做权威校验"}</strong>
                  碰撞、窄通道和跨墙由准备任务判定。
                </span>
              </div>
            ) : (
              fails.map((check, index) => (
                <div className="constraint error" key={`prep-${index}`}>
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
          </details>
        </section>
      </div>
    </>
  );
}

function ConveyorFields({
  draft,
  selected,
  onElement,
}: {
  draft: Draft;
  selected: PoseEl;
  onElement: (patch: Partial<PoseEl>) => void;
}) {
  const linear = isLinearConveyor(selected.typeElementId);
  const linked = linear && linearEndsLinked(selected, conveyorLinks(draft.elements));
  const speed = selected.speedMpm === undefined ? 30 : selected.speedMpm;
  return (
    <>
      <div className="field" id="footprintLine">
        <label>脚印</label>
        <div className="input-row">
          <input
            readOnly
            value={`${selected.lengthM} × ${selected.widthM} m · ${selected.yawDeg}°`}
          />
        </div>
      </div>
      <NumberField
        label="速度"
        unit="m/min"
        inputId="speed_mpm"
        value={speed === null ? "" : String(speed)}
        placeholder={copy.missing}
        onChange={(value) => {
          if (value.trim() === "") {
            onElement({ speedMpm: null });
            return;
          }
          const parsed = parseNum(value);
          if (parsed === null) return;
          onElement({ speedMpm: parsed });
        }}
      />
      <p className="inspector-empty" id="speedMpmNote">
        正式字段 speed_mpm。引擎按 m/s = speed_mpm / 60 计算。
      </p>
      {linear ? (
        <p className="inspector-empty" id="conveyorLinkNote">
          {linked ? "两端已对上邻段或月台。" : copy.conveyorUnlinked}
        </p>
      ) : (
        <p className="inspector-empty" id="cvRuntimeNote">
          {copy.conveyorIdleNote}
        </p>
      )}
      {linear ? (
        <details>
          <summary className="panel-row fold-summary">
            <h3>输送默认参数</h3>
            <span className="mini-tag">可改</span>
          </summary>
          <NumberField
            label="吞吐"
            unit="件/时"
            value={String(selected.throughputUph ?? 120)}
            onChange={(value) => onElement({ throughputUph: parseNum(value) })}
          />
          <NumberField
            label="载重"
            unit="kg"
            value={String(selected.maxLoadKg ?? 1500)}
            onChange={(value) => onElement({ maxLoadKg: parseNum(value) })}
          />
          <div className="field">
            <label>方向</label>
            <div className="input-row">
              <input
                value={selected.direction || "forward"}
                onChange={(event) => onElement({ direction: event.target.value })}
              />
            </div>
          </div>
          <div className="field">
            <label>允许货型</label>
            <div className="input-row">
              <input
                value={(selected.allowLoadTypes || ["pallet"]).join(",")}
                onChange={(event) =>
                  onElement({
                    allowLoadTypes: event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean),
                  })
                }
              />
            </div>
          </div>
        </details>
      ) : null}
    </>
  );
}

function NumberField({
  label,
  unit,
  value,
  placeholder,
  disabled,
  inputId,
  onChange,
}: {
  label: string;
  unit: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  inputId?: string;
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
          id={inputId}
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
