const RFC_WITH_GMT = / GMT$/;

export const parseBackendDate = (value?: string | null): Date | null => {
  if (!value) return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  // Ignore malformed timestamps that are actually URLs.
  if (/^https?:\/\//i.test(trimmed)) {
    return null;
  }

  const direct = new Date(trimmed);
  if (!Number.isNaN(direct.getTime())) {
    return direct;
  }

  // Handle RFC timestamps with GMT suffix by converting to numeric UTC offset.
  if (RFC_WITH_GMT.test(trimmed)) {
    const normalized = trimmed.replace(RFC_WITH_GMT, ' +0000');
    const fallback = new Date(normalized);
    if (!Number.isNaN(fallback.getTime())) {
      return fallback;
    }
  }

  return null;
};

export const formatBackendDate = (value?: string | null): string => {
  const parsed = parseBackendDate(value);
  if (!parsed) return 'Unknown date';
  return parsed.toLocaleDateString();
};
