"""Hand-written conversation turns used by DEMO_MODE and every failure path.

Every line here is written and checked by hand. This is what the app falls
back to when a provider is down, and what `DEMO_MODE=true` serves instead of
calling out at all - so a live demo never depends on someone else's uptime.

Rules these turns follow, matching what the live prompt asks the model for:

- Every `target_word` is a real `VocabItem.term` value from seed_vocab, so
  the SM-2 update credits the vocabulary actually on screen.
- Exactly one reply per turn is correct, and its position varies.
- Each wrong reply contains a concrete grammatical error in that language -
  never merely an off-topic or incomplete answer.

Spanish runs a full eight-turn arc per topic, because it is the language a
demo is most likely to be given in. The other three carry three turns per
topic: enough that an outage does not loop immediately, without pretending a
hand-written bank is the primary path. Falling back across languages is never
an option, so each language stands on its own bank - a French lesson
answering itself in Spanish would be worse than repeating.
"""

import unicodedata

from .models import DAILY_ROUTINE, DEFAULT_LANGUAGE, ORDERING_FOOD, TRAVEL_BASICS


# Scaffolding for a learner who chooses to type instead of tapping: the shape
# of a correct answer with the tested part blanked out. Keyed on target word
# rather than passed to every _turn() call, so the bank stays readable.
# Keys are written unaccented purely so the lookup is forgiving. The values
# are shown to the learner as a model of correct Spanish, in an app that marks
# a dropped accent wrong, so they carry full accents and punctuation.
SPANISH_STARTERS = {
    # daily routine
    'levantarse': 'Me levanto a las ____.',
    'desayunar': 'Desayuno en ____.',
    'ducharse': 'Me ducho ____ de desayunar.',
    'vestirse': 'Sí, me visto muy ____.',
    'el trabajo': 'Voy al trabajo en ____.',
    'almorzar': 'Almuerzo a la ____.',
    'cenar': 'Ceno con ____.',
    'acostarse': 'Me acuesto a las ____.',
    # ordering food
    'la mesa': 'Una mesa para ____, por favor.',
    'el menu': 'Sí, ¿me trae el ____, por favor?',
    'la bebida': 'Un vaso de ____, por favor.',
    'la ensalada': 'Sí, una ensalada ____.',
    'el pollo': '____ con arroz, por favor.',
    'picante': 'Sí, me gusta la comida ____.',
    'el postre': 'Sí, un ____ de postre.',
    'la cuenta': 'No, gracias. La ____, por favor.',
    # travel basics
    'el billete': 'Un billete a ____, por favor.',
    'a que hora sale?': '¿A qué hora ____ el tren?',
    'la estacion': '¿Dónde ____ la estación?',
    'cerca': '¿Está ____ del hotel?',
    'a la derecha': 'Gracias. ¿Y luego a la ____?',
    'el hotel': 'Sí, mi hotel ____ en el centro.',
    'la habitacion': 'Sí, reservé una ____ doble.',
    'la ayuda': 'No, gracias. Ha sido de mucha ____.',
}

def _starter_for(target, starters):
    """Look up a starter, falling back to an accent-insensitive match.

    The exact key is tried first, then a flattened one. Order matters: the
    flattening drops every non-spacing combining mark, which is exactly right
    for a missing Spanish accent but destroys Devanagari, where the vowel
    signs in मेज़ are combining marks carrying the word. Trying the written
    key first means the Hindi map is keyed the way the words are actually
    spelled, and only Latin scripts ever reach the forgiving path.
    """
    key = target.replace('¿', '').replace('¡', '').lower().strip()
    if key in starters:
        return starters[key]

    decomposed = unicodedata.normalize('NFD', key)
    flattened = ''.join(
        char for char in decomposed if unicodedata.category(char) != 'Mn'
    )
    return starters.get(flattened, '')


def _turn(target, text, en, replies):
    """Build a turn, numbering the replies so ids always match their order."""
    return {
        'target_word': target,
        'tutor_message': text,
        'tutor_message_en': en,
        'sentence_starter': '',
        'replies': [
            {
                'id': index,
                'text': reply[0],
                'en': reply[1],
                'is_correct': reply[2],
                'why_wrong': reply[3] if len(reply) > 3 else '',
            }
            for index, reply in enumerate(replies)
        ],
    }


def _bank(turns, starters):
    """Attach each turn's sentence starter from its language's starter map.

    Done here rather than inside _turn() so the starter map does not have to
    be threaded through every one of the calls below.
    """
    for turn in turns:
        turn['sentence_starter'] = _starter_for(turn['target_word'], starters)
    return turns


