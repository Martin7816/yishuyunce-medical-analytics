CREATE TABLE IF NOT EXISTS `analysis_snapshot_result` (
  `module_key` VARCHAR(64) NOT NULL,
  `entity_key` VARCHAR(191) NOT NULL,
  `payload_json` JSON NOT NULL,
  `data_version` VARCHAR(191) NOT NULL,
  `generated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`module_key`, `entity_key`),
  KEY `idx_analysis_snapshot_version` (`data_version`),
  CONSTRAINT `ck_analysis_module_key_nonempty` CHECK (CHAR_LENGTH(TRIM(`module_key`)) > 0),
  CONSTRAINT `ck_analysis_entity_key_nonempty` CHECK (CHAR_LENGTH(TRIM(`entity_key`)) > 0),
  CONSTRAINT `ck_analysis_data_version_nonempty` CHECK (CHAR_LENGTH(TRIM(`data_version`)) > 0),
  CONSTRAINT `ck_analysis_payload_object` CHECK (JSON_TYPE(`payload_json`) = 'OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
