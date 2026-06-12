export const toDateInputValue = (value?: string | null) => {
  if (!value) return "";

  const raw = String(value).trim();

  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

  const slashMatch = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);

  if (slashMatch) {
    const [, month, day, year] = slashMatch;

    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
  }

  const date = new Date(raw);

  if (Number.isNaN(date.getTime())) return "";

  return date.toISOString().slice(0, 10);
};

export const displayDate = (value?: string | null) => {
  if (!value) return "";

  const raw = String(value).trim();

  if (/^\d{2}\/\d{2}\/\d{4}$/.test(raw)) return raw;

  const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);

  if (isoMatch) {
    const [, year, month, day] = isoMatch;
    return `${month}/${day}/${year}`;
  }

  const date = new Date(raw);

  if (Number.isNaN(date.getTime())) return raw;

  return date.toLocaleDateString();
};

export const timestampOf = (item: any) => {
  const value =
    item?.last_activity_at ||
    item?.lastActivityAt ||
    item?.updatedAt ||
    item?.updated_at ||
    item?.uploaded_at ||
    item?.created_at ||
    item?.timestamp;

  if (!value) return -1;

  const timestamp = new Date(value).getTime();

  return Number.isNaN(timestamp) ? -1 : timestamp;
};

export const syncTimestampOf = timestampOf;

export const syncTimeMs = (value: any) => {
  if (!value) return -1;

  const timestamp = new Date(value).getTime();

  return Number.isNaN(timestamp) ? -1 : timestamp;
};

export const incomingStateTime = (item: any) =>
  syncTimeMs(item?.updatedAt || item?.updated_at || item?.last_activity_at || item?.timestamp);

export const formatDurationSeconds = (seconds?: number | string | null) => {
  if (seconds === undefined || seconds === null || seconds === "") return "-";

  const total = Number(seconds);

  if (!Number.isFinite(total)) return String(seconds);

  if (total < 60) return `${Math.round(total)}s`;

  const minutes = Math.floor(total / 60);
  const remainingSeconds = Math.round(total % 60);

  return `${minutes}m ${remainingSeconds}s`;
};

export const formatDurationBetween = (start?: string | null, end?: string | null) => {
  if (!start || !end) return "-";

  const startMs = new Date(start).getTime();
  const endMs = new Date(end).getTime();

  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return "-";

  return formatDurationSeconds((endMs - startMs) / 1000);
};

export const inDateRange = (item: any, range: string) => {
  if (range === "ALL") return true;

  const value =
    item?.updatedAt ||
    item?.updated_at ||
    item?.created_at ||
    item?.last_activity_at ||
    item?.uploaded_at;

  if (!value) return false;

  const age = Date.now() - new Date(value).getTime();

  if (!Number.isFinite(age)) return false;

  const days = range === "TODAY" ? 1 : range === "7D" ? 7 : 30;

  return age <= days * 24 * 60 * 60 * 1000;
};