SPANISH_TURNS = {
    # --- waking up through going to bed ---------------------------------
    DAILY_ROUTINE: _bank([
        _turn(
            'levantarse',
            '¡Hola! ¿A qué hora te levantas normalmente?',
            'Hi! What time do you usually get up?',
            [
                ('Yo levanto a las siete.', 'I get up at seven.', False,
                 "'levantarse' is reflexive - it needs 'me'."),
                ('Me levanto a las siete.', 'I get up at seven.', True),
                ('Me levanta a las siete.', 'I get up at seven.', False,
                 "'levanta' is he/she - use 'levanto' for I."),
            ],
        ),
        _turn(
            'desayunar',
            '¿Y desayunas en casa o en el trabajo?',
            'And do you have breakfast at home or at work?',
            [
                ('Desayuno en casa.', 'I have breakfast at home.', True),
                ('Yo desayunar en casa.', 'I have breakfast at home.', False,
                 "Conjugate the verb: 'desayuno', not 'desayunar'."),
                ('Desayunas en casa.', 'You have breakfast at home.', False,
                 "'desayunas' means you - use 'desayuno' for I."),
            ],
        ),
        _turn(
            'ducharse',
            '¿Te duchas antes o después de desayunar?',
            'Do you shower before or after breakfast?',
            [
                ('Me ducho antes de desayunar.', 'I shower before breakfast.', True),
                ('Yo ducho antes de desayunar.', 'I shower before breakfast.', False,
                 "'ducharse' is reflexive - it needs 'me'."),
                ('Me ducho antes que desayunar.', 'I shower before breakfast.', False,
                 "The phrase is 'antes de', not 'antes que'."),
            ],
        ),
        _turn(
            'vestirse',
            '¿Te vistes rápido por la mañana?',
            'Do you get dressed quickly in the morning?',
            [
                ('Sí, me vesto muy rápido.', 'Yes, I get dressed very quickly.', False,
                 "The stem changes: 'me visto', not 'me vesto'."),
                ('Sí, yo visto muy rápido.', 'Yes, I get dressed very quickly.', False,
                 "'vestirse' is reflexive - it needs 'me'."),
                ('Sí, me visto muy rápido.', 'Yes, I get dressed very quickly.', True),
            ],
        ),
        _turn(
            'el trabajo',
            '¿Y cómo vas al trabajo?',
            'And how do you get to work?',
            [
                ('Voy a el trabajo en autobús.', 'I go to work by bus.', False,
                 "'a' and 'el' contract to 'al'."),
                ('Voy al trabajo en autobús.', 'I go to work by bus.', True),
                ('Yo va al trabajo en autobús.', 'I go to work by bus.', False,
                 "'va' is he/she - use 'voy' for I."),
            ],
        ),
        _turn(
            'almorzar',
            '¿A qué hora almuerzas?',
            'What time do you have lunch?',
            [
                ('Almuerzo a la una.', 'I have lunch at one.', True),
                ('Almorzo a la una.', 'I have lunch at one.', False,
                 "The stem changes: 'almuerzo', not 'almorzo'."),
                ('Almuerzo a las una.', 'I have lunch at one.', False,
                 "One o'clock is singular: 'a la una'."),
            ],
        ),
        _turn(
            'cenar',
            '¿Con quién cenas normalmente?',
            'Who do you usually have dinner with?',
            [
                ('Yo cenar con mi familia.', 'I have dinner with my family.', False,
                 "Conjugate the verb: 'ceno', not 'cenar'."),
                ('Ceno con mi familia.', 'I have dinner with my family.', True),
                ('Ceno con mi familio.', 'I have dinner with my family.', False,
                 "The word is 'familia' - it is feminine."),
            ],
        ),
        _turn(
            'acostarse',
            'Qué bien. ¿Y a qué hora te acuestas?',
            'Nice. And what time do you go to bed?',
            [
                ('Me acosto a las once.', 'I go to bed at eleven.', False,
                 "The stem changes: 'me acuesto', not 'me acosto'."),
                ('Me acuesto en las once.', 'I go to bed at eleven.', False,
                 "Clock times take 'a las', not 'en las'."),
                ('Me acuesto a las once.', 'I go to bed at eleven.', True),
            ],
        ),
    ], SPANISH_STARTERS),
    # --- sitting down through paying ------------------------------------
    ORDERING_FOOD: _bank([
        _turn(
            'la mesa',
            'Buenas tardes. ¿Una mesa para cuántas personas?',
            'Good afternoon. A table for how many people?',
            [
                ('Una mesa para dos, por favor.', 'A table for two, please.', True),
                ('Un mesa para dos, por favor.', 'A table for two, please.', False,
                 "'mesa' is feminine - it takes 'una'."),
                ('Una mesa por dos, por favor.', 'A table for two, please.', False,
                 "Use 'para' for purpose, not 'por'."),
            ],
        ),
        _turn(
            'el menú',
            'Perfecto. ¿Quiere ver el menú?',
            'Perfect. Would you like to see the menu?',
            [
                ('Sí, ¿me trae el menú, por favor?',
                 'Yes, could you bring me the menu, please?', True),
                ('Sí, ¿me trae la menú, por favor?',
                 'Yes, could you bring me the menu, please?', False,
                 "'menú' is masculine - it takes 'el'."),
                ('Sí, yo querer el menú.', 'Yes, I want the menu.', False,
                 "Conjugate the verb: 'quiero', not 'querer'."),
            ],
        ),
        _turn(
            'la bebida',
            '¿Y qué quiere beber?',
            'And what would you like to drink?',
            [
                ('Una vaso de agua, por favor.', 'A glass of water, please.', False,
                 "'vaso' is masculine - it takes 'un'."),
                ('Un vaso de agua, por favor.', 'A glass of water, please.', True),
                ('Un vaso de la agua, por favor.', 'A glass of water, please.', False,
                 "Drop the article: 'de agua', not 'de la agua'."),
            ],
        ),
        _turn(
            'la ensalada',
            '¿Desea algo para empezar?',
            'Would you like something to start?',
            [
                ('Sí, un ensalada mixta.', 'Yes, a mixed salad.', False,
                 "'ensalada' is feminine - it takes 'una'."),
                ('Sí, una ensalada mixto.', 'Yes, a mixed salad.', False,
                 "The adjective must agree: 'mixta'."),
                ('Sí, una ensalada mixta.', 'Yes, a mixed salad.', True),
            ],
        ),
        _turn(
            'el pollo',
            'Muy bien. ¿Y de plato principal?',
            'Very good. And for the main course?',
            [
                ('La pollo con arroz, por favor.', 'Chicken with rice, please.', False,
                 "'pollo' is masculine - it takes 'el'."),
                ('Pollo con arroz, por favor.', 'Chicken with rice, please.', True),
                ('Yo querer pollo con arroz.', 'I want chicken with rice.', False,
                 "Conjugate the verb: 'quiero', not 'querer'."),
            ],
        ),
        _turn(
            'picante',
            '¿Le gusta la comida picante?',
            'Do you like spicy food?',
            [
                ('Sí, me gusta la comida picante.', 'Yes, I like spicy food.', True),
                ('Sí, me gusta la comida picanta.', 'Yes, I like spicy food.', False,
                 "'picante' does not change for gender."),
                ('Sí, yo gusta la comida picante.', 'Yes, I like spicy food.', False,
                 "'gustar' needs 'me': 'me gusta'."),
            ],
        ),
        _turn(
            'el postre',
            '¿Quiere algo de postre?',
            'Would you like any dessert?',
            [
                ('Sí, una flan de postre.', 'Yes, a flan for dessert.', False,
                 "'flan' is masculine - it takes 'un'."),
                ('Sí, un flan del postre.', 'Yes, a flan for dessert.', False,
                 "The phrase is 'de postre', without the article."),
                ('Sí, un flan de postre.', 'Yes, a flan for dessert.', True),
            ],
        ),
        _turn(
            'la cuenta',
            'Enseguida. ¿Algo más?',
            'Right away. Anything else?',
            [
                ('No, gracias. El cuenta, por favor.',
                 'No thanks. The bill, please.', False,
                 "'cuenta' is feminine - it takes 'la'."),
                ('No, gracias. La cuenta, por favor.',
                 'No thanks. The bill, please.', True),
                ('No, gracias. La cuento, por favor.',
                 'No thanks. The bill, please.', False,
                 "'cuento' means a story - you want 'cuenta'."),
            ],
        ),
    ], SPANISH_STARTERS),
    # --- buying a ticket through finding the hotel -----------------------
    TRAVEL_BASICS: _bank([
        _turn(
            'el billete',
            'Buenos días. ¿Adónde va?',
            'Good morning. Where are you going?',
            [
                ('Un billete a Madrid, por favor.', 'A ticket to Madrid, please.', True),
                ('Una billete a Madrid, por favor.', 'A ticket to Madrid, please.', False,
                 "'billete' is masculine - it takes 'un'."),
                ('Un billete en Madrid, por favor.', 'A ticket to Madrid, please.', False,
                 "Destinations take 'a', not 'en'."),
            ],
        ),
        _turn(
            '¿a qué hora sale?',
            'Aquí tiene. El tren sale muy pronto.',
            'Here you are. The train leaves very soon.',
            [
                ('¿A qué hora sales el tren?', 'What time does the train leave?', False,
                 "'sales' means you leave - use 'sale' for the train."),
                ('¿A qué hora sale el tren?', 'What time does the train leave?', True),
                ('¿A qué hora sale la tren?', 'What time does the train leave?', False,
                 "'tren' is masculine - it takes 'el'."),
            ],
        ),
        _turn(
            'la estación',
            'A las nueve, desde la estación central.',
            'At nine, from the central station.',
            [
                ('¿Dónde es la estación?', 'Where is the station?', False,
                 "Location uses 'estar': '¿Dónde está?'"),
                ('¿Dónde está el estación?', 'Where is the station?', False,
                 "'estación' is feminine - it takes 'la'."),
                ('¿Dónde está la estación?', 'Where is the station?', True),
            ],
        ),
        _turn(
            'cerca',
            'Está muy cerca de aquí, a cinco minutos.',
            "It's very close to here, five minutes away.",
            [
                ('¿Está cerca del hotel?', 'Is it near the hotel?', True),
                ('¿Está cerca de el hotel?', 'Is it near the hotel?', False,
                 "'de' and 'el' contract to 'del'."),
                ('¿Es cerca del hotel?', 'Is it near the hotel?', False,
                 "Location uses 'estar', not 'ser'."),
            ],
        ),
        _turn(
            'a la derecha',
            'Sí. Gire a la derecha al salir.',
            'Yes. Turn right as you leave.',
            [
                ('Gracias. ¿Y luego a la izquierdo?',
                 'Thanks. And then to the left?', False,
                 "The phrase is 'a la izquierda', with an -a."),
                ('Gracias. ¿Y luego a la izquierda?',
                 'Thanks. And then to the left?', True),
                ('Gracias. ¿Y luego al izquierda?',
                 'Thanks. And then to the left?', False,
                 "It is 'a la izquierda', not 'al izquierda'."),
            ],
        ),
        _turn(
            'el hotel',
            'Exacto. ¿Ya tiene hotel en la ciudad?',
            'Exactly. Do you already have a hotel in the city?',
            [
                ('Sí, mi hotel está en el centro.',
                 'Yes, my hotel is downtown.', True),
                ('Sí, mi hotel es en el centro.',
                 'Yes, my hotel is downtown.', False,
                 "Location uses 'estar', not 'ser'."),
                ('Sí, mi hotel está en la centro.',
                 'Yes, my hotel is downtown.', False,
                 "'centro' is masculine - it takes 'el'."),
            ],
        ),
        _turn(
            'la habitación',
            'Muy bien. ¿Reservó una habitación doble?',
            'Very good. Did you book a double room?',
            [
                ('Sí, reservé un habitación doble.',
                 'Yes, I booked a double room.', False,
                 "'habitación' is feminine - it takes 'una'."),
                ('Sí, yo reservar una habitación doble.',
                 'Yes, I booked a double room.', False,
                 "Conjugate the verb: 'reservé', not 'reservar'."),
                ('Sí, reservé una habitación doble.',
                 'Yes, I booked a double room.', True),
            ],
        ),
        _turn(
            'la ayuda',
            'Perfecto. ¿Necesita algo más?',
            'Perfect. Do you need anything else?',
            [
                ('No, gracias. Ha sido de mucha ayuda.',
                 "No thanks. You've been a great help.", True),
                ('No, gracias. Ha sido de mucho ayuda.',
                 "No thanks. You've been a great help.", False,
                 "'ayuda' is feminine - it takes 'mucha'."),
                ('No, gracias. Es sido de mucha ayuda.',
                 "No thanks. You've been a great help.", False,
                 "The perfect tense uses 'ha', not 'es'."),
            ],
        ),
    ], SPANISH_STARTERS),
}


