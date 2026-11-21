CREATE TABLE IF NOT EXISTS cms_members (
  email TEXT PRIMARY KEY COLLATE NOCASE,
  role TEXT NOT NULL CHECK (role IN ('editor','publisher'))
);
CREATE TABLE IF NOT EXISTS cms_versions (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  object_key TEXT NOT NULL UNIQUE,
  author TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS cms_versions_latest ON cms_versions (created_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS cms_live (
  path TEXT PRIMARY KEY,
  version_id TEXT NOT NULL REFERENCES cms_versions(id)
);
CREATE TABLE IF NOT EXISTS cms_releases (
  id INTEGER PRIMARY KEY,
  actor TEXT NOT NULL,
  published_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  changes TEXT NOT NULL CHECK (json_valid(changes) AND json_type(changes)='array' AND json_array_length(changes) BETWEEN 1 AND 1000)
);

CREATE TRIGGER IF NOT EXISTS cms_apply_release AFTER INSERT ON cms_releases
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM cms_members WHERE email = NEW.actor AND role = 'publisher'
  ) THEN RAISE(ABORT, 'publisher_required') END;
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM json_each(NEW.changes) c
    LEFT JOIN cms_live l ON l.path = json_extract(c.value, '$.path')
    LEFT JOIN cms_versions v ON v.id = json_extract(c.value, '$.version')
    WHERE l.version_id IS NOT json_extract(c.value, '$.expected')
      OR l.version_id IS json_extract(c.value, '$.version')
      OR (json_extract(c.value, '$.version') IS NOT NULL AND v.path IS NOT json_extract(c.value, '$.path'))
  ) THEN RAISE(ABORT, 'release_conflict') END;
  DELETE FROM cms_live WHERE path IN (
    SELECT json_extract(value, '$.path') FROM json_each(NEW.changes)
    WHERE json_extract(value, '$.version') IS NULL
  );
  INSERT INTO cms_live(path, version_id)
    SELECT json_extract(value, '$.path'), json_extract(value, '$.version') FROM json_each(NEW.changes)
    WHERE json_extract(value, '$.version') IS NOT NULL
    ON CONFLICT(path) DO UPDATE SET version_id = excluded.version_id;
END;
