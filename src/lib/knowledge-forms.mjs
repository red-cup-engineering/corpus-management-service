import { bytesCompare, encodeCanonical, exactIdentity } from "@red-cup-engineering/semiotic-content-address-system";

export function analyzeForms(forms) {
  const issues = [];
  const seen = new Set();
  const charges = new Map();
  forms.forEach((form, index) => {
    const locus = typeof form?.id === "string" && form.id ? form.id : `form-index:${index}`;
    if (!form || typeof form !== "object" || Array.isArray(form)) {
      issues.push({ type: "ill-typed-form", locus });
      return;
    }
    if (typeof form.id !== "string" || !form.id) issues.push({ type: "missing-identifier", locus });
    else if (seen.has(form.id)) issues.push({ type: "duplicate-identifier", locus: form.id });
    else seen.add(form.id);
    if (typeof form.schema !== "string" || !form.schema) issues.push({ type: "missing-schema-address", locus });
    if (!form.provenance || typeof form.provenance !== "object") issues.push({ type: "missing-provenance", locus });
    for (const claim of Array.isArray(form.claims) ? form.claims : []) {
      if (!claim || typeof claim.entity !== "string" || typeof claim.attribute !== "string" || !["held", "denied"].includes(claim.charge)) {
        issues.push({ type: "ill-typed-claim", locus });
        continue;
      }
      const key = exactIdentity([claim.entity, claim.attribute, claim.value]);
      if (!charges.has(key)) charges.set(key, new Set());
      charges.get(key).add(claim.charge);
    }
  });
  for (const [locus, values] of charges) if (values.size > 1) issues.push({ type: "contested-claim", locus });
  return issues.sort((a, b) => bytesCompare(encodeCanonical(a), encodeCanonical(b)));
}