FRENCH_STARTERS = {
    'se lever': 'Je me lève à ____.',
    'prendre le petit déjeuner': 'Je prends mon petit déjeuner ____.',
    'le travail': 'Je vais au travail en ____.',
    'la table': "Une table pour ____, s'il vous plaît.",
    "l'addition": "Oui, ____ s'il vous plaît.",
    "l'eau": "Un verre ____, s'il vous plaît.",
    'le billet': "Un billet pour ____, s'il vous plaît.",
    'la gare': "Où est ____, s'il vous plaît ?",
    "l'hôtel": 'Mon hôtel est ____.',
}

FRENCH_TURNS = {
    DAILY_ROUTINE: _bank([
        _turn(
            'se lever',
            "Bonjour ! À quelle heure te lèves-tu d'habitude ?",
            'Hello! What time do you usually get up?',
            [
                ('Je lève à sept heures.', 'I get up at seven.', False,
                 "'se lever' is reflexive - it needs 'me'."),
                ('Je me lève à sept heures.', 'I get up at seven.', True),
                ('Je se lève à sept heures.', 'I get up at seven.', False,
                 "With 'je' the reflexive pronoun is 'me', not 'se'."),
            ],
        ),
        _turn(
            'prendre le petit déjeuner',
            'Et tu prends ton petit déjeuner à la maison ?',
            'And do you have your breakfast at home?',
            [
                ('Oui, je prends mon petit déjeuner à la maison.',
                 'Yes, I have my breakfast at home.', True),
                ('Oui, je prend mon petit déjeuner à la maison.',
                 'Yes, I have my breakfast at home.', False,
                 "With 'je' the form is 'prends', with an s."),
                ('Oui, je prends ma petit déjeuner à la maison.',
                 'Yes, I have my breakfast at home.', False,
                 "'déjeuner' is masculine, so it takes 'mon'."),
            ],
        ),
        _turn(
            'le travail',
            'Comment vas-tu au travail ?',
            'How do you get to work?',
            [
                ('Je vais à le travail en bus.', 'I go to work by bus.', False,
                 "'à' and 'le' contract to 'au'."),
                ('Je va au travail en bus.', 'I go to work by bus.', False,
                 "With 'je' the form is 'vais', not 'va'."),
                ('Je vais au travail en bus.', 'I go to work by bus.', True),
            ],
        ),
    ], FRENCH_STARTERS),

    ORDERING_FOOD: _bank([
        _turn(
            'la table',
            'Bonsoir ! Une table pour combien de personnes ?',
            'Good evening! A table for how many people?',
            [
                ("Un table pour deux, s'il vous plaît.",
                 'A table for two, please.', False,
                 "'table' is feminine, so it takes 'une'."),
                ("Une table pour deux, s'il vous plaît.",
                 'A table for two, please.', True),
                ("Une table par deux, s'il vous plaît.",
                 'A table for two, please.', False,
                 "The preposition here is 'pour', not 'par'."),
            ],
        ),
        _turn(
            "l'addition",
            'Vous avez terminé ?',
            'Have you finished?',
            [
                ("Oui, le addition s'il vous plaît.", 'Yes, the bill please.',
                 False, "'addition' is feminine and elides: l'addition."),
                ("Oui, l'addition s'il vous plaisez.", 'Yes, the bill please.',
                 False, "The set phrase is 's'il vous plaît'."),
                ("Oui, l'addition s'il vous plaît.", 'Yes, the bill please.',
                 True),
            ],
        ),
        _turn(
            "l'eau",
            "Qu'est-ce que vous voulez boire ?",
            'What would you like to drink?',
            [
                ("Un verre d'eau, s'il vous plaît.", 'A glass of water, please.',
                 True),
                ("Un verre de eau, s'il vous plaît.", 'A glass of water, please.',
                 False, "'de' elides before a vowel: d'eau."),
                ("Une verre d'eau, s'il vous plaît.", 'A glass of water, please.',
                 False, "'verre' is masculine, so it takes 'un'."),
            ],
        ),
    ], FRENCH_STARTERS),

    TRAVEL_BASICS: _bank([
        _turn(
            'le billet',
            'Bonjour, vous voulez aller où ?',
            'Hello, where would you like to go?',
            [
                ("Une billet pour Paris, s'il vous plaît.",
                 'A ticket to Paris, please.', False,
                 "'billet' is masculine, so it takes 'un'."),
                ("Un billet pour Paris, s'il vous plaît.",
                 'A ticket to Paris, please.', True),
                ("Un billet à Paris, s'il vous plaît.",
                 'A ticket to Paris, please.', False,
                 "A ticket to a place takes 'pour', not 'à'."),
            ],
        ),
        _turn(
            'la gare',
            'Le train part dans dix minutes.',
            'The train leaves in ten minutes.',
            [
                ("Où est le gare, s'il vous plaît ?",
                 'Where is the station, please?', False,
                 "'gare' is feminine, so it takes 'la'."),
                ("Où sont la gare, s'il vous plaît ?",
                 'Where is the station, please?', False,
                 "One station is singular: 'est', not 'sont'."),
                ("Où est la gare, s'il vous plaît ?",
                 'Where is the station, please?', True),
            ],
        ),
        _turn(
            "l'hôtel",
            "Votre hôtel est loin d'ici ?",
            'Is your hotel far from here?',
            [
                ('Non, mon hôtel est dans le centre.',
                 'No, my hotel is in the centre.', True),
                ('Non, mon hôtel es dans le centre.',
                 'No, my hotel is in the centre.', False,
                 "The form for 'il' is 'est', not 'es'."),
                ('Non, ma hôtel est dans le centre.',
                 'No, my hotel is in the centre.', False,
                 "'hôtel' is masculine, so it takes 'mon'."),
            ],
        ),
    ], FRENCH_STARTERS),
}


