export const normalizeSuggestion = (suggestion: any) => {
  if (!suggestion) return null;

  if (typeof suggestion === "string") {
    return {
      category: "Suggestion",
      message: suggestion,
      severity: "info",
    };
  }

  return {
    category: suggestion.category || suggestion.field || suggestion.type || "Suggestion",
    field: suggestion.field,
    message:
      suggestion.message ||
      suggestion.suggestion ||
      suggestion.recommendation ||
      suggestion.description ||
      "",
    severity: suggestion.severity || suggestion.priority || "info",
    value: suggestion.value,
  };
};

export const suggestionsFromDenial = (denial: any) => {
  const raw =
    denial?.suggestions ||
    denial?.recommendations ||
    denial?.ai_suggestions ||
    denial?.payload?.suggestions ||
    [];

  const list = Array.isArray(raw) ? raw : [raw];

  return list.map(normalizeSuggestion).filter(Boolean);
};