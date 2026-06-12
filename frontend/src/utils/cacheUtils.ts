export const CLAIM_CACHE_KEYS = [
  "claims",
  "cachedClaims",
  "workspaceState",
  "offlineClaims",
  "claimWorkspace",
  "claimData",
  "savedClaims",
  "ehr-unified-claims-v2",
  "ehr-completed-claims-v1",
  "ehr-command-center-completed-claims-v1",
  "ehr-claim-processing-mode-overrides-v1",
  "ehr-claim-hitl-cases-v1",
];

export const clearClaimCache = () => {
  if (typeof window === "undefined") return;

  CLAIM_CACHE_KEYS.forEach((key) => {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // Browser storage may be unavailable in private or restricted contexts.
    }

    try {
      window.sessionStorage.removeItem(key);
    } catch {
      // Browser storage may be unavailable in private or restricted contexts.
    }
  });

  if (window.indexedDB) {
    const indexedDbWithDatabases = window.indexedDB as IDBFactory & {
      databases?: () => Promise<Array<{ name?: string | null }>>;
    };

    indexedDbWithDatabases.databases?.()
      .then((dbs) => {
        dbs.forEach((db) => {
          if (db?.name) {
            window.indexedDB.deleteDatabase(db.name);
          }
        });
      })
      .catch(() => {
        // Some browsers do not allow enumerating IndexedDB databases.
      });
  }
};