GERMAN_STARTERS = {
    'aufstehen': 'Ich stehe um ____ Uhr auf.',
    'frühstücken': 'Ich frühstücke ____.',
    'die arbeit': 'Ich fahre mit ____ zur Arbeit.',
    'der tisch': 'Einen Tisch für ____, bitte.',
    'die rechnung': 'Nein danke, ____ bitte.',
    'das wasser': 'Ein Glas ____, bitte.',
    'die fahrkarte': 'Eine Fahrkarte nach ____, bitte.',
    'der bahnhof': 'Wo ist ____, bitte?',
    'das hotel': 'Mein Hotel ist ____.',
}

GERMAN_TURNS = {
    DAILY_ROUTINE: _bank([
        _turn(
            'aufstehen',
            'Guten Morgen! Wann stehst du normalerweise auf?',
            'Good morning! When do you usually get up?',
            [
                ('Ich aufstehe um sieben Uhr.', 'I get up at seven.', False,
                 "'aufstehen' is separable - 'auf' goes to the end."),
                ('Ich stehe um sieben Uhr auf.', 'I get up at seven.', True),
                ('Ich stehst um sieben Uhr auf.', 'I get up at seven.', False,
                 "'stehst' goes with 'du' - use 'stehe' for 'ich'."),
            ],
        ),
        _turn(
            'frühstücken',
            'Und wo frühstückst du?',
            'And where do you have breakfast?',
            [
                ('Ich frühstücke zu Hause.', 'I have breakfast at home.', True),
                ('Ich frühstücken zu Hause.', 'I have breakfast at home.', False,
                 "Conjugate it: 'frühstücke' with 'ich', not the infinitive."),
                ('Ich frühstücke nach Hause.', 'I have breakfast at home.', False,
                 "'nach Hause' is movement - staying somewhere is 'zu Hause'."),
            ],
        ),
        _turn(
            'die Arbeit',
            'Wie kommst du zur Arbeit?',
            'How do you get to work?',
            [
                ('Ich fahre mit den Bus zur Arbeit.', 'I go to work by bus.',
                 False, "'mit' takes the dative: 'mit dem Bus'."),
                ('Ich mit dem Bus zur Arbeit fahre.', 'I go to work by bus.',
                 False, 'In a main clause the verb must come second.'),
                ('Ich fahre mit dem Bus zur Arbeit.', 'I go to work by bus.',
                 True),
            ],
        ),
    ], GERMAN_STARTERS),

    ORDERING_FOOD: _bank([
        _turn(
            'der Tisch',
            'Guten Abend! Für wie viele Personen?',
            'Good evening! For how many people?',
            [
                ('Ein Tisch für zwei, bitte.', 'A table for two, please.', False,
                 "This is the object, so it takes the accusative 'einen'."),
                ('Einen Tisch für zwei, bitten.', 'A table for two, please.',
                 False, "'bitten' means to ask - the polite word is 'bitte'."),
                ('Einen Tisch für zwei, bitte.', 'A table for two, please.', True),
            ],
        ),
        _turn(
            'die Rechnung',
            'Möchten Sie noch einen Nachtisch?',
            'Would you like a dessert as well?',
            [
                ('Nein danke, die Rechnung bitte.', 'No thanks, the bill please.',
                 True),
                ('Nein danke, der Rechnung bitte.', 'No thanks, the bill please.',
                 False, "'Rechnung' is feminine, so it takes 'die'."),
                ('Nein danke, ich möchte die Rechnung bekommt.',
                 'No thanks, I would like the bill.', False,
                 "After 'möchte' the second verb is an infinitive: 'bekommen'."),
            ],
        ),
        _turn(
            'das Wasser',
            'Was möchten Sie trinken?',
            'What would you like to drink?',
            [
                ('Eine Glas Wasser, bitte.', 'A glass of water, please.', False,
                 "'Glas' is neuter, so it takes 'ein'."),
                ('Ein Glas Wasser, bitte.', 'A glass of water, please.', True),
                ('Ich möchte ein Glas Wasser trinke.',
                 'I would like to drink a glass of water.', False,
                 "The second verb goes to the end as an infinitive: 'trinken'."),
            ],
        ),
    ], GERMAN_STARTERS),

    TRAVEL_BASICS: _bank([
        _turn(
            'die Fahrkarte',
            'Guten Tag, wohin möchten Sie?',
            'Hello, where would you like to go?',
            [
                ('Ein Fahrkarte nach Berlin, bitte.', 'A ticket to Berlin, please.',
                 False, "'Fahrkarte' is feminine, so it takes 'eine'."),
                ('Eine Fahrkarte zu Berlin, bitte.', 'A ticket to Berlin, please.',
                 False, "Cities take 'nach', not 'zu'."),
                ('Eine Fahrkarte nach Berlin, bitte.', 'A ticket to Berlin, please.',
                 True),
            ],
        ),
        _turn(
            'der Bahnhof',
            'Der Zug fährt in zehn Minuten.',
            'The train leaves in ten minutes.',
            [
                ('Wo ist der Bahnhof, bitte?', 'Where is the station, please?',
                 True),
                ('Wo ist die Bahnhof, bitte?', 'Where is the station, please?',
                 False, "'Bahnhof' is masculine, so it takes 'der'."),
                ('Wo der Bahnhof ist, bitte?', 'Where is the station, please?',
                 False, 'In a question the verb comes straight after the question word.'),
            ],
        ),
        _turn(
            'das Hotel',
            'Ist Ihr Hotel weit von hier?',
            'Is your hotel far from here?',
            [
                ('Nein, meine Hotel ist im Zentrum.', 'No, my hotel is in the centre.',
                 False, "'Hotel' is neuter, so it takes 'mein'."),
                ('Nein, mein Hotel ist in das Zentrum.',
                 'No, my hotel is in the centre.', False,
                 "Being somewhere takes the dative: 'im Zentrum'."),
                ('Nein, mein Hotel ist im Zentrum.', 'No, my hotel is in the centre.',
                 True),
            ],
        ),
    ], GERMAN_STARTERS),
}


