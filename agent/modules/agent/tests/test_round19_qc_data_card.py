"""QC registrations remain declarations and survive a compact cohort card."""
from backend.analysis_data_card import summarize


def test_registered_qc_limits_visible_in_large_cohort_card():
    entries = [
        {"subject_id": "s" + str(i), "index": i, "species_declared": "human",
         "qc_visual": "需复核" if i in (2, 5) else "可保留",
         "qc_note": "Low contrast; retained pending follow-up" if i in (2, 5) else "AI preliminary only",
         "qc_reviewer": "Claude AI 初查，非专家盲审",
         "qc_automatic_flags": '["etiv_mm3"]' if i == 8 else "[]",
         "qc_visual_source": "/operator/review.csv"}
        for i in range(20)
    ]
    result = summarize({"files": []}, entries, {})
    assert len(result["summary"]) <= 1500
    assert "s2,s5" in result["summary"]
    assert "automatic flags retained=s8" in result["summary"]
    assert "not expert/blind approval" in result["summary"]
    assert len(result["quality_control"]) == 20
    assert result["quality_control"][2]["qc_note"].startswith("Low contrast")


def test_unregistered_qc_does_not_change_old_card_schema():
    result = summarize({"files": []}, [{"subject_id": "s0", "index": 0}], {})
    assert "quality_control" not in result
    assert "QC declarations" not in result["summary"]


def test_both_legacy_and_registered_card_stay_unverified():
    result = summarize({"files": []}, [{"subject_id": "s0", "index": 0,
                       "qc_visual": "可保留", "qc_note": "AI report"}], {})
    assert result["subjects"][0]["species_verified"] is None
    assert "physical scale unverified" in result["subjects"][0]["space"]
    assert "not expert/blind approval" in result["summary"]
