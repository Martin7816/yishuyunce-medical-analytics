CREATE TABLE IF NOT EXISTS `analysis_snapshot_result` (
  `module_key` VARCHAR(64) NOT NULL,
  `entity_key` VARCHAR(191) NOT NULL,
  `payload_json` JSON NOT NULL,
  `data_version` VARCHAR(191) NOT NULL,
  `generated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`module_key`, `entity_key`),
  KEY `idx_analysis_snapshot_version` (`data_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