# Written in Devanagari, which is what the vocabulary stores and what the
# browser's hi-IN voice reads aloud. The prompt tells the grader to accept
# Roman transliteration too, because a learner on a laptop has no easy way to
# type Devanagari and refusing their answer would punish the keyboard, not
# the Hindi.
HINDI_STARTERS = {
    'उठना': 'मैं ____ बजे उठता हूँ।',
    'नाश्ता करना': 'मैं ____ नाश्ता करता हूँ।',
    'काम': 'मैं ____ से काम पर जाता हूँ।',
    'मेज़': '____ लोगों के लिए एक मेज़, कृपया।',
    'बिल': 'नहीं, कृपया ____ ले आइए।',
    'पानी': 'एक गिलास ____, कृपया।',
    'टिकट': '____ के लिए एक टिकट, कृपया।',
    'स्टेशन': '____ कहाँ है?',
    'होटल': 'मेरा होटल ____ है।',
}

HINDI_TURNS = {
    DAILY_ROUTINE: _bank([
        _turn(
            'उठना',
            'नमस्ते! आप सुबह कितने बजे उठते हैं?',
            'Hello! What time do you get up in the morning?',
            [
                ('मैं सात बजे उठते हूँ।', 'I get up at seven.', False,
                 "With मैं the verb is उठता, not the plural उठते."),
                ('मैं सात बजे उठता हूँ।', 'I get up at seven.', True),
                ('मैं सात बजे उठता है।', 'I get up at seven.', False,
                 "मैं takes हूँ - है belongs to वह."),
            ],
        ),
        _turn(
            'नाश्ता करना',
            'आप नाश्ता कहाँ करते हैं?',
            'Where do you have breakfast?',
            [
                ('मैं घर पर नाश्ता करना हूँ।', 'I have breakfast at home.', False,
                 'करना is the infinitive - it needs to be करता here.'),
                ('मैं घर को नाश्ता करता हूँ।', 'I have breakfast at home.', False,
                 'A place takes पर or में, not को.'),
                ('मैं घर पर नाश्ता करता हूँ।', 'I have breakfast at home.', True),
            ],
        ),
        _turn(
            'काम',
            'आप काम पर कैसे जाते हैं?',
            'How do you get to work?',
            [
                ('मैं बस से काम पर जाता हूँ।', 'I go to work by bus.', True),
                ('मैं बस को काम पर जाता हूँ।', 'I go to work by bus.', False,
                 'Travelling by something takes से, not को.'),
                ('मैं बस से काम पर जाता हैं।', 'I go to work by bus.', False,
                 'मैं takes हूँ - हैं is the plural form.'),
            ],
        ),
    ], HINDI_STARTERS),

    ORDERING_FOOD: _bank([
        _turn(
            'मेज़',
            'नमस्ते! कितने लोगों के लिए?',
            'Hello! For how many people?',
            [
                ('दो लोग के लिए एक मेज़, कृपया।', 'A table for two, please.',
                 False, 'Before के लिए the noun goes oblique: लोगों.'),
                ('दो लोगों को एक मेज़, कृपया।', 'A table for two, please.',
                 False, '"For" here is के लिए, not को.'),
                ('दो लोगों के लिए एक मेज़, कृपया।', 'A table for two, please.',
                 True),
            ],
        ),
        _turn(
            'बिल',
            'कुछ और चाहिए?',
            'Would you like anything else?',
            [
                ('नहीं, कृपया बिल ले आइए।', 'No, please bring the bill.', True),
                ('नहीं, कृपया बिल ले आओ।', 'No, please bring the bill.', False,
                 'आओ is the तुम form - with कृपया use आइए.'),
                ('नहीं, कृपया बिल को ले आइए।', 'No, please bring the bill.',
                 False, 'An inanimate object like बिल does not take को here.'),
            ],
        ),
        _turn(
            'पानी',
            'आप क्या पीना चाहेंगे?',
            'What would you like to drink?',
            [
                ('एक गिलास पानी को, कृपया।', 'A glass of water, please.', False,
                 'No postposition is needed after पानी here.'),
                ('एक गिलास पानी, कृपया।', 'A glass of water, please.', True),
                ('एक गिलास में पानी, कृपया।', 'A glass of water, please.', False,
                 'The phrase is एक गिलास पानी - में changes the meaning.'),
            ],
        ),
    ], HINDI_STARTERS),

    TRAVEL_BASICS: _bank([
        _turn(
            'टिकट',
            'आपको कहाँ जाना है?',
            'Where do you need to go?',
            [
                ('दिल्ली के लिए एक टिकट, कृपया।', 'A ticket to Delhi, please.',
                 True),
                ('दिल्ली को एक टिकट, कृपया।', 'A ticket to Delhi, please.',
                 False, 'A ticket to a place takes के लिए, not को.'),
                ('दिल्ली के लिए एक टिकट चाहिए हूँ।', 'I need a ticket to Delhi.',
                 False, 'चाहिए stands on its own - it does not take हूँ.'),
            ],
        ),
        _turn(
            'स्टेशन',
            'ट्रेन दस मिनट में जाएगी।',
            'The train leaves in ten minutes.',
            [
                ('स्टेशन कहाँ हैं?', 'Where is the station?', False,
                 'One station is singular, so it takes है.'),
                ('स्टेशन कहाँ है?', 'Where is the station?', True),
                ('स्टेशन को कहाँ है?', 'Where is the station?', False,
                 'The subject of है does not take को.'),
            ],
        ),
        _turn(
            'होटल',
            'क्या आपका होटल यहाँ से दूर है?',
            'Is your hotel far from here?',
            [
                ('नहीं, मेरी होटल शहर के बीच में है।',
                 'No, my hotel is in the city centre.', False,
                 'होटल is masculine, so it takes मेरा.'),
                ('नहीं, मेरा होटल शहर के बीच में हैं।',
                 'No, my hotel is in the city centre.', False,
                 'One hotel is singular, so it takes है.'),
                ('नहीं, मेरा होटल शहर के बीच में है।',
                 'No, my hotel is in the city centre.', True),
            ],
        ),
    ], HINDI_STARTERS),
}


# Keyed by language, never falling through to another one: serving Spanish
# into a French lesson would teach the wrong thing, which is worse than
# repeating a turn.
FALLBACK_TURNS = {
    'Spanish': SPANISH_TURNS,
    'French': FRENCH_TURNS,
    'German': GERMAN_TURNS,
    'Hindi': HINDI_TURNS,
}
