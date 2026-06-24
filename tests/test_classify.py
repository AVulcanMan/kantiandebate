import pytest

from kds.corpus.classify import classify


@pytest.mark.parametrize(
    "text,expected_class",
    [
        ("Lobbying should be banned in US politics.", "policy"),
        ("The US Federal Government should implement more checks.", "policy"),
        ("Courts ought to forgive first-time offenders.", "value"),
        ("This house values hard work over creativity.", "value"),
        ("The existence of billionaires is immoral.", "value"),
        ("Online education has improved education.", "fact"),
        ("Strong dictatorship is better than weak democracy.", "fact"),
        ("Social media does more harm than good.", "fact"),
    ],
)
def test_known_classifications(text, expected_class):
    cls, conf = classify(text)
    assert cls == expected_class
    assert conf in {"high", "medium", "low"}


def test_comparative_ruling_better_than_is_fact():
    # Frozen taxonomy decision: 'better than' => fact, not value.
    assert classify("Cats are better than dogs.")[0] == "fact"


def test_comparative_ruling_outweighs_is_value():
    assert classify("Liberty outweighs security.")[0] == "value"
