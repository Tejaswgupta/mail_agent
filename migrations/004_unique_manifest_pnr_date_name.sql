-- Migration 004: keep only the latest manifest row for a PNR/date/name tuple.
--
-- "Name" is normalized as full_name when present, otherwise first_name + last_name.
-- Existing duplicates are collapsed before the unique index is created.

WITH ranked_manifest_duplicates AS (
    SELECT
        mp.id,
        ROW_NUMBER() OVER (
            PARTITION BY
                lower(trim(mp.pnr)),
                mp.flight_date,
                lower(trim(COALESCE(
                    NULLIF(mp.full_name, ''),
                    trim(COALESCE(mp.first_name, '') || ' ' || COALESCE(mp.last_name, ''))
                )))
            ORDER BY COALESCE(a.uploaded_at, '') DESC, mp.rowid DESC
        ) AS duplicate_rank
    FROM manifest_passengers mp
    LEFT JOIN attachments a ON a.id = mp.attachment_id
    WHERE mp.pnr IS NOT NULL
      AND trim(mp.pnr) <> ''
      AND mp.flight_date IS NOT NULL
      AND trim(mp.flight_date) <> ''
      AND trim(COALESCE(
            NULLIF(mp.full_name, ''),
            trim(COALESCE(mp.first_name, '') || ' ' || COALESCE(mp.last_name, ''))
      )) <> ''
)
DELETE FROM manifest_passengers
WHERE id IN (
    SELECT id FROM ranked_manifest_duplicates WHERE duplicate_rank > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS manifest_pax_unique_pnr_date_name_idx
ON manifest_passengers (
    lower(trim(pnr)),
    flight_date,
    lower(trim(COALESCE(
        NULLIF(full_name, ''),
        trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))
    )))
)
WHERE pnr IS NOT NULL
  AND trim(pnr) <> ''
  AND flight_date IS NOT NULL
  AND trim(flight_date) <> ''
  AND trim(COALESCE(
        NULLIF(full_name, ''),
        trim(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))
  )) <> '';
