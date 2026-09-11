"""Hand-written conversation turns used by DEMO_MODE and every failure path.

Every line here is written and checked by hand. This is what the app falls
back to when a provider is down, and what `DEMO_MODE=true` serves instead of
calling out at all - so a live demo never depends on someone else's uptime.

Rules these turns follow, matching what the live prompt asks the model for:

- Each topic runs a coherent eight-turn arc, so a full session never repeats.
- Every `target_word` is a real `VocabItem.spanish` value from seed_vocab, so
  the SM-2 update credits the vocabulary actually on screen.
- Exactly one reply per turn is correct, and its position varies.
- Each wrong reply contains a concrete grammatical error - conjugation,
  gender, ser/estar, a missing preposition or a confusable word - never merely
  an off-topic or incomplete answer.
"""

from .models import DAILY_ROUTINE, ORDERING_FOOD, TRAVEL_BASICS


def _turn(target, es, en, replies):
    """Build a turn, numbering the replies so ids always match their order."""
    return {
        'target_word': target,
        'tutor_message_es': es,
        'tutor_message_en': en,
        'replies': [
            {
                'id': index,
                'es': reply[0],
                'en': reply[1],
                'is_correct': reply[2],
                'why_wrong': reply[3] if len(reply) > 3 else '',
            }
            for index, reply in enumerate(replies)
        ],
    }


FALLBACK_TURNS = {
    # --- waking up through going to bed ---------------------------------
    DAILY_ROUTINE: [
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
    ],
    # --- sitting down through paying ------------------------------------
    ORDERING_FOOD: [
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
    ],
    # --- buying a ticket through finding the hotel -----------------------
    TRAVEL_BASICS: [
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
    ],
}
