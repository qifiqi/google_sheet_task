from app.services.xpl_service import XPLAnalyzer, xpl_analyzer


def test_xpl_service_exposes_the_composed_analyzer():
    assert isinstance(xpl_analyzer, XPLAnalyzer)


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
