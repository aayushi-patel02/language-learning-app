"""Turning stored feedback into learning insights.

The tutor writes a free-text reason for every wrong answer ("'mesa' is
feminine, it takes 'una'"). Individually that helps one turn; in aggregate it
answers a more useful question, which is *what kind* of mistake this learner
keeps making.

There is no taxonomy coming back from the model, so the areas below are
matched on the vocabulary the reasons actually use. That is a heuristic, and
it is deliberately a conservative one: a reason that matches nothing is
counted as uncategorised rather than forced into the nearest bucket, because
a confidently wrong diagnosis is worse for a learner than no diagnosis.
"""

# Ordered: the first area whose keywords appear wins, so the more specific
# patterns are listed before the general ones.
GRAMMAR_AREAS = [
    (
        'Ser and estar',
        ('ser ', 'estar', "'es'", "'está'", 'es instead', 'está instead'),
    ),
    (
        'Reflexive verbs',
        ('reflexive', "needs 'me'", "'me '", 'pronoun is missing'),
    ),
    (
        'Verb conjugation',
        ('conjugat', 'infinitive', 'first person', 'third person',
         'wrong person', 'tense', 'stem'),
    ),
    (
        'Gender and articles',
        ('feminine', 'masculine', 'gender', 'article', "'el'", "'la'",
         "'un'", "'una'", 'agree'),
    ),
    (
        'Prepositions',
        ('preposition', "'a las'", "'de'", "'en'", "'por'", "'para'",
         'contract'),
    ),
    (
        'Word choice',
        ('confusable', 'means a', 'wrong word', 'instead of', 'you want'),
    ),
]


def categorise(feedback):
    """Name the grammar area a piece of feedback is about, or None."""
    if not feedback:
        return None
    text = feedback.lower()
    for area, keywords in GRAMMAR_AREAS:
        if any(keyword.lower() in text for keyword in keywords):
            return area
    return None


def grammar_breakdown(recent_feedback, older_feedback):
    """Compare error counts per area across two windows.

    `trend` says whether the learner is making fewer of this kind of mistake
    than they were, which is the only reading of the numbers that is
    actionable. Areas with too little data are reported as 'watching' rather
    than given a direction they have not earned.
    """
    areas = {}
    for window, feedbacks in (('recent', recent_feedback), ('older', older_feedback)):
        for feedback in feedbacks:
            area = categorise(feedback)
            if area is None:
                continue
            areas.setdefault(area, {'recent': 0, 'older': 0})[window] += 1

    breakdown = []
    for area, counts in areas.items():
        recent, older = counts['recent'], counts['older']
        if recent + older < 3:
            trend = 'watching'
        elif recent < older:
            trend = 'improving'
        elif recent > older:
            trend = 'needs work'
        else:
            trend = 'steady'
        breakdown.append({
            'area': area,
            'errors': recent + older,
            'recent_errors': recent,
            'trend': trend,
        })

    # Most mistakes first: that is the area worth a learner's attention.
    breakdown.sort(key=lambda entry: (-entry['errors'], entry['area']))
    return breakdown
