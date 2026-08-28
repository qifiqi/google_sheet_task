from app.services.performance_analysis_service import XPLAnalyzer as PerformanceAnalyzer
from app.services.xpl_service import XPLAnalyzer as LegacyXPLAnalyzer, xpl_analyzer


def test_legacy_xpl_import_uses_the_performance_analyzer():
    assert LegacyXPLAnalyzer is PerformanceAnalyzer
    assert isinstance(xpl_analyzer, PerformanceAnalyzer)


def test_composed_analyzer_keeps_text_analysis_behavior():
    result = xpl_analyzer.analyze(
        "\n".join(
            [
                "2025/10/5\t0.00%",
                "2025/10/6\t-0.55%",
                "2025/11/3\t14.88%",
                "2025/12/31\t18.76%",
                "2026/1/2\t21.72%",
                "2026/2/2\t30.23%",
                "2026/3/31\t50.29%",
            ]
        )
    )

    assert result["status"] == "success"
    assert result["results"]["analysis_mode"] == "single"
