from types import SimpleNamespace

from langchain_core.messages import SystemMessage

from drone_security.decisions import LangGraphDecisionGate
from drone_security.models.perception import DecisionWindow, SceneObservation
from drone_security.models.session import DEFAULT_WATCH_BRIEF


class FakeClassifier:
    def __init__(self, noul: float, rule: str = "person_on_property", severity: str = "warn") -> None:
        self.noul = noul
        self.rule = rule
        self.severity = severity
        self.states: list[object] = []
        self.questions: dict[str, object] = {}

    def invoke(self, payload: dict[str, object]) -> object:
        self.states.append(payload["state"])
        self.questions = payload["questions"]
        return SimpleNamespace(
            nouls={"alert": SimpleNamespace(noul=self.noul)},
            choices={
                "rule": SimpleNamespace(choice=self.rule, confidence=0.8),
                "severity": SimpleNamespace(choice=self.severity, confidence=0.7),
            },
        )


def _window(video: bytes | None = None) -> DecisionWindow:
    observation = SceneObservation(1_000, 4, True, "person", 0.8, "A person is at the gate.")
    return DecisionWindow("s1", 0, 10_000, (observation,), video=video)


def test_high_noul_routes_to_alert_and_attaches_video():
    classifier = FakeClassifier(0.91)
    result = LangGraphDecisionGate(classifier, threshold=0.6).evaluate(_window(video=b"fake-mp4"))
    assert result.worth_reporting is True
    assert result.fired_rules == ("person_on_property",)
    assert result.severity == "warn"
    state = classifier.states[0]
    assert isinstance(state, list)
    assert isinstance(state[0], SystemMessage)
    assert DEFAULT_WATCH_BRIEF in state[0].content
    assert "person is at the gate" in state[1]
    assert state[2]["type"] == "video"
    assert state[2]["mime_type"] == "video/mp4"


def test_low_noul_is_not_an_alert_and_skips_video_block():
    classifier = FakeClassifier(0.2, rule="none", severity="info")
    result = LangGraphDecisionGate(classifier, threshold=0.6).evaluate(_window())
    assert result.worth_reporting is False
    assert result.fired_rules == ()
    assert isinstance(classifier.states[0], list)
    assert len(classifier.states[0]) == 2


def test_rule_none_suppresses_alert_even_when_noul_is_high():
    classifier = FakeClassifier(0.95, rule="none")
    result = LangGraphDecisionGate(classifier, threshold=0.6).evaluate(_window())
    assert result.worth_reporting is False
    assert result.fired_rules == ()


def test_custom_watch_brief_is_the_system_prompt_and_the_alert_question():
    classifier = FakeClassifier(0.88, rule="brief_match")
    brief = "Only alert when a boat is near the dock. Ignore people and cars."
    result = LangGraphDecisionGate(classifier, threshold=0.6).evaluate(_window(), watch_brief=brief)
    assert result.worth_reporting is True
    assert result.fired_rules == ("brief_match",)
    message = classifier.states[0][0]
    assert isinstance(message, SystemMessage)
    assert brief in message.content
    alert = classifier.questions["alert"]
    assert brief in alert.instructions  # type: ignore[attr-defined]


def test_blank_watch_brief_uses_person_and_vehicle_detection():
    classifier = FakeClassifier(0.2, rule="none", severity="info")
    LangGraphDecisionGate(classifier, threshold=0.6).evaluate(_window(), watch_brief="   ")
    assert DEFAULT_WATCH_BRIEF in classifier.states[0][0].content
    assert "Person detection" in classifier.questions["alert"].instructions  # type: ignore[attr-defined]


def test_missing_api_key_routes_clear_without_calling_google():
    result = LangGraphDecisionGate(None, threshold=0.6, unavailable_reason="GOOGLE_API_KEY is not set").evaluate(
        _window()
    )
    assert result.worth_reporting is False
    assert "GOOGLE_API_KEY" in result.detail
