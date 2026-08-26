from app.product_identity import (
    INSIGHT_REPORT_TITLE,
    PRODUCT_NAME,
    PRODUCT_SHORT_NAME,
    PRODUCT_TAGLINE,
)


def test_product_identity_uses_the_formal_project_name():
    assert PRODUCT_NAME == "医数云策智慧医疗运营大数据与AI决策分析平台"
    assert PRODUCT_SHORT_NAME == "医数云策"
    assert PRODUCT_NAME == f"{PRODUCT_SHORT_NAME}{PRODUCT_TAGLINE}"
    assert INSIGHT_REPORT_TITLE == "医数云策洞察简报"
