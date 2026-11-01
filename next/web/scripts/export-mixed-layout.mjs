import { writeFileSync } from "node:fs";
import { MIXED_TEMPLATE_ID, buildFacility, buildLayout, draftFor } from "../src/workbench/draft.ts";

const draft = draftFor("mixed");
if (draft.templateId !== MIXED_TEMPLATE_ID) throw new Error(draft.templateId);
const facility = buildFacility(draft, "facility-mixed", "mx-fac-eb");
const layout = buildLayout(draft, "layout-mixed-wh-v0", "pending", {
  id: "facility-mixed",
  revision: "mx-fac-eb",
});
writeFileSync("/tmp/mx-layout.json", JSON.stringify(layout, null, 2));
writeFileSync("/tmp/mx-facility.json", JSON.stringify(facility, null, 2));
console.log("template", draft.templateId, "elements", layout.elements.length);
