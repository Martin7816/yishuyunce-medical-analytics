-- M1 服务结果表：疾病病例量 TOP10
--
-- 这张表只保存当前已经校验并发布的完整结果批次，不保存原始住院明细，
-- 也不保存历史批次。正式刷新必须使用下方“事务刷新模板”，不能逐行提交。

CREATE TABLE IF NOT EXISTS `disease_case_count_top10_result` (
    `rank` TINYINT UNSIGNED NOT NULL,
    `diagnosis_name` VARCHAR(255)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    `case_count` BIGINT UNSIGNED NOT NULL,
    `unit` VARCHAR(32)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `data_version` VARCHAR(255)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    `generated_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`rank`),
    UNIQUE KEY `uq_top10_version_rank` (`data_version`, `rank`),
    UNIQUE KEY `uq_top10_version_diagnosis` (`data_version`, `diagnosis_name`),
    CONSTRAINT `ck_top10_rank` CHECK (`rank` BETWEEN 1 AND 10),
    CONSTRAINT `ck_top10_diagnosis_name` CHECK (CHAR_LENGTH(`diagnosis_name`) > 0),
    CONSTRAINT `ck_top10_case_count` CHECK (`case_count` > 0),
    CONSTRAINT `ck_top10_unit` CHECK (`unit` = 'discharge_records'),
    CONSTRAINT `ck_top10_data_version` CHECK (CHAR_LENGTH(`data_version`) > 0)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_bin;

-- 当前结果查询：表中所有已提交记录属于同一个完整 data_version。
SELECT
    `rank`,
    `diagnosis_name`,
    `case_count`,
    `unit`,
    `data_version`,
    `generated_at`
FROM `disease_case_count_top10_result`
ORDER BY `rank` ASC;

-- 事务刷新模板（由结果发布程序绑定参数后执行）：
-- 1. Spark 结果先在 HDFS/发布程序侧完成完整性核对：排名连续、数量 1—10、
--    名称唯一、排序符合 docs/02-metrics-and-data-contract.md。
-- 2. 生成一次性的 :data_version 和 :generated_at，并为本批每一行使用相同值。
-- 3. 在 MySQL 中执行以下事务；每条 INSERT 的列顺序必须与候选结果一致。
-- 4. 插入后执行 COUNT/版本/排名检查，全部通过才 COMMIT；任何异常都 ROLLBACK。
--
-- START TRANSACTION;
-- DELETE FROM `disease_case_count_top10_result`;
-- INSERT INTO `disease_case_count_top10_result`
--     (`rank`, `diagnosis_name`, `case_count`, `unit`, `data_version`, `generated_at`)
-- VALUES
--     (:rank_1, :diagnosis_1, :count_1, 'discharge_records', :data_version, :generated_at),
--     -- ... 继续到本批最后一行，最多 10 行
--     (:rank_n, :diagnosis_n, :count_n, 'discharge_records', :data_version, :generated_at);
--
-- SELECT
--     COUNT(*) AS row_count,
--     MIN(`rank`) AS min_rank,
--     MAX(`rank`) AS max_rank,
--     COUNT(DISTINCT `rank`) AS distinct_rank_count,
--     MAX(`rank`) - MIN(`rank`) + 1 AS expected_contiguous_count,
--     COUNT(DISTINCT `data_version`) AS version_count,
--     COUNT(DISTINCT `generated_at`) AS generated_at_count
-- FROM `disease_case_count_top10_result`;
--
-- 若 row_count 与候选行数不一致、distinct_rank_count <> row_count、
-- expected_contiguous_count <> row_count、version_count <> 1 或
-- generated_at_count <> 1，则 ROLLBACK；否则 COMMIT。
--
-- 事务失败时回滚 DELETE 和 INSERT，旧的已提交批次继续可读；成功刷新后只保留
-- 新的当前批次。重复发布同一 data_version 是幂等的，因为每次都替换完整当前批次。
