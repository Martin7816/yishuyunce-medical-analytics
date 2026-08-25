-- Internal-only additive aggregate layer.
--
-- This file is a schema artifact only.  It is not executed by the application
-- or by the test suite.  The publisher stages a batch, validates it, and only
-- then moves the singleton active pointer in one transaction.

CREATE TABLE IF NOT EXISTS `analytics_aggregate_batch` (
    `batch_id` VARCHAR(128)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `data_version` VARCHAR(191)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `formula_version` VARCHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `registry_version` VARCHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `suppression_policy_version` VARCHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `suppression_policy_json` JSON NOT NULL,
    `grain_json` JSON NOT NULL,
    `measures_json` JSON NOT NULL,
    `input_file_name` VARCHAR(255)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `source_sha256` CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `raw_records` BIGINT UNSIGNED NOT NULL,
    `source_records` BIGINT UNSIGNED NOT NULL,
    `aggregate_rows` BIGINT UNSIGNED NOT NULL,
    `status` VARCHAR(16)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `active_status_guard` TINYINT
        GENERATED ALWAYS AS (
            CASE WHEN `status` = 'ACTIVE' THEN 1 ELSE NULL END
        ) STORED,
    `generated_at` DATETIME(6) NOT NULL,
    `validated_at` DATETIME(6) NULL,
    `activated_at` DATETIME(6) NULL,
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    `error_message` VARCHAR(1024)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
    PRIMARY KEY (`batch_id`),
    UNIQUE KEY `uq_aggregate_batch_identity` (
        `data_version`, `formula_version`, `registry_version`,
        `suppression_policy_version`
    ),
    KEY `idx_aggregate_batch_status` (`status`),
    KEY `idx_aggregate_batch_data_version` (`data_version`),
    UNIQUE KEY `uq_aggregate_batch_single_active` (`active_status_guard`),
    UNIQUE KEY `uq_aggregate_batch_status` (`batch_id`, `status`),
    CONSTRAINT `ck_aggregate_batch_status` CHECK (
        `status` IN ('STAGING', 'VALIDATED', 'ACTIVE', 'RETIRED', 'FAILED')
    ),
    CONSTRAINT `ck_aggregate_batch_json` CHECK (
        JSON_TYPE(`suppression_policy_json`) = 'OBJECT'
        AND JSON_TYPE(`grain_json`) = 'ARRAY'
        AND JSON_TYPE(`measures_json`) = 'ARRAY'
    ),
    CONSTRAINT `ck_aggregate_batch_counts` CHECK (
        `raw_records` >= `source_records`
        AND `source_records` > 0
        AND `aggregate_rows` > 0
    ),
    CONSTRAINT `ck_aggregate_batch_sha256` CHECK (
        `source_sha256` REGEXP '^[0-9a-f]{64}$'
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_bin;


CREATE TABLE IF NOT EXISTS `analytics_aggregate_fact` (
    `batch_id` VARCHAR(128)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `facility_id` VARCHAR(64)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `diagnosis_code` VARCHAR(64)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `age` VARCHAR(64)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `gender` VARCHAR(16)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `severity` VARCHAR(64)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `payment` VARCHAR(128)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `admission` VARCHAR(64)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `record_count` BIGINT UNSIGNED NOT NULL,
    `los_sum` BIGINT UNSIGNED NOT NULL,
    `los_valid_count` BIGINT UNSIGNED NOT NULL,
    `charges_sum` DECIMAL(38, 2) NOT NULL,
    `charges_valid_count` BIGINT UNSIGNED NOT NULL,
    `costs_sum` DECIMAL(38, 2) NOT NULL,
    `costs_valid_count` BIGINT UNSIGNED NOT NULL,
    `emergency_yes_count` BIGINT UNSIGNED NOT NULL,
    `emergency_valid_count` BIGINT UNSIGNED NOT NULL,
    `surgical_yes_count` BIGINT UNSIGNED NOT NULL,
    `surgical_valid_count` BIGINT UNSIGNED NOT NULL,
    `severe_yes_count` BIGINT UNSIGNED NOT NULL,
    `severe_valid_count` BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (
        `batch_id`, `facility_id`, `diagnosis_code`, `age`, `gender`,
        `severity`, `payment`, `admission`
    ),
    KEY `idx_aggregate_fact_diagnosis` (`batch_id`, `diagnosis_code`),
    KEY `idx_aggregate_fact_facility` (`batch_id`, `facility_id`),
    KEY `idx_aggregate_fact_age` (`batch_id`, `age`),
    KEY `idx_aggregate_fact_gender` (`batch_id`, `gender`),
    KEY `idx_aggregate_fact_severity` (`batch_id`, `severity`),
    KEY `idx_aggregate_fact_payment` (`batch_id`, `payment`),
    KEY `idx_aggregate_fact_admission` (`batch_id`, `admission`),
    CONSTRAINT `fk_aggregate_fact_batch`
        FOREIGN KEY (`batch_id`) REFERENCES `analytics_aggregate_batch` (`batch_id`)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT `ck_aggregate_fact_dimensions` CHECK (
        CHAR_LENGTH(TRIM(`facility_id`)) > 0
        AND CHAR_LENGTH(TRIM(`diagnosis_code`)) > 0
        AND CHAR_LENGTH(TRIM(`age`)) > 0
        AND CHAR_LENGTH(TRIM(`gender`)) > 0
        AND CHAR_LENGTH(TRIM(`severity`)) > 0
        AND CHAR_LENGTH(TRIM(`payment`)) > 0
        AND CHAR_LENGTH(TRIM(`admission`)) > 0
    ),
    CONSTRAINT `ck_aggregate_fact_counts` CHECK (
        `record_count` > 0
        AND `los_valid_count` <= `record_count`
        AND `charges_valid_count` <= `record_count`
        AND `costs_valid_count` <= `record_count`
        AND `emergency_valid_count` <= `record_count`
        AND `surgical_valid_count` <= `record_count`
        AND `severe_valid_count` <= `record_count`
        AND `emergency_yes_count` <= `emergency_valid_count`
        AND `surgical_yes_count` <= `surgical_valid_count`
        AND `severe_yes_count` <= `severe_valid_count`
    ),
    CONSTRAINT `ck_aggregate_fact_sums` CHECK (
        `charges_sum` >= 0 AND `costs_sum` >= 0
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_bin;


CREATE TABLE IF NOT EXISTS `analytics_aggregate_active_batch` (
    `singleton_id` TINYINT UNSIGNED NOT NULL,
    `batch_id` VARCHAR(128)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `batch_status` VARCHAR(16)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'ACTIVE',
    `activated_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`singleton_id`),
    CONSTRAINT `ck_aggregate_active_singleton` CHECK (
        `singleton_id` = 1 AND `batch_status` = 'ACTIVE'
    ),
    CONSTRAINT `fk_aggregate_active_batch`
        FOREIGN KEY (`batch_id`, `batch_status`)
        REFERENCES `analytics_aggregate_batch` (`batch_id`, `status`)
        ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_bin;